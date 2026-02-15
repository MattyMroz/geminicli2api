# geminicli2api — Przewodnik deweloperski

Jak budować aplikacje korzystające z geminicli2api jako backendu AI.

> **TL;DR**: geminicli2api to lokalny serwer proxy, który udostępnia modele Google Gemini przez standardowe API kompatybilne z OpenAI. Wystarczy wysłać request HTTP — tak samo jak do OpenAI, tylko na `localhost:8888`.

---

## Spis treści

- [Wymagania wstępne](#wymagania-wstępne)
- [Pierwsze kroki](#pierwsze-kroki)
- [API Endpoints — przegląd](#api-endpoints--przegląd)
- [Format OpenAI (zalecany)](#format-openai-zalecany)
  - [Chat Completions](#chat-completions)
  - [Streaming](#streaming)
  - [System prompt](#system-prompt)
  - [Obrazy (vision)](#obrazy-vision)
  - [Lista modeli](#lista-modeli)
- [Format natywny Gemini](#format-natywny-gemini)
- [Dostępne modele i warianty](#dostępne-modele-i-warianty)
- [Parametry generowania](#parametry-generowania)
- [Autentykacja](#autentykacja)
- [Gotowe przykłady w Pythonie](#gotowe-przykłady-w-pythonie)
  - [Minimalny klient (requests)](#minimalny-klient-requests)
  - [Klient async (httpx)](#klient-async-httpx)
  - [Streaming w Pythonie](#streaming-w-pythonie)
  - [Wysyłanie obrazów](#wysyłanie-obrazów)
  - [Równoległe requesty (concurrency)](#równoległe-requesty-concurrency)
- [Przykłady curl](#przykłady-curl)
- [Obsługa błędów](#obsługa-błędów)
- [Wzorce z translatora — co warto skopiować](#wzorce-z-translatora--co-warto-skopiować)
- [Budowanie własnej aplikacji — checklist](#budowanie-własnej-aplikacji--checklist)
- [Kompatybilność z bibliotekami OpenAI](#kompatybilność-z-bibliotekami-openai)
- [FAQ](#faq)

---

## Wymagania wstępne

Zanim zaczniesz budować aplikację, upewnij się że:

1. **Serwer proxy działa** — uruchom go w osobnym terminalu:
   ```bash
   uv run start.py
   ```

2. **Masz co najmniej 1 konto Google** dodane:
   ```bash
   uv run start.py --add-account   # lub: uv run start.py -a
   ```

3. **Serwer odpowiada** — sprawdź health check:
   ```bash
   curl http://127.0.0.1:8888/health
   ```
   Oczekiwana odpowiedź: `{"status": "healthy", "service": "geminicli2api", "accounts": 1}`

---

## Pierwsze kroki

Najszybszy sposób na pierwszy request:

```bash
curl http://127.0.0.1:8888/v1/chat/completions \
  -H "Authorization: Bearer 123456" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-flash",
    "messages": [{"role": "user", "content": "Powiedz cześć!"}]
  }'
```

To wszystko. Format jest identyczny jak OpenAI API.

---

## API Endpoints — przegląd

| Endpoint | Metoda | Opis |
|----------|--------|------|
| `/v1/chat/completions` | POST | Chat completions (format OpenAI) |
| `/v1/models` | GET | Lista modeli (format OpenAI) |
| `/v1beta/models` | GET | Lista modeli (format Gemini) |
| `/v1beta/models/{model}:generateContent` | POST | Generowanie (format Gemini) |
| `/v1beta/models/{model}:streamGenerateContent` | POST | Streaming (format Gemini) |
| `/health` | GET | Health check (bez autentykacji) |
| `/` | GET | Info o serwerze (bez autentykacji) |

**Rekomendacja**: Używaj formatu OpenAI (`/v1/chat/completions`) — jest prostszy i kompatybilny z wieloma bibliotekami.

---

## Format OpenAI (zalecany)

### Chat Completions

```
POST /v1/chat/completions
```

**Request body:**

```json
{
  "model": "gemini-2.5-flash",
  "messages": [
    {"role": "system", "content": "Jesteś pomocnym asystentem."},
    {"role": "user", "content": "Co to jest Python?"}
  ],
  "temperature": 0.7,
  "top_p": 0.95,
  "max_tokens": 8192,
  "stream": false
}
```

**Response body:**

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "gemini-2.5-flash",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Python to język programowania...",
        "reasoning_content": "..."
      },
      "finish_reason": "stop"
    }
  ]
}
```

> **Uwaga**: Pole `reasoning_content` zawiera "myślenie" modelu (jeśli model to obsługuje). Nie pojawi się dla modeli z sufiksem `-nothinking`.

---

### Streaming

Ustaw `"stream": true` — odpowiedź przychodzi jako Server-Sent Events (SSE):

```
POST /v1/chat/completions
Content-Type: application/json

{"model": "gemini-2.5-flash", "messages": [...], "stream": true}
```

**Odpowiedź SSE:**

```
data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","choices":[{"delta":{"content":"Py"}}]}

data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","choices":[{"delta":{"content":"thon"}}]}

data: {"id":"chatcmpl-abc","object":"chat.completion.chunk","choices":[{"delta":{"content":" to..."}}]}

data: [DONE]
```

---

### System prompt

System prompt przesyłaj jako wiadomość o roli `"system"` — **musi być pierwsza** na liście:

```json
{
  "messages": [
    {"role": "system", "content": "Odpowiadaj wyłącznie po polsku. Bądź zwięzły."},
    {"role": "user", "content": "What is machine learning?"}
  ]
}
```

---

### Obrazy (vision)

Modele Gemini obsługują multimodalne wejście. Obrazy przesyłaj jako base64 w formacie `data:` URI:

```json
{
  "model": "gemini-2.5-flash",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,iVBORw0KGgo..."
          }
        },
        {
          "type": "text",
          "text": "Co jest na tym obrazku?"
        }
      ]
    }
  ]
}
```

**Obsługiwane formaty**: PNG, JPEG, WebP, HEIC, HEIF

**Wskazówka**: `content` może być stringiem (tylko tekst) albo tablicą (tekst + obrazy).

---

### Lista modeli

```
GET /v1/models
```

Zwraca listę w formacie OpenAI:

```json
{
  "object": "list",
  "data": [
    {"id": "gemini-2.5-flash", "object": "model", "owned_by": "google"},
    {"id": "gemini-2.5-pro", "object": "model", "owned_by": "google"},
    ...
  ]
}
```

---

## Format natywny Gemini

Jeśli potrzebujesz pełnej kontroli nad API Gemini, możesz korzystać z endpointu natywnego:

```
POST /v1beta/models/gemini-2.5-flash:generateContent
```

```json
{
  "contents": [
    {
      "role": "user",
      "parts": [{"text": "Co to jest Python?"}]
    }
  ],
  "generationConfig": {
    "temperature": 0.7,
    "topP": 0.95,
    "maxOutputTokens": 8192,
    "thinkingConfig": {
      "thinkingBudget": 8192,
      "includeThoughts": true
    }
  }
}
```

**Streaming natywny:**
```
POST /v1beta/models/gemini-2.5-flash:streamGenerateContent
```

---

## Dostępne modele i warianty

### Modele bazowe

| Model | Opis | Max output |
|-------|------|------------|
| `gemini-2.0-flash` | Starszy, szybki | 8 192 |
| `gemini-2.5-flash` | Szybki, dobry do testów | 65 535 |
| `gemini-2.5-flash-lite` | Najszybszy, najlżejszy | 65 535 |
| `gemini-2.5-pro` | Najlepszy do złożonych zadań | 65 535 |
| `gemini-3-flash-preview` | Nowa generacja, preview | 65 535 |
| `gemini-3-pro-preview` | Najsilniejszy, preview | 65 535 |

### Warianty (sufiksy)

Każdy model bazowy (oprócz `gemini-2.0-flash` i `gemini-2.5-flash-lite`) jest dostępny w wariantach:

| Sufiks | Działanie | Kiedy używać |
|--------|-----------|--------------|
| *(brak)* | Domyślny tryb myślenia | Większość zastosowań |
| `-search` | Dodaje Google Search grounding | Pytania o aktualności, fakty |
| `-nothinking` | Wyłącza myślenie | Szybkie odpowiedzi, niski koszt |
| `-maxthinking` | Maksymalny budżet myślenia | Matematyka, coding, logika |

**Przykłady**: `gemini-2.5-pro-search`, `gemini-2.5-flash-nothinking`, `gemini-3-pro-preview-maxthinking`

### Który model wybrać?

| Scenariusz | Rekomendacja |
|-----------|--------------|
| Szybki prototyp | `gemini-2.5-flash-nothinking` |
| Tłumaczenia, pisanie | `gemini-2.5-pro` |
| Analiza kodu / matematyka | `gemini-2.5-pro-maxthinking` |
| Asystent z aktualnymi danymi | `gemini-2.5-flash-search` |
| Najszybsza odpowiedź | `gemini-2.5-flash-lite` |
| Najlepsza jakość (preview) | `gemini-3-pro-preview` |

Pełna lista: `uv run start.py --list-models` (skrót: `-l`)

---

## Parametry generowania

| Parametr | Typ | Domyślnie | Zakres | Opis |
|----------|-----|-----------|--------|------|
| `model` | string | *wymagany* | — | Nazwa modelu |
| `messages` | array | *wymagany* | — | Lista wiadomości |
| `stream` | bool | `false` | — | Streaming SSE |
| `temperature` | float | `1.0` | 0.0–2.0 | Losowość odpowiedzi (niższa = bardziej deterministyczna) |
| `top_p` | float | `0.95` | 0.0–1.0 | Nucleus sampling |
| `max_tokens` | int | *model default* | 1–65535 | Maks. tokenów w odpowiedzi |
| `stop` | string/array | `null` | — | Sekwencje stopu |
| `frequency_penalty` | float | `null` | — | Kara za częstotliwość |
| `presence_penalty` | float | `null` | — | Kara za obecność |
| `seed` | int | `null` | — | Seed dla powtarzalności |
| `response_format` | object | `null` | — | Format odpowiedzi (np. JSON) |
| `reasoning_effort` | string | `null` | — | Kontrola intensywności myślenia |

**Rekomendacje**:
- **Tłumaczenia**: `temperature: 0.3`, `top_p: 1.0`
- **Kreatywne pisanie**: `temperature: 1.0`, `top_p: 0.95`
- **Kodowanie**: `temperature: 0.2`, `max_tokens: 65536`
- **Streszczenia**: `temperature: 0.5`

---

## Autentykacja

Serwer akceptuje 4 sposoby autentykacji (użyj jednego):

| Metoda | Header / Parametr | Przykład |
|--------|-------------------|---------|
| Bearer token | `Authorization: Bearer <hasło>` | `Bearer 123456` |
| Basic auth | `Authorization: Basic <base64>` | `Basic dXNlcjoxMjM0NTY=` |
| Query param | `?key=<hasło>` | `?key=123456` |
| Header Gemini | `x-goog-api-key: <hasło>` | `x-goog-api-key: 123456` |

Domyślne hasło: `123456` (zmień w `.env` → `GEMINI_AUTH_PASSWORD`)

---

## Gotowe przykłady w Pythonie

### Minimalny klient (requests)

```python
"""Najprostszy możliwy klient — 10 linii."""
import requests

response = requests.post(
    "http://127.0.0.1:8888/v1/chat/completions",
    headers={"Authorization": "Bearer 123456"},
    json={
        "model": "gemini-2.5-flash",
        "messages": [{"role": "user", "content": "Powiedz cześć!"}],
    },
)

print(response.json()["choices"][0]["message"]["content"])
```

**Zależności**: `pip install requests`

---

### Klient async (httpx)

```python
"""Klient asynchroniczny — lepszy do współbieżności."""
import asyncio
import httpx

async def ask(prompt: str, model: str = "gemini-2.5-flash") -> str:
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8888",
        headers={"Authorization": "Bearer 123456"},
        timeout=300.0,
    ) as client:
        resp = await client.post("/v1/chat/completions", json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
        })
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

# Użycie
result = asyncio.run(ask("Napisz haiku o programowaniu"))
print(result)
```

**Zależności**: `pip install httpx`

---

### Streaming w Pythonie

```python
"""Streaming — odpowiedź token po tokenie."""
import httpx
import json

def stream_chat(prompt: str, model: str = "gemini-2.5-flash"):
    with httpx.Client(
        base_url="http://127.0.0.1:8888",
        headers={"Authorization": "Bearer 123456"},
        timeout=300.0,
    ) as client:
        with client.stream("POST", "/v1/chat/completions", json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }) as response:
            for line in response.iter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    chunk = json.loads(line[6:])
                    content = chunk["choices"][0]["delta"].get("content", "")
                    if content:
                        print(content, end="", flush=True)
    print()  # newline

stream_chat("Wyjaśnij czym jest API w 3 zdaniach")
```

**Zależności**: `pip install httpx`

---

### Wysyłanie obrazów

```python
"""Analiza obrazu — vision."""
import base64
import httpx

def analyze_image(image_path: str, prompt: str = "Co widzisz na tym obrazku?") -> str:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    # Wykryj MIME type
    ext = image_path.lower().split(".")[-1]
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "webp": "image/webp"}.get(ext, "image/png")

    resp = httpx.post(
        "http://127.0.0.1:8888/v1/chat/completions",
        headers={"Authorization": "Bearer 123456"},
        json={
            "model": "gemini-2.5-flash",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
        },
        timeout=300.0,
    )
    return resp.json()["choices"][0]["message"]["content"]

# Użycie
print(analyze_image("screenshot.png", "Opisz co jest na tym zrzucie ekranu"))
```

**Zależności**: `pip install httpx`

---

### Równoległe requesty (concurrency)

```python
"""Wysyłanie wielu requestów jednocześnie z limitem współbieżności."""
import asyncio
import httpx

CONCURRENT_LIMIT = 10  # max równoległych requestów

async def translate_batch(texts: list[str]) -> list[str]:
    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)

    async def _translate_one(text: str, client: httpx.AsyncClient) -> str:
        async with semaphore:
            resp = await client.post("/v1/chat/completions", json={
                "model": "gemini-2.5-flash",
                "messages": [
                    {"role": "system", "content": "Przetłumacz na polski. Zwróć tylko tłumaczenie."},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.3,
            })
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8888",
        headers={"Authorization": "Bearer 123456"},
        timeout=300.0,
    ) as client:
        tasks = [_translate_one(t, client) for t in texts]
        return await asyncio.gather(*tasks)

# Użycie
texts = ["Hello world", "Good morning", "How are you?", "See you later"]
results = asyncio.run(translate_batch(texts))
for original, translated in zip(texts, results):
    print(f"{original} → {translated}")
```

**Zależności**: `pip install httpx`

---

## Przykłady curl

```bash
# Proste pytanie
curl -s http://127.0.0.1:8888/v1/chat/completions \
  -H "Authorization: Bearer 123456" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-2.5-flash","messages":[{"role":"user","content":"Cześć!"}]}' \
  | python -m json.tool

# Z system promptem
curl -s http://127.0.0.1:8888/v1/chat/completions \
  -H "Authorization: Bearer 123456" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-pro",
    "messages": [
      {"role": "system", "content": "Odpowiadaj w formie haiku."},
      {"role": "user", "content": "Programowanie"}
    ],
    "temperature": 1.0
  }'

# Streaming
curl -N http://127.0.0.1:8888/v1/chat/completions \
  -H "Authorization: Bearer 123456" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-2.5-flash","messages":[{"role":"user","content":"Opowiedz historię"}],"stream":true}'

# Health check
curl http://127.0.0.1:8888/health

# Lista modeli (format OpenAI)
curl -s http://127.0.0.1:8888/v1/models -H "Authorization: Bearer 123456" | python -m json.tool

# Lista modeli (format Gemini)
curl -s http://127.0.0.1:8888/v1beta/models -H "x-goog-api-key: 123456" | python -m json.tool

# Natywny Gemini request
curl -s http://127.0.0.1:8888/v1beta/models/gemini-2.5-flash:generateContent \
  -H "x-goog-api-key: 123456" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [{"role": "user", "parts": [{"text": "Cześć!"}]}]
  }'
```

---

## Obsługa błędów

Serwer zwraca błędy w formacie OpenAI:

```json
{
  "error": {
    "message": "Opis błędu",
    "type": "api_error",
    "code": 500
  }
}
```

### Kody błędów

| Kod | Znaczenie | Co robić |
|-----|-----------|----------|
| 400 | Nieprawidłowy request | Sprawdź format JSON i wymagane pola |
| 401 | Brak/złe hasło | Dodaj header `Authorization` z poprawnym hasłem |
| 403 | Konto odrzucone | Serwer automatycznie próbuje inne konto |
| 404 | Nieznany model/endpoint | Sprawdź nazwę modelu w `GET /v1/models` |
| 500 | Błąd wewnętrzny | Sprawdź logi serwera, spróbuj ponownie |
| 502 | Brak połączenia z Google | Sprawdź internet |
| 504 | Timeout | Model potrzebuje więcej czasu, zwiększ timeout |

### Wzorzec retry z exponential backoff

```python
import asyncio
import httpx

MAX_RETRIES = 5
INITIAL_BACKOFF = 1.0
MAX_BACKOFF = 60.0

async def robust_request(client: httpx.AsyncClient, payload: dict) -> dict:
    """Request z automatycznym retry i exponential backoff."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.post("/v1/chat/completions", json=payload)

            if resp.status_code == 200:
                return resp.json()

            # Retry na 429 (rate limit) i 5xx (server error)
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = min(INITIAL_BACKOFF * (2 ** attempt), MAX_BACKOFF)
                print(f"Błąd {resp.status_code}, retry za {wait:.1f}s...")
                await asyncio.sleep(wait)
                continue

            # Błędy klienta (400, 401, 404) — nie ponownie próbuj
            resp.raise_for_status()

        except httpx.ConnectError:
            print("Serwer proxy niedostępny. Czy jest uruchomiony?")
            await asyncio.sleep(INITIAL_BACKOFF * (2 ** attempt))
        except httpx.ReadTimeout:
            print("Timeout — model potrzebuje więcej czasu")
            await asyncio.sleep(INITIAL_BACKOFF)

    raise Exception(f"Nie udało się po {MAX_RETRIES} próbach")
```

---

## Wzorce z translatora — co warto skopiować

Translator (`apps/gemini_translator/`) to gotowy przykład aplikacji zbudowanej na geminicli2api. Oto kluczowe wzorce:

### 1. Klasa klienta API (api_client.py)

Translator ma dedykowaną klasę `GeminiAPIClient` z:
- **Lazy initialization** klienta HTTP (tworzy się przy pierwszym użyciu)
- **Health check** przed rozpoczęciem pracy
- **Osobne metody** dla tekstu (`generate`) i obrazów (`generate_with_image`)
- **Obsługa różnych wyjątków** httpx (ConnectError, ReadTimeout, ConnectTimeout)

**Skopiuj ten wzorzec** jeśli budujesz coś większego niż skrypt jednorazowy.

### 2. Semaphore do limitowania współbieżności

```python
self.semaphore = asyncio.Semaphore(concurrent_requests)

async def do_work(self):
    async with self.semaphore:  # max N równoległych operacji
        result = await self.api_client.generate(...)
```

Serwer proxy obsługuje wiele requestów jednocześnie. Jeśli masz 3 konta Google, możesz spokojnie wysyłać 20+ równoległych requestów.

### 3. Exponential backoff na błędy

```python
MAX_RETRIES = 100
INITIAL_BACKOFF = 1.0
MAX_BACKOFF = 60.0

wait_time = min(INITIAL_BACKOFF * (2 ** attempt), MAX_BACKOFF)
await asyncio.sleep(wait_time)
```

### 4. Write lock na współdzielone pliki

```python
self.write_lock = asyncio.Lock()

async with self.write_lock:
    subs.save(output_path, encoding='utf-8')
```

Jeśli wiele zadań pisze do tego samego pliku, użyj locka.

### 5. Timeout 300 sekund

Modele Gemini (szczególnie Pro z myśleniem) mogą generować odpowiedzi nawet kilka minut. Domyślne timeouty bibliotek HTTP (5–30 sek.) są **za krótkie**.

```python
timeout = httpx.Timeout(300.0, connect=30.0)
```

---

## Budowanie własnej aplikacji — checklist

### Zależności do zainstalowania

```bash
# Minimalne (sync)
pip install requests

# Zalecane (async + streaming)
pip install httpx

# Jeśli przetwarzasz napisy SRT
pip install pysrt

# Jeśli chcesz śledzenie ogólne plików
pip install natsort

# Ładne logowanie w terminalu
pip install rich
```

### Szablon nowej aplikacji

```
my_app/
├── main.py              ← Punkt wejścia
├── config.py            ← Konfiguracja (URL proxy, model, parametry)
├── api_client.py        ← Klient HTTP (skopiuj z translatora lub napisz swój)
├── requirements.txt     ← httpx, inne zależności
└── README.md
```

### Minimalny `config.py`

```python
from dataclasses import dataclass

@dataclass
class AppConfig:
    # Proxy
    proxy_url: str = "http://127.0.0.1:8888"
    api_key: str = "123456"

    # Model
    model: str = "gemini-2.5-flash"
    temperature: float = 0.7
    max_tokens: int = 8192

    # App
    concurrent_requests: int = 5
    timeout: float = 300.0
```

### Minimalny `api_client.py`

```python
import httpx
from typing import Optional

class AIClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 300.0):
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout, connect=30.0),
        )

    async def ask(
        self,
        prompt: str,
        model: str = "gemini-2.5-flash",
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = await self.client.post("/v1/chat/completions", json={
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    async def close(self):
        await self.client.aclose()
```

---

## Kompatybilność z bibliotekami OpenAI

Ponieważ geminicli2api implementuje format OpenAI, możesz użyć oficjalnej biblioteki:

### openai Python SDK

```python
from openai import OpenAI

client = OpenAI(
    api_key="123456",
    base_url="http://127.0.0.1:8888/v1",
)

response = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=[{"role": "user", "content": "Cześć!"}],
)

print(response.choices[0].message.content)
```

**Zależności**: `pip install openai`

### openai Python SDK (async)

```python
from openai import AsyncOpenAI
import asyncio

client = AsyncOpenAI(
    api_key="123456",
    base_url="http://127.0.0.1:8888/v1",
)

async def main():
    response = await client.chat.completions.create(
        model="gemini-2.5-pro",
        messages=[{"role": "user", "content": "Cześć!"}],
    )
    print(response.choices[0].message.content)

asyncio.run(main())
```

### openai SDK streaming

```python
from openai import OpenAI

client = OpenAI(api_key="123456", base_url="http://127.0.0.1:8888/v1")

stream = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=[{"role": "user", "content": "Napisz opowiadanie"}],
    stream=True,
)

for chunk in stream:
    content = chunk.choices[0].delta.content
    if content:
        print(content, end="", flush=True)
```

### LangChain

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gemini-2.5-flash",
    api_key="123456",
    base_url="http://127.0.0.1:8888/v1",
    temperature=0.7,
)

response = llm.invoke("Czym jest sztuczna inteligencja?")
print(response.content)
```

**Zależności**: `pip install langchain-openai`

---

## FAQ

### Ile requestów mogę wysyłać jednocześnie?

Serwer obsługuje dowolną liczbę requestów — jest asynchroniczny (FastAPI + uvicorn). Limitujący jest rate limit Google. Z 3 kontami Google możesz spokojnie wysyłać 20+ równoległych requestów.

### Czy muszę uruchamiać serwer proxy osobno?

Tak, serwer musi działać w tle (`uv run start.py`). **Wyjątek**: Translator ma opcję `auto_start_server`, która automatycznie startuje serwer — możesz zaimplementować coś podobnego w swojej aplikacji. Możesz też szybko uruchomić translator skrótem: `uv run start.py -t`.

### Jak zmienić port serwera?

Edytuj `.env`:
```
PORT=9999
```
I ustaw `proxy_url` w swojej aplikacji na `http://127.0.0.1:9999`.

### Czym się różni format OpenAI od natywnego Gemini?

| Cecha | OpenAI format | Natywny Gemini |
|-------|---------------|----------------|
| Endpoint | `/v1/chat/completions` | `/v1beta/models/{model}:generateContent` |
| Wiadomości | `messages: [{role, content}]` | `contents: [{role, parts}]` |
| System prompt | `role: "system"` | Osobne pole `systemInstruction` |
| Odpowiedź | `choices[0].message.content` | `candidates[0].content.parts[0].text` |
| Kompatybilność | OpenAI SDK, LangChain, etc. | Tylko natywne zapytania |

**Rekomendacja**: Używaj formatu OpenAI — jest prostszy i kompatybilny z ekosystemem.

### Czy serwer działa jak zwykłe API OpenAI?

Tak, w 95% przypadków. Główne różnice:
- Dodatkowe pole `reasoning_content` (myślenie modelu)
- Inne nazwy modeli (`gemini-*` zamiast `gpt-*`)
- Brak kilku rzadkich parametrów (np. `logprobs`)

### Jak sprawdzić ile mam kont?

```bash
curl http://127.0.0.1:8888/health
# Odpowiedź: {"status": "healthy", "accounts": 3}
```

Albo z CLI:
```bash
curl http://127.0.0.1:8888/
```
