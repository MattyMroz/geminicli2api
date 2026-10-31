"""
API Client — httpx-based client for communicating with the geminicli2api proxy server.

Replaces direct google.generativeai SDK calls with HTTP requests to our local proxy.
"""

import logging
import os
from typing import ClassVar

import httpx


class GeminiAPIClient:
    """HTTP client for the geminicli2api proxy server."""

    def __init__(self, base_url: str = "http://127.0.0.1:8888", api_key: str = "123456", timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(self.timeout, connect=30.0),
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def health_check(self) -> bool:
        """Check if the proxy server is running."""
        try:
            client = await self._get_client()
            resp = await client.get("/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def generate(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.3,
        top_p: float = 1.0,
        max_tokens: int = 65536,
        system_prompt: str | None = None,
        response_format: dict | None = None,
    ) -> str:
        """
        Send a chat completion request to the proxy server.
        Returns the text content of the response.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if response_format:
            payload["response_format"] = response_format

        client = await self._get_client()

        try:
            resp = await client.post("/v1/chat/completions", json=payload)
        except httpx.ConnectError:
            raise Exception("Cannot connect to proxy server. Is it running?")
        except httpx.ReadTimeout:
            raise Exception("Proxy server read timeout — model may need more time")
        except httpx.ConnectTimeout:
            raise Exception("Proxy server connection timeout")
        except httpx.HTTPError as e:
            raise Exception(f"HTTP error: {e}")

        if resp.status_code != 200:
            error_text = resp.text[:500]
            logging.error(f"API error {resp.status_code}: {error_text}")
            raise Exception(f"API error {resp.status_code}: {error_text}")

        data = resp.json()

        # Extract text from OpenAI-format response
        choices = data.get("choices", [])
        if not choices:
            raise Exception("No choices in API response")

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise Exception("Empty content in API response")

        return content.strip()

    async def generate_with_image(
        self,
        model: str,
        prompt: str,
        image_data: bytes,
        mime_type: str = "image/png",
        temperature: float = 0.3,
        top_p: float = 1.0,
        max_tokens: int = 65536,
    ) -> str:
        """Send a chat completion request with an image."""
        import base64

        b64_data = base64.b64encode(image_data).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{b64_data}"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": False,
        }

        client = await self._get_client()

        try:
            resp = await client.post("/v1/chat/completions", json=payload)
        except httpx.ConnectError:
            raise Exception("Cannot connect to proxy server. Is it running?")
        except httpx.ReadTimeout:
            raise Exception("Proxy server read timeout — model may need more time")
        except httpx.ConnectTimeout:
            raise Exception("Proxy server connection timeout")
        except httpx.HTTPError as e:
            raise Exception(f"HTTP error: {e}")

        if resp.status_code != 200:
            error_text = resp.text[:500]
            logging.error(f"API error {resp.status_code}: {error_text}")
            raise Exception(f"API error {resp.status_code}: {error_text}")

        data = resp.json()
        choices = data.get("choices", [])
        if not choices:
            raise Exception("No choices in API response")

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            raise Exception("Empty content in API response")

        return content.strip()


class FoundryClient:
    """Direct client for the Palantir Foundry LLM proxy (no local server, no CLI).

    Same `generate` contract as GeminiAPIClient. The model is given as
    "<provider>/<model>", e.g. "foundry-google/gemini-3.8-flash",
    "foundry-anthropic/claude-opus-5-5", "foundry/gpt-6-sol" or "foundry-xai/grok-4.7".
    The token is read from `token_file` (the one opencode uses), else FOUNDRY_API_TOKEN.
    """

    ROUTES: ClassVar[dict[str, str]] = {
        "foundry-google": "/api/v2/llm/proxy/google/v1",
        "foundry-anthropic": "/api/v2/llm/proxy/anthropic/v1",
        "foundry": "/api/v2/llm/proxy/openai/v1",
        "foundry-xai": "/api/v2/llm/proxy/xai/v1",
    }

    def __init__(self, base_url: str, token_file: str = "", timeout: float = 900.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        token = ""
        if token_file and os.path.isfile(token_file):
            with open(token_file, encoding="utf-8") as f:
                token = f.read().strip()
        token = token or os.environ.get("FOUNDRY_API_TOKEN", "").strip()
        if not token:
            raise RuntimeError(f"No Foundry token: {token_file} missing and FOUNDRY_API_TOKEN not set")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self._headers,
                timeout=httpx.Timeout(self.timeout, connect=30.0),
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def generate(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.3,
        top_p: float = 1.0,
        max_tokens: int = 65536,
        system_prompt: str | None = None,
        response_format: dict | None = None,
    ) -> str:
        provider, _, model_id = model.partition("/")
        if provider not in self.ROUTES or not model_id:
            raise ValueError(f"Unsupported Foundry model: {model}")
        base = f"{self.base_url}{self.ROUTES[provider]}"

        if provider == "foundry-google":
            url = f"{base}/models/{model_id}:generateContent"
            generation = {"temperature": temperature, "topP": top_p, "maxOutputTokens": max_tokens}
            if response_format:
                generation["responseMimeType"] = "application/json"
            body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": generation}
            if system_prompt:
                body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
            headers = None
        elif provider == "foundry-anthropic":
            url = f"{base}/messages"
            # Recent Claude models reject sampling parameters (temperature is deprecated)
            body = {"model": model_id, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
            if system_prompt:
                body["system"] = system_prompt
            headers = {"anthropic-version": "2023-06-01"}
        else:
            url = f"{base}/responses"
            messages = [{"role": "user", "content": prompt}]
            if system_prompt:
                messages.insert(0, {"role": "system", "content": system_prompt})
            body = {"model": model_id, "input": messages, "max_output_tokens": max_tokens, "store": False}
            headers = None

        client = await self._get_client()
        try:
            resp = await client.post(url, json=body, headers=headers)
        except httpx.HTTPError as e:
            raise Exception(f"Foundry HTTP error ({model}): {e!r}")
        if resp.status_code != 200:
            raise Exception(f"Foundry API error {resp.status_code} ({model}): {resp.text[:500]}")
        data = resp.json()

        if provider == "foundry-google":
            candidates = data.get("candidates") or []
            if not candidates:
                raise Exception(f"No candidates in Foundry response ({model}): {str(data)[:300]}")
            candidate = candidates[0]
            parts = candidate.get("content", {}).get("parts", [])
            content = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            finish = candidate.get("finishReason")
            truncated = finish == "MAX_TOKENS"
        elif provider == "foundry-anthropic":
            content = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            finish = data.get("stop_reason")
            truncated = finish == "max_tokens"
        else:
            content = "".join(
                c.get("text", "")
                for item in data.get("output", [])
                if item.get("type") == "message"
                for c in item.get("content", [])
                if c.get("type") == "output_text"
            )
            finish = data.get("status")
            truncated = finish == "incomplete"

        if truncated:
            raise Exception(f"Response truncated by output limit ({model}, {finish})")
        if not content.strip():
            raise Exception(f"Empty Foundry response ({model}, {finish})")
        return content.strip()
