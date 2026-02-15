"""
Google API Client - Handles all communication with Google's Gemini API.
Used by both OpenAI compatibility layer and native Gemini endpoints.
"""
import json
import logging
import uuid
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
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
    should_include_thoughts,
    _has_thinking_support,
)
import asyncio

# Request timeouts (seconds)
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 300  # 5 min for long generations
STREAM_READ_TIMEOUT = 600  # 10 min for streaming

# --- Connection-pooled HTTP session ---
_http_session: requests.Session = None


def _get_session() -> requests.Session:
    """Get or create a module-level requests.Session with connection pooling."""
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        # Connection pool: up to 20 connections, 10 per host (Google API only)
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            pool_block=False,
        )
        _http_session.mount("https://", adapter)
        _http_session.mount("http://", adapter)
    return _http_session


def _get_account_count() -> int:
    """Get number of available accounts for retry logic."""
    from server.auth import _accounts_manager
    if _accounts_manager:
        return max(_accounts_manager.count, 1)
    return 1


def _try_send_request_with_creds(payload: dict, is_streaming: bool, creds, request_id: str = "") -> Response:
    """Single attempt to send a request to Google's Gemini API using given credentials."""
    rid = request_id or str(uuid.uuid4())[:8]

    if not creds:
        logging.error(f"[{rid}] No credentials available")
        return Response(
            content=json.dumps({"error": {"message": "Authentication failed. No credentials available.", "code": 500}}),
            status_code=500,
            media_type="application/json"
        )

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleAuthRequest())
            save_credentials(creds)
            logging.debug(f"[{rid}] Token refreshed successfully")
        except Exception as e:
            logging.error(f"[{rid}] Token refresh failed: {e}")
            return Response(
                content=json.dumps({"error": {"message": "Token refresh failed. Please restart the proxy.", "code": 500}}),
                status_code=500,
                media_type="application/json"
            )
    elif not creds.token:
        logging.error(f"[{rid}] No access token available")
        return Response(
            content=json.dumps({"error": {"message": "No access token. Please restart the proxy.", "code": 500}}),
            status_code=500,
            media_type="application/json"
        )

    try:
        proj_id = get_user_project_id(creds)
    except Exception as e:
        logging.error(f"[{rid}] Failed to get project ID: {e}")
        return Response(
            content=json.dumps({"error": {"message": f"Project ID discovery failed: {e}", "code": 500}}),
            status_code=500,
            media_type="application/json"
        )

    if not proj_id:
        logging.error(f"[{rid}] No project ID")
        return Response(
            content=json.dumps({"error": {"message": "Failed to get user project ID.", "code": 500}}),
            status_code=500,
            media_type="application/json"
        )

    try:
        onboard_user(creds, proj_id)
    except Exception as e:
        logging.error(f"[{rid}] Onboarding failed: {e}")
        return Response(
            content=json.dumps({"error": {"message": f"Onboarding failed: {e}", "code": 500}}),
            status_code=500,
            media_type="application/json"
        )

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
    model_name = payload.get("model", "unknown")
    logging.info(f"[{rid}] Sending request to Google API: model={model_name}, stream={is_streaming}")

    try:
        session = _get_session()
        if is_streaming:
            resp = session.post(
                target_url, data=final_post_data, headers=request_headers,
                stream=True, timeout=(CONNECT_TIMEOUT, STREAM_READ_TIMEOUT))
            return _handle_streaming_response(resp, rid)
        else:
            resp = session.post(
                target_url, data=final_post_data, headers=request_headers,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
            return _handle_non_streaming_response(resp, rid)
    except requests.exceptions.ConnectTimeout:
        logging.error(f"[{rid}] Connection timeout to Google API")
        return Response(
            content=json.dumps(
                {"error": {"message": "Connection timeout to Google API. Try again.", "code": 504}}),
            status_code=504,
            media_type="application/json"
        )
    except requests.exceptions.ReadTimeout:
        logging.error(f"[{rid}] Read timeout from Google API")
        return Response(
            content=json.dumps(
                {"error": {"message": "Read timeout from Google API. The model may need more time.", "code": 504}}),
            status_code=504,
            media_type="application/json"
        )
    except requests.exceptions.ConnectionError as e:
        logging.error(f"[{rid}] Connection error: {e}")
        return Response(
            content=json.dumps(
                {"error": {"message": "Cannot connect to Google API. Check your internet connection.", "code": 502}}),
            status_code=502,
            media_type="application/json"
        )
    except requests.exceptions.RequestException as e:
        logging.error(f"[{rid}] Request to Google API failed: {str(e)}")
        return Response(
            content=json.dumps(
                {"error": {"message": f"Request failed: {str(e)}", "code": 500}}),
            status_code=500,
            media_type="application/json"
        )
    except Exception as e:
        logging.error(f"[{rid}] Unexpected error during Google API request: {str(e)}")
        return Response(
            content=json.dumps(
                {"error": {"message": f"Unexpected error: {str(e)}", "code": 500}}),
            status_code=500,
            media_type="application/json"
        )


async def send_gemini_request(payload: dict, is_streaming: bool = False) -> Response:
    """Send a request to Google's Gemini API, retrying with different accounts on 403.

    Credentials are obtained in the async context (proper round-robin),
    then the blocking HTTP call runs in a thread.
    """
    request_id = str(uuid.uuid4())[:8]
    max_retries = _get_account_count()
    last_response = None
    model_name = payload.get("model", "unknown")

    logging.info(f"[{request_id}] New request: model={model_name}, stream={is_streaming}, accounts={max_retries}")

    for attempt in range(max_retries):
        # Get credentials HERE, in the event loop — thread-safe rotation
        creds = get_credentials()
        response = await asyncio.to_thread(_try_send_request_with_creds, payload, is_streaming, creds, request_id)
        last_response = response

        # Check if 403 — try next account (round-robin rotates automatically)
        status = getattr(response, "status_code", None)
        if status == 403 and attempt < max_retries - 1:
            logging.warning(
                f"[{request_id}] Account returned 403, trying next account ({attempt + 1}/{max_retries})...")
            continue

        if status and status >= 400:
            logging.warning(f"[{request_id}] Request completed with status {status}")
        else:
            logging.info(f"[{request_id}] Request completed successfully")

        return response

    logging.error(f"[{request_id}] All {max_retries} accounts failed")
    return last_response


def _handle_streaming_response(resp, rid: str = "") -> StreamingResponse:
    """Handle streaming response from Google API."""
    if resp.status_code != 200:
        logging.error(
            f"[{rid}] Google API returned status {resp.status_code}: {resp.text[:500]}")
        error_message = f"Google API error: {resp.status_code}"
        try:
            error_data = resp.json()
            if "error" in error_data:
                error_message = error_data["error"].get(
                    "message", error_message)
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
            import threading

            loop = asyncio.get_running_loop()
            chunk_queue = asyncio.Queue()

            def _read_stream():
                """Read blocking iter_lines in a thread, push to async queue."""
                try:
                    with resp:
                        for chunk in resp.iter_lines():
                            loop.call_soon_threadsafe(chunk_queue.put_nowait, chunk)
                    loop.call_soon_threadsafe(chunk_queue.put_nowait, None)  # sentinel
                except Exception as ex:
                    loop.call_soon_threadsafe(chunk_queue.put_nowait, ex)

            thread = threading.Thread(target=_read_stream, daemon=True)
            thread.start()

            while True:
                item = await chunk_queue.get()

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
                                response_json = json.dumps(
                                    response_chunk, separators=(',', ':'))
                                response_line = f"data: {response_json}\n\n"
                                yield response_line.encode('utf-8', "ignore")
                                await asyncio.sleep(0)
                            else:
                                obj_json = json.dumps(
                                    obj, separators=(',', ':'))
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


def _handle_non_streaming_response(resp, rid: str = "") -> Response:
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
        logging.error(
            f"Google API returned status {resp.status_code}: {resp.text}")
        try:
            error_data = resp.json()
            if "error" in error_data:
                error_message = error_data["error"].get(
                    "message", f"API error: {resp.status_code}")
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
    safety_settings = openai_payload.get(
        "safetySettings", DEFAULT_SAFETY_SETTINGS)

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

    if _has_thinking_support(model_from_path):
        if "thinkingConfig" not in native_request["generationConfig"]:
            native_request["generationConfig"]["thinkingConfig"] = {}

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
