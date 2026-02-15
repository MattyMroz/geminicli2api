"""
OpenAI Format Transformers - Handles conversion between OpenAI and Gemini API formats.
"""
import json
import time
import uuid
import re
from typing import Dict, Any

from server.models import OpenAIChatCompletionRequest, OpenAIChatCompletionResponse
from server.config import (
    DEFAULT_SAFETY_SETTINGS,
    is_search_model,
    get_base_model_name,
    get_thinking_budget,
    should_include_thoughts,
    is_nothinking_model,
    is_maxthinking_model,
    _has_thinking_support,
)


def openai_request_to_gemini(openai_request: OpenAIChatCompletionRequest) -> Dict[str, Any]:
    """Transform an OpenAI chat completion request to Gemini format."""
    contents = []
    system_parts = []

    for message in openai_request.messages:
        role = message.role

        # Extract system messages into systemInstruction
        if role == "system":
            if isinstance(message.content, list):
                for part in message.content:
                    if part.get("type") == "text":
                        system_parts.append({"text": part.get("text", "")})
            else:
                system_parts.append({"text": message.content or ""})
            continue

        if role == "assistant":
            role = "model"

        if isinstance(message.content, list):
            parts = []
            for part in message.content:
                if part.get("type") == "text":
                    text_value = part.get("text", "") or ""
                    pattern = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')
                    matches = list(pattern.finditer(text_value))
                    if not matches:
                        parts.append({"text": text_value})
                    else:
                        last_idx = 0
                        for m in matches:
                            url = m.group(1).strip().strip('"').strip("'")
                            if m.start() > last_idx:
                                before = text_value[last_idx:m.start()]
                                if before:
                                    parts.append({"text": before})
                            if url.startswith("data:"):
                                try:
                                    header, base64_data = url.split(",", 1)
                                    mime_type = ""
                                    if ":" in header:
                                        mime_type = header.split(
                                            ":", 1)[1].split(";", 1)[0] or ""
                                    if mime_type.startswith("image/"):
                                        parts.append({
                                            "inlineData": {"mimeType": mime_type, "data": base64_data}
                                        })
                                    else:
                                        parts.append(
                                            {"text": text_value[m.start():m.end()]})
                                except Exception:
                                    parts.append(
                                        {"text": text_value[m.start():m.end()]})
                            else:
                                parts.append(
                                    {"text": text_value[m.start():m.end()]})
                            last_idx = m.end()
                        if last_idx < len(text_value):
                            tail = text_value[last_idx:]
                            if tail:
                                parts.append({"text": tail})
                elif part.get("type") == "image_url":
                    image_url = part.get("image_url", {}).get("url")
                    if image_url:
                        try:
                            mime_type, base64_data = image_url.split(";")
                            _, mime_type = mime_type.split(":")
                            _, base64_data = base64_data.split(",")
                            parts.append({
                                "inlineData": {"mimeType": mime_type, "data": base64_data}
                            })
                        except ValueError:
                            continue
            contents.append({"role": role, "parts": parts})
        else:
            text = message.content or ""
            parts = []
            pattern = re.compile(r'!\[[^\]]*\]\(([^)]+)\)')
            last_idx = 0
            for m in pattern.finditer(text):
                url = m.group(1).strip().strip('"').strip("'")
                if m.start() > last_idx:
                    before = text[last_idx:m.start()]
                    if before:
                        parts.append({"text": before})
                if url.startswith("data:"):
                    try:
                        header, base64_data = url.split(",", 1)
                        mime_type = ""
                        if ":" in header:
                            mime_type = header.split(
                                ":", 1)[1].split(";", 1)[0] or ""
                        if mime_type.startswith("image/"):
                            parts.append({
                                "inlineData": {"mimeType": mime_type, "data": base64_data}
                            })
                        else:
                            parts.append({"text": text[m.start():m.end()]})
                    except Exception:
                        parts.append({"text": text[m.start():m.end()]})
                else:
                    parts.append({"text": text[m.start():m.end()]})
                last_idx = m.end()
            if last_idx < len(text):
                tail = text[last_idx:]
                if tail:
                    parts.append({"text": tail})
            contents.append(
                {"role": role, "parts": parts if parts else [{"text": text}]})

    generation_config = {}
    if openai_request.temperature is not None:
        generation_config["temperature"] = openai_request.temperature
    if openai_request.top_p is not None:
        generation_config["topP"] = openai_request.top_p
    if openai_request.max_tokens is not None:
        generation_config["maxOutputTokens"] = openai_request.max_tokens
    if openai_request.stop is not None:
        if isinstance(openai_request.stop, str):
            generation_config["stopSequences"] = [openai_request.stop]
        elif isinstance(openai_request.stop, list):
            generation_config["stopSequences"] = openai_request.stop
    if openai_request.frequency_penalty is not None:
        generation_config["frequencyPenalty"] = openai_request.frequency_penalty
    if openai_request.presence_penalty is not None:
        generation_config["presencePenalty"] = openai_request.presence_penalty
    if openai_request.n is not None:
        generation_config["candidateCount"] = openai_request.n
    if openai_request.seed is not None:
        generation_config["seed"] = openai_request.seed
    if openai_request.response_format is not None:
        if openai_request.response_format.get("type") == "json_object":
            generation_config["responseMimeType"] = "application/json"

    request_payload = {
        "contents": contents,
        "generationConfig": generation_config,
        "safetySettings": DEFAULT_SAFETY_SETTINGS,
        "model": get_base_model_name(openai_request.model)
    }

    # Add systemInstruction if system messages were present
    if system_parts:
        request_payload["systemInstruction"] = {
            "role": "user",
            "parts": system_parts
        }

    if is_search_model(openai_request.model):
        request_payload["tools"] = [{"googleSearch": {}}]

    if _has_thinking_support(openai_request.model):
        thinking_budget = None

        if is_nothinking_model(openai_request.model) or is_maxthinking_model(openai_request.model):
            thinking_budget = get_thinking_budget(openai_request.model)
        else:
            reasoning_effort = getattr(
                openai_request, 'reasoning_effort', None)
            if reasoning_effort:
                base_model = get_base_model_name(openai_request.model)
                if reasoning_effort == "minimal":
                    if "gemini-2.5-flash" in base_model:
                        thinking_budget = 0
                    elif "gemini-2.5-pro" in base_model or "gemini-3-pro" in base_model:
                        thinking_budget = 128
                    elif "gemini-3-flash" in base_model:
                        thinking_budget = 0
                elif reasoning_effort == "low":
                    thinking_budget = 1000
                elif reasoning_effort == "medium":
                    thinking_budget = -1
                elif reasoning_effort == "high":
                    if "gemini-2.5-flash" in base_model:
                        thinking_budget = 24576
                    elif "gemini-2.5-pro" in base_model:
                        thinking_budget = 32768
                    elif "gemini-3-pro" in base_model:
                        thinking_budget = 45000
                    elif "gemini-3-flash" in base_model:
                        thinking_budget = 24576
            else:
                thinking_budget = get_thinking_budget(openai_request.model)

        if thinking_budget is not None:
            request_payload["generationConfig"]["thinkingConfig"] = {
                "thinkingBudget": thinking_budget,
                "includeThoughts": should_include_thoughts(openai_request.model)
            }

    return request_payload


