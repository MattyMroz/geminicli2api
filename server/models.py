from typing import Any

from pydantic import BaseModel, ConfigDict

# --- OpenAI Models ---


class OpenAIChatMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]]
    reasoning_content: str | None = None


class OpenAIChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[OpenAIChatMessage]
    stream: bool = False
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop: str | list[str] | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    n: int | None = None
    seed: int | None = None
    response_format: dict[str, Any] | None = None
    reasoning_effort: str | None = None


class OpenAIChatCompletionChoice(BaseModel):
    index: int
    message: OpenAIChatMessage
    finish_reason: str | None = None


class OpenAIChatCompletionResponse(BaseModel):
    id: str
    object: str
    created: int
    model: str
    choices: list[OpenAIChatCompletionChoice]


class OpenAIDelta(BaseModel):
    content: str | None = None
    reasoning_content: str | None = None


class OpenAIChatCompletionStreamChoice(BaseModel):
    index: int
    delta: OpenAIDelta
    finish_reason: str | None = None


class OpenAIChatCompletionStreamResponse(BaseModel):
    id: str
    object: str
    created: int
    model: str
    choices: list[OpenAIChatCompletionStreamChoice]


# --- Gemini Models ---


class GeminiPart(BaseModel):
    text: str


class GeminiContent(BaseModel):
    role: str
    parts: list[GeminiPart]


class GeminiRequest(BaseModel):
    contents: list[GeminiContent]


class GeminiCandidate(BaseModel):
    content: GeminiContent
    finish_reason: str | None = None
    index: int


class GeminiResponse(BaseModel):
    candidates: list[GeminiCandidate]
