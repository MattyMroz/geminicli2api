"""
Gemini API Client - talks to the official generativelanguage.googleapis.com.

Second backend next to google_api_client.py (OAuth / CodeAssist). This one uses
a plain AI Studio API key, so it stays inside Google's documented free tier
instead of the internal Gemini CLI endpoint.

Both backends speak the same native Gemini shapes, so the routers and the
OpenAI compatibility layer call this through send_gemini_request() unchanged.
"""
import asyncio
import json
import logging
import uuid

import requests
from fastapi import Response
from fastapi.responses import StreamingResponse
from requests.adapters import HTTPAdapter

from server.config import GEMINI_API_ENDPOINT, GEMINI_API_KEY, get_base_model_name

# Request timeouts (seconds) — same budgets as the OAuth backend
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 300  # 5 min for long generations
STREAM_READ_TIMEOUT = 600  # 10 min for streaming

# Harm categories the public API accepts. DEFAULT_SAFETY_SETTINGS also carries
# CodeAssist-only ones (HARM_CATEGORY_IMAGE_*, HARM_CATEGORY_UNSPECIFIED) which
# this endpoint rejects with 400, so they are dropped per request.
# Probed against v1beta on 2026-07-30.
SUPPORTED_HARM_CATEGORIES = frozenset({
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
    "HARM_CATEGORY_CIVIC_INTEGRITY",
    "HARM_CATEGORY_JAILBREAK",
})

# --- Connection-pooled HTTP session ---
_http_session: requests.Session | None = None


def _get_session() -> requests.Session:
    """Get or create a module-level requests.Session with connection pooling."""
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            pool_block=False,
        )
        _http_session.mount("https://", adapter)
        _http_session.mount("http://", adapter)
    return _http_session


def is_api_key_configured() -> bool:
    """Return whether an AI Studio API key is available."""
    return bool(GEMINI_API_KEY)


def _clean_model_id(model: str) -> str:
    """Reduce a proxy model name to the bare id the API URL expects.

    Three things get stripped. A "models/" prefix, because the URL already has
    one. A trailing ":action", because the native route pattern
    "{model_name}:{action}" does not split on the colon, so model_name arrives
    as "gemini-3.5-flash-lite:generateContent". And the proxy's own variant
    suffixes (-search/-nothinking/-maxthinking), which describe how to build the
    request, not a model the API knows.

    The OAuth backend never needed this: it sends the model in the body, and the
    native route hands it the name unresolved.
    """
    cleaned = model.strip().removeprefix("models/")
    if ":" in cleaned:
        cleaned = cleaned.split(":", 1)[0]
    return get_base_model_name(cleaned)


def _adapt_request_body(request_body: dict) -> dict:
    """Drop request fields the public API does not accept.

    Keeps the caller's payload untouched: the proxy builds one body shaped for
    CodeAssist, and only the parts this endpoint rejects are filtered out.
    """
    safety_settings = request_body.get("safetySettings")
    if not isinstance(safety_settings, list):
        return request_body

    kept = [s for s in safety_settings if s.get("category") in SUPPORTED_HARM_CATEGORIES]
    if len(kept) == len(safety_settings):
        return request_body

    adapted = dict(request_body)
    adapted["safetySettings"] = kept
    return adapted


def _error_response(message: str, code: int) -> Response:
    """Build a Gemini-shaped JSON error response."""
    return Response(
        content=json.dumps({"error": {"message": message, "code": code}}),
        status_code=code,
        media_type="application/json",
    )


def _explain_status(resp) -> str:
    """Turn an upstream error into a message that says what to do next.

    Mirrors the failure modes the AniShift Gemini provider maps: quota vs plain
    rate limit, missing model, blocked credentials, transient overload.
    """
    try:
        error = resp.json().get("error", {})
        upstream = error.get("message", "")
        status = error.get("status", "")
    except Exception:
        upstream = resp.text[:200]
        status = ""

    marker = f"{upstream} {status}".lower()
    if resp.status_code == 429:
        if any(f in marker for f in ("daily", "per_day", "perday")):
            return f"Gemini daily quota exhausted (free tier). Wait for the reset. {upstream}"
        return f"Gemini rate limit reached. Retry shortly. {upstream}"
    if resp.status_code == 404:
        return f"Model not found on this API key. Check the model id. {upstream}"
    if resp.status_code in (401, 403):
        return f"GEMINI_API_KEY rejected. Check the key in .env. {upstream}"
    if resp.status_code == 503:
        return f"Model temporarily overloaded upstream. Retry shortly. {upstream}"
    return upstream or f"Gemini API error: {resp.status_code}"


