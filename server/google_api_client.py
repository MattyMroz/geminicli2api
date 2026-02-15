"""
Google API Client - Handles all communication with Google's Gemini API.
Used by both OpenAI compatibility layer and native Gemini endpoints.
"""
import json
import logging
import requests
from fastapi import Response
from fastapi.responses import StreamingResponse
from google.auth.transport.requests import Request as GoogleAuthRequest

from server.auth import get_credentials, save_credentials, get_user_project_id, onboard_user
from server.utils import get_user_agent
from server.config import (
    CODE_ASSIST_ENDPOINT,
    DEFAULT_SAFETY_SETTINGS,
    get_base_model_name,
    is_search_model,
    get_thinking_budget,
    should_include_thoughts
)
import asyncio


def _get_account_count() -> int:
    """Get number of available accounts for retry logic."""
    from server.auth import _accounts_manager
    if _accounts_manager:
        return max(_accounts_manager.count, 1)
    return 1


def _try_send_request_with_creds(payload: dict, is_streaming: bool, creds) -> Response:
    """Single attempt to send a request to Google's Gemini API using given credentials."""
    if not creds:
        return Response(
            content="Authentication failed. Please restart the proxy to log in.",
            status_code=500
        )

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleAuthRequest())
            save_credentials(creds)
        except Exception:
            return Response(
                content="Token refresh failed. Please restart the proxy to re-authenticate.",
                status_code=500
            )
    elif not creds.token:
        return Response(
            content="No access token. Please restart the proxy to re-authenticate.",
            status_code=500
        )

    proj_id = get_user_project_id(creds)
    if not proj_id:
        return Response(content="Failed to get user project ID.", status_code=500)

    onboard_user(creds, proj_id)

    final_payload = {
        "model": payload.get("model"),
        "project": proj_id,
        "request": payload.get("request", {})
    }

    action = "streamGenerateContent" if is_streaming else "generateContent"
    target_url = f"{CODE_ASSIST_ENDPOINT}/v1internal:{action}"
    if is_streaming:
        target_url += "?alt=sse"

    request_headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
        "User-Agent": get_user_agent(),
    }

    final_post_data = json.dumps(final_payload)

    try:
        if is_streaming:
            resp = requests.post(target_url, data=final_post_data, headers=request_headers, stream=True)
            return _handle_streaming_response(resp)
        else:
            resp = requests.post(target_url, data=final_post_data, headers=request_headers)
            return _handle_non_streaming_response(resp)
    except requests.exceptions.RequestException as e:
        logging.error(f"Request to Google API failed: {str(e)}")
        return Response(
            content=json.dumps({"error": {"message": f"Request failed: {str(e)}"}}),
            status_code=500,
            media_type="application/json"
        )
    except Exception as e:
        logging.error(f"Unexpected error during Google API request: {str(e)}")
        return Response(
            content=json.dumps({"error": {"message": f"Unexpected error: {str(e)}"}}),
            status_code=500,
            media_type="application/json"
        )


async def send_gemini_request(payload: dict, is_streaming: bool = False) -> Response:
    """Send a request to Google's Gemini API, retrying with different accounts on 403.
    
    Credentials are obtained in the async context (proper round-robin),
    then the blocking HTTP call runs in a thread.
    """
    max_retries = _get_account_count()
    last_response = None

    for attempt in range(max_retries):
        # Get credentials HERE, in the event loop — thread-safe rotation
        creds = get_credentials()
        response = await asyncio.to_thread(_try_send_request_with_creds, payload, is_streaming, creds)
        last_response = response

        # Check if 403 — try next account (round-robin rotates automatically)
        status = getattr(response, "status_code", None)
        if status == 403 and attempt < max_retries - 1:
            logging.warning(f"Account returned 403, trying next account ({attempt + 1}/{max_retries})...")
            continue
        return response

    return last_response


