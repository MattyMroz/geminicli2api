"""
Gemini API Routes - Handles native Gemini API endpoints.
Proxies requests directly to Google's API without format transformations.
"""
import json
import logging
from fastapi import APIRouter, Request, Response, Depends

from server.auth import authenticate_user
from server.google_api_client import send_gemini_request, build_gemini_payload_from_native
from server.config import SUPPORTED_MODELS

router = APIRouter()


@router.get("/v1beta/models")
async def gemini_list_models(request: Request, username: str = Depends(authenticate_user)):
    """Native Gemini models endpoint."""
    try:
        logging.info("Gemini models list requested")
        models_response = {"models": SUPPORTED_MODELS}
        logging.info(f"Returning {len(SUPPORTED_MODELS)} Gemini models")
        return Response(
            content=json.dumps(models_response),
            status_code=200,
            media_type="application/json; charset=utf-8"
        )
    except Exception as e:
        logging.error(f"Failed to list Gemini models: {str(e)}")
        return Response(
            content=json.dumps({"error": {"message": f"Failed to list models: {str(e)}", "code": 500}}),
            status_code=500,
            media_type="application/json"
        )


@router.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def gemini_proxy(request: Request, full_path: str, username: str = Depends(authenticate_user)):
    """Native Gemini API proxy endpoint — handles all native Gemini API calls."""
    try:
        post_data = await request.body()
        is_streaming = "stream" in full_path.lower()
        model_name = _extract_model_from_path(full_path)

        logging.info(f"Gemini proxy request: path={full_path}, model={model_name}, stream={is_streaming}")

        if not model_name:
            logging.error(f"Could not extract model name from path: {full_path}")
            return Response(
                content=json.dumps({"error": {"message": f"Could not extract model name from path: {full_path}", "code": 400}}),
                status_code=400,
                media_type="application/json"
            )

        try:
            if post_data:
                incoming_request = json.loads(post_data)
            else:
                incoming_request = {}
        except json.JSONDecodeError:
            return Response(
                content=json.dumps({"error": {"message": "Invalid JSON in request body", "code": 400}}),
                status_code=400,
                media_type="application/json"
            )

        gemini_payload = build_gemini_payload_from_native(incoming_request, model_name)
        response = await send_gemini_request(gemini_payload, is_streaming=is_streaming)

        if hasattr(response, 'status_code'):
            if response.status_code != 200:
                logging.error(f"Gemini API returned error: status={response.status_code}")
            else:
                logging.info(f"Successfully processed Gemini request for model: {model_name}")

        return response

    except Exception as e:
        logging.error(f"Gemini proxy error: {str(e)}")
        return Response(
            content=json.dumps({"error": {"message": f"Proxy error: {str(e)}", "code": 500}}),
            status_code=500,
            media_type="application/json"
        )


def _extract_model_from_path(path: str) -> str:
    """Extract model name from a Gemini API path."""
    parts = path.split('/')
    try:
        models_index = parts.index('models')
        if models_index + 1 < len(parts):
            model_name = parts[models_index + 1]
            if ':' in model_name:
                model_name = model_name.split(':')[0]
            return model_name
    except ValueError:
        pass
    return None