def _try_send_request(payload: dict, is_streaming: bool, request_id: str = "") -> Response:
    """Single attempt against generativelanguage.googleapis.com."""
    rid = request_id or str(uuid.uuid4())[:8]

    if not GEMINI_API_KEY:
        logging.error(f"[{rid}] GEMINI_API_KEY is not set")
        return _error_response("GEMINI_API_KEY is not set. Add it to .env.", 500)

    # The OAuth backend wraps the payload as {model, project, request}; the
    # public API takes the request body directly with the model in the URL.
    raw_model = payload.get("model", "")
    model = _clean_model_id(raw_model)
    request_body = _adapt_request_body(payload.get("request", {}))

    # The native route cannot split "{model_name}:{action}" on the colon, so it
    # always reports action="generateContent" and streaming is lost. The action
    # is still readable from the model name it passed through.
    if ":" in raw_model:
        is_streaming = raw_model.split(":", 1)[1].lower().startswith("stream")

    action = "streamGenerateContent" if is_streaming else "generateContent"
    target_url = f"{GEMINI_API_ENDPOINT}/v1beta/models/{model}:{action}"
    if is_streaming:
        target_url += "?alt=sse"

    request_headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }

    logging.info(f"[{rid}] Sending request to Gemini API: model={model}, stream={is_streaming}")

    try:
        session = _get_session()
        if is_streaming:
            resp = session.post(
                target_url, data=json.dumps(request_body), headers=request_headers,
                stream=True, timeout=(CONNECT_TIMEOUT, STREAM_READ_TIMEOUT))
            return _handle_streaming_response(resp, rid)
        resp = session.post(
            target_url, data=json.dumps(request_body), headers=request_headers,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        return _handle_non_streaming_response(resp, rid)
    except requests.exceptions.ConnectTimeout:
        logging.error(f"[{rid}] Connection timeout to Gemini API")
        return _error_response("Connection timeout to Gemini API. Try again.", 504)
    except requests.exceptions.ReadTimeout:
        logging.error(f"[{rid}] Read timeout from Gemini API")
        return _error_response("Read timeout from Gemini API. The model may need more time.", 504)
    except requests.exceptions.ConnectionError as e:
        logging.error(f"[{rid}] Connection error: {e}")
        return _error_response("Cannot connect to Gemini API. Check your internet connection.", 502)
    except requests.exceptions.RequestException as e:
        logging.error(f"[{rid}] Request to Gemini API failed: {e}")
        return _error_response(f"Request failed: {e}", 500)
    except Exception as e:
        logging.error(f"[{rid}] Unexpected error during Gemini API request: {e}")
        return _error_response(f"Unexpected error: {e}", 500)


async def send_gemini_api_request(payload: dict, is_streaming: bool = False) -> Response:
    """Send one request through the API-key backend.

    No account rotation here: a single key means a retry would hit the same
    quota, so failures are returned as-is instead of being retried blindly.
    """
    request_id = str(uuid.uuid4())[:8]
    model = payload.get("model", "unknown")
    logging.info(f"[{request_id}] New API-key request: model={model}, stream={is_streaming}")

    response = await asyncio.to_thread(_try_send_request, payload, is_streaming, request_id)

    status = getattr(response, "status_code", None)
    if status and status >= 400:
        logging.warning(f"[{request_id}] Request completed with status {status}")
    else:
        logging.info(f"[{request_id}] Request completed successfully")
    return response


def _handle_streaming_response(resp, rid: str = "") -> StreamingResponse:
    """Relay an SSE stream from the Gemini API.

    Unlike CodeAssist, the public API already emits bare Gemini chunks, so the
    lines pass through without unwrapping a "response" envelope.
    """
    response_headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Content-Type-Options": "nosniff",
    }

    if resp.status_code != 200:
        error_message = _explain_status(resp)
        logging.error(f"[{rid}] Gemini API returned status {resp.status_code}: {error_message}")

        async def error_generator():
            error_response = {
                "error": {
                    "message": error_message,
                    "type": "invalid_request_error" if resp.status_code == 404 else "api_error",
                    "code": resp.status_code,
                }
            }
            yield f'data: {json.dumps(error_response)}\n\n'.encode()

        return StreamingResponse(
            error_generator(),
            media_type="text/event-stream",
            headers=response_headers,
            status_code=resp.status_code,
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
                        except json.JSONDecodeError:
                            continue
                        obj_json = json.dumps(obj, separators=(',', ':'))
                        yield f"data: {obj_json}\n\n".encode('utf-8', "ignore")
                        await asyncio.sleep(0)
        except requests.exceptions.RequestException as e:
            logging.error(f"Streaming request failed: {e}")
            error_response = {
                "error": {"message": f"Upstream request failed: {e}", "type": "api_error", "code": 502}
            }
            yield f'data: {json.dumps(error_response)}\n\n'.encode('utf-8', "ignore")
        except Exception as e:
            logging.error(f"Unexpected error during streaming: {e}")
            error_response = {
                "error": {"message": f"An unexpected error occurred: {e}", "type": "api_error", "code": 500}
            }
            yield f'data: {json.dumps(error_response)}\n\n'.encode('utf-8', "ignore")

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers=response_headers,
    )


def _handle_non_streaming_response(resp, rid: str = "") -> Response:
    """Handle a non-streaming response from the Gemini API."""
    if resp.status_code == 200:
        # Already a bare Gemini response — no envelope to unwrap.
        return Response(
            content=resp.content,
            status_code=200,
            media_type="application/json; charset=utf-8",
        )

    error_message = _explain_status(resp)
    logging.error(f"[{rid}] Gemini API returned status {resp.status_code}: {error_message}")
    error_response = {
        "error": {
            "message": error_message,
            "type": "invalid_request_error" if resp.status_code == 404 else "api_error",
            "code": resp.status_code,
        }
    }
    return Response(
        content=json.dumps(error_response),
        status_code=resp.status_code,
        media_type="application/json",
    )