def _handle_streaming_response(resp) -> StreamingResponse:
    """Handle streaming response from Google API."""
    if resp.status_code != 200:
        logging.error(f"Google API returned status {resp.status_code}: {resp.text}")
        error_message = f"Google API error: {resp.status_code}"
        try:
            error_data = resp.json()
            if "error" in error_data:
                error_message = error_data["error"].get("message", error_message)
        except Exception:
            pass

        async def error_generator():
            error_response = {
                "error": {
                    "message": error_message,
                    "type": "invalid_request_error" if resp.status_code == 404 else "api_error",
                    "code": resp.status_code
                }
            }
            yield f'data: {json.dumps(error_response)}\n\n'.encode('utf-8')

        response_headers = {
            "Content-Type": "text/event-stream",
            "Content-Disposition": "attachment",
            "Vary": "Origin, X-Origin, Referer",
            "X-XSS-Protection": "0",
            "X-Frame-Options": "SAMEORIGIN",
            "X-Content-Type-Options": "nosniff",
            "Server": "ESF"
        }

        return StreamingResponse(
            error_generator(),
            media_type="text/event-stream",
            headers=response_headers,
            status_code=resp.status_code
        )

    async def stream_generator():
        try:
            import queue
            import threading

            chunk_queue = queue.Queue()

            def _read_stream():
                """Read blocking iter_lines in a thread, push to queue."""
                try:
                    with resp:
                        for chunk in resp.iter_lines():
                            chunk_queue.put(chunk)
                    chunk_queue.put(None)  # sentinel
                except Exception as ex:
                    chunk_queue.put(ex)

            thread = threading.Thread(target=_read_stream, daemon=True)
            thread.start()

            while True:
                # Non-blocking poll so we don't block the event loop
                while True:
                    try:
                        item = chunk_queue.get_nowait()
                        break
                    except queue.Empty:
                        await asyncio.sleep(0.01)

                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                chunk = item

                if chunk:
                    if not isinstance(chunk, str):
                        chunk = chunk.decode('utf-8', "ignore")

                    if chunk.startswith('data: '):
                        chunk = chunk[len('data: '):]
                        try:
                            obj = json.loads(chunk)
                            if "response" in obj:
                                response_chunk = obj["response"]
                                response_json = json.dumps(response_chunk, separators=(',', ':'))
                                response_line = f"data: {response_json}\n\n"
                                yield response_line.encode('utf-8', "ignore")
                                await asyncio.sleep(0)
                            else:
                                obj_json = json.dumps(obj, separators=(',', ':'))
                                yield f"data: {obj_json}\n\n".encode('utf-8', "ignore")
                        except json.JSONDecodeError:
                            continue
        except requests.exceptions.RequestException as e:
            logging.error(f"Streaming request failed: {str(e)}")
            error_response = {
                "error": {"message": f"Upstream request failed: {str(e)}", "type": "api_error", "code": 502}
            }
            yield f'data: {json.dumps(error_response)}\n\n'.encode('utf-8', "ignore")
        except Exception as e:
            logging.error(f"Unexpected error during streaming: {str(e)}")
            error_response = {
                "error": {"message": f"An unexpected error occurred: {str(e)}", "type": "api_error", "code": 500}
            }
            yield f'data: {json.dumps(error_response)}\n\n'.encode('utf-8', "ignore")

    response_headers = {
        "Content-Type": "text/event-stream",
        "Content-Disposition": "attachment",
        "Vary": "Origin, X-Origin, Referer",
        "X-XSS-Protection": "0",
        "X-Frame-Options": "SAMEORIGIN",
        "X-Content-Type-Options": "nosniff",
        "Server": "ESF"
    }

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers=response_headers
    )


def _handle_non_streaming_response(resp) -> Response:
    """Handle non-streaming response from Google API."""
    if resp.status_code == 200:
        try:
            google_api_response = resp.text
            if google_api_response.startswith('data: '):
                google_api_response = google_api_response[len('data: '):]
            google_api_response = json.loads(google_api_response)
            standard_gemini_response = google_api_response.get("response")
            return Response(
                content=json.dumps(standard_gemini_response),
                status_code=200,
                media_type="application/json; charset=utf-8"
            )
        except (json.JSONDecodeError, AttributeError) as e:
            logging.error(f"Failed to parse Google API response: {str(e)}")
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type=resp.headers.get("Content-Type")
            )
    else:
        logging.error(f"Google API returned status {resp.status_code}: {resp.text}")
        try:
            error_data = resp.json()
            if "error" in error_data:
                error_message = error_data["error"].get("message", f"API error: {resp.status_code}")
                error_response = {
                    "error": {
                        "message": error_message,
                        "type": "invalid_request_error" if resp.status_code == 404 else "api_error",
                        "code": resp.status_code
                    }
                }
                return Response(
                    content=json.dumps(error_response),
                    status_code=resp.status_code,
                    media_type="application/json"
                )
        except (json.JSONDecodeError, KeyError):
            pass

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("Content-Type")
        )


def build_gemini_payload_from_openai(openai_payload: dict) -> dict:
    """Build a Gemini API payload from an OpenAI-transformed request."""
    model = openai_payload.get("model")
    safety_settings = openai_payload.get("safetySettings", DEFAULT_SAFETY_SETTINGS)

    request_data = {
        "contents": openai_payload.get("contents"),
        "systemInstruction": openai_payload.get("systemInstruction"),
        "cachedContent": openai_payload.get("cachedContent"),
        "tools": openai_payload.get("tools"),
        "toolConfig": openai_payload.get("toolConfig"),
        "safetySettings": safety_settings,
        "generationConfig": openai_payload.get("generationConfig", {}),
    }

    request_data = {k: v for k, v in request_data.items() if v is not None}

    return {
        "model": model,
        "request": request_data
    }


def build_gemini_payload_from_native(native_request: dict, model_from_path: str) -> dict:
    """Build a Gemini API payload from a native Gemini request."""
    native_request["safetySettings"] = DEFAULT_SAFETY_SETTINGS

    if "generationConfig" not in native_request:
        native_request["generationConfig"] = {}

    if "thinkingConfig" not in native_request["generationConfig"]:
        native_request["generationConfig"]["thinkingConfig"] = {}

    if "gemini-2.5-flash-image" not in model_from_path:
        thinking_budget = get_thinking_budget(model_from_path)
        include_thoughts = should_include_thoughts(model_from_path)

        native_request["generationConfig"]["thinkingConfig"]["includeThoughts"] = include_thoughts
        if "thinkingBudget" not in native_request["generationConfig"]["thinkingConfig"]:
            native_request["generationConfig"]["thinkingConfig"]["thinkingBudget"] = thinking_budget

    if is_search_model(model_from_path):
        if "tools" not in native_request:
            native_request["tools"] = []
        if not any(tool.get("googleSearch") for tool in native_request["tools"]):
            native_request["tools"].append({"googleSearch": {}})

    return {
        "model": get_base_model_name(model_from_path),
        "request": native_request
    }
