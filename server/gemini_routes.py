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
            content=json.dumps(
                {"error": {"message": f"Failed to list models: {str(e)}", "code": 500}}),
            status_code=500,
            media_type="application/json"
        )


@router.api_route("/v1beta/models/{model_name}:{action}", methods=["GET", "POST"])
@router.api_route("/v1beta/models/{model_name}", methods=["GET", "POST"])
@router.api_route("/v1/models/{model_name}:{action}", methods=["GET", "POST"])
@router.api_route("/v1/models/{model_name}", methods=["GET", "POST"])
async def gemini_proxy(
    request: Request,
    model_name: str,
    action: str = "generateContent",
    username: str = Depends(authenticate_user),
):
    """Native Gemini API proxy endpoint — handles Gemini model API calls."""
    try:
        post_data = await request.body()
        is_streaming = action.lower().startswith("stream")

        logging.info(
            f"Gemini proxy request: model={model_name}, action={action}, stream={is_streaming}")

        try:
            if post_data:
                incoming_request = json.loads(post_data)
            else:
                incoming_request = {}
        except json.JSONDecodeError:
            return Response(
                content=json.dumps(
                    {"error": {"message": "Invalid JSON in request body", "code": 400}}),
                status_code=400,
                media_type="application/json"
            )

        gemini_payload = build_gemini_payload_from_native(
            incoming_request, model_name)
        response = await send_gemini_request(gemini_payload, is_streaming=is_streaming)

        if hasattr(response, 'status_code'):
            if response.status_code != 200:
                logging.error(
                    f"Gemini API returned error: status={response.status_code}")
            else:
                logging.info(
                    f"Successfully processed Gemini request for model: {model_name}")

        return response

    except Exception as e:
        logging.error(f"Gemini proxy error: {str(e)}")
        return Response(
            content=json.dumps(
                {"error": {"message": f"Proxy error: {str(e)}", "code": 500}}),
            status_code=500,
            media_type="application/json"
        )