def gemini_response_to_openai(gemini_response: Dict[str, Any], model: str) -> Dict[str, Any]:
    """Transform a Gemini API response to OpenAI chat completion format."""
    choices = []

    for candidate in gemini_response.get("candidates", []):
        role = candidate.get("content", {}).get("role", "assistant")
        if role == "model":
            role = "assistant"

        parts = candidate.get("content", {}).get("parts", [])
        content_parts = []
        reasoning_content = ""

        for part in parts:
            if part.get("text") is not None:
                if part.get("thought", False):
                    reasoning_content += part.get("text", "")
                else:
                    content_parts.append(part.get("text", ""))
                continue

            inline = part.get("inlineData")
            if inline and inline.get("data"):
                mime = inline.get("mimeType") or "image/png"
                if isinstance(mime, str) and mime.startswith("image/"):
                    data_b64 = inline.get("data")
                    content_parts.append(
                        f"![image](data:{mime};base64,{data_b64})")
                continue

        content = "\n\n".join([p for p in content_parts if p is not None])

        message = {"role": role, "content": content}
        if reasoning_content:
            message["reasoning_content"] = reasoning_content

        choices.append({
            "index": candidate.get("index", 0),
            "message": message,
            "finish_reason": _map_finish_reason(candidate.get("finishReason")),
        })

    return {
        "id": str(uuid.uuid4()),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": choices,
    }


def gemini_stream_chunk_to_openai(gemini_chunk: Dict[str, Any], model: str, response_id: str) -> Dict[str, Any]:
    """Transform a Gemini streaming response chunk to OpenAI streaming format."""
    choices = []

    for candidate in gemini_chunk.get("candidates", []):
        role = candidate.get("content", {}).get("role", "assistant")
        if role == "model":
            role = "assistant"

        parts = candidate.get("content", {}).get("parts", [])
        content_parts = []
        reasoning_content = ""

        for part in parts:
            if part.get("text") is not None:
                if part.get("thought", False):
                    reasoning_content += part.get("text", "")
                else:
                    content_parts.append(part.get("text", ""))
                continue

            inline = part.get("inlineData")
            if inline and inline.get("data"):
                mime = inline.get("mimeType") or "image/png"
                if isinstance(mime, str) and mime.startswith("image/"):
                    data_b64 = inline.get("data")
                    content_parts.append(
                        f"![image](data:{mime};base64,{data_b64})")
                continue

        content = "\n\n".join([p for p in content_parts if p is not None])

        delta = {}
        if content:
            delta["content"] = content
        if reasoning_content:
            delta["reasoning_content"] = reasoning_content

        choices.append({
            "index": candidate.get("index", 0),
            "delta": delta,
            "finish_reason": _map_finish_reason(candidate.get("finishReason")),
        })

    return {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": choices,
    }


def _map_finish_reason(gemini_reason: str) -> str:
    """Map Gemini finish reasons to OpenAI finish reasons."""
    if gemini_reason == "STOP":
        return "stop"
    elif gemini_reason == "MAX_TOKENS":
        return "length"
    elif gemini_reason in ["SAFETY", "RECITATION"]:
        return "content_filter"
    else:
        return None
