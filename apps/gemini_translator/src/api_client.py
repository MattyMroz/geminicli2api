"""
API Client — httpx-based client for communicating with the geminicli2api proxy server.

Replaces direct google.generativeai SDK calls with HTTP requests to our local proxy.
"""
import httpx
import logging
from typing import Optional


class GeminiAPIClient:
    """HTTP client for the geminicli2api proxy server."""

    def __init__(self, base_url: str = "http://127.0.0.1:8888", api_key: str = "123456", timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

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
        system_prompt: Optional[str] = None,
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

        messages = [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_uri}},
                {"type": "text", "text": prompt},
            ]
        }]

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
