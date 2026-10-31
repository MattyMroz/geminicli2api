# 🧠 BRAINSTORM — geminicli2api v2.0

# Kompleksowa analiza projektu, architektura, plany rozwoju

# Data: 2026-02-15

# Autor: AI Assistant (Copilot)

______________________________________________________________________

## SPIS TREŚCI

01. [PROJEKT — WIZJA I MISJA](#1-projekt--wizja-i-misja)
02. [ANALIZA OBECNEGO STANU](#2-analiza-obecnego-stanu)
03. [ARCHITEKTURA SYSTEMU](#3-architektura-systemu)
04. [SERWER PROXY — DEEP DIVE](#4-serwer-proxy--deep-dive)
05. [TRANSLATOR — DEEP DIVE](#5-translator--deep-dive)
06. [SYSTEM AUTENTYKACJI I KONT](#6-system-autentykacji-i-kont)
07. [MODELE I ICH WARIANTY](#7-modele-i-ich-warianty)
08. [OBSŁUGA BŁĘDÓW I ODPORNOŚĆ](#8-obs%C5%82uga-b%C5%82%C4%99d%C3%B3w-i-odporno%C5%9B%C4%87)
09. [WYDAJNOŚĆ I WSPÓŁBIEŻNOŚĆ](#9-wydajno%C5%9B%C4%87-i-wsp%C3%B3%C5%82bie%C5%BCno%C5%9B%C4%87)
10. [BEZPIECZEŃSTWO](#10-bezpiecze%C5%84stwo)
11. [TESTOWANIE](#11-testowanie)
12. [ZNANE PROBLEMY I TECH DEBT](#12-znane-problemy-i-tech-debt)
13. [ROADMAP — KRÓTKOTERMINOWA (v2.1)](#13-roadmap--kr%C3%B3tkoterminowa-v21)
14. [ROADMAP — ŚREDNIOTERMINOWA (v3.0)](#14-roadmap--%C5%9Brednioterminowa-v30)
15. [ROADMAP — DŁUGOTERMINOWA (v4.0+)](#15-roadmap--d%C5%82ugoterminowa-v40)
16. [POMYSŁY NA NOWE FUNKCJE](#16-pomys%C5%82y-na-nowe-funkcje)
17. [ALTERNATYWNE PODEJŚCIA](#17-alternatywne-podej%C5%9Bcia)
18. [PORÓWNANIE Z INNYMI PROJEKTAMI](#18-por%C3%B3wnanie-z-innymi-projektami)
19. [DEPLOYMENT I HOSTING](#19-deployment-i-hosting)
20. [DOKUMENTACJA I DX](#20-dokumentacja-i-dx)
21. [PODSUMOWANIE I WNIOSKI](#21-podsumowanie-i-wnioski)

______________________________________________________________________

## 1. PROJEKT — WIZJA I MISJA

### 1.1 Co to jest geminicli2api?

Darmowy, lokalny proxy serwer, który udostępnia Google Gemini API
za pośrednictwem standardowych endpointów (OpenAI-compatible + native Gemini).
Zamiast kluczy API, wykorzystuje OAuth credentials z kont Google,
co umożliwia darmowe korzystanie z najnowszych modeli Gemini.

### 1.2 Dlaczego to istnieje?

- **Koszt**: Google Gemini CLI/IDE daje darmowy dostęp do modeli,
  ale nie udostępnia API — ten projekt to bridge.
- **Kompatybilność**: Wiele narzędzi (SillyTavern, Open WebUI, Aider)
  oczekuje API w formacie OpenAI — proxy to konwertuje.
- **Multi-account**: Jeden serwer, wiele kont Google → round-robin
  → obejście rate limitów.

### 1.3 Dla kogo?

- Deweloperzy chcący testować Gemini bez płacenia
- Tłumacze potrzebujący batch translation
- Hobbystyczni użytkownicy AI chatbotów
- Twórcy treści szukający darmowego AI

### 1.4 Kluczowe metryki sukcesu

| Metryka                    | Obecna wartość | Cel  |
| -------------------------- | -------------- | ---- |
| Modele bazowe              | 6              | 6+   |
| Warianty (search/thinking) | 20             | 20+  |
| Konta OAuth                | 3              | 10+  |
| Czas odpowiedzi (flash)    | ~1–3s          | \<2s |
| Uptime (no crashes)        | ~95%           | 99%  |
| Testy automatyczne         | 2 skrypty      | 50+  |

______________________________________________________________________

## 2. ANALIZA OBECNEGO STANU

### 2.1 Co działa dobrze

01. **Podstawowy flow działa** — requesty OpenAI → Gemini → odpowiedź
02. **Multi-account rotation** — 3 konta, round-robin, thread-safe (Lock)
03. **Streaming** — SSE prawidłowo proxy'owane
04. **Translator** — batch SRT translation z concurrent requests
05. **CLI** — `start.py` z argparse, `--translate`, `--add-account`, `--list-models`
06. **Thinking/Search warianty** — dynamiczne generowanie `-search`, `-nothinking`, `-maxthinking`
07. **System prompty** — poprawnie mapowane na Gemini `systemInstruction`
08. **Obsługa obrazów** — inline base64 images w chat completions
09. **Error handling** — JSON error responses, request_id tracking
10. **Graceful shutdown** — sigint handler w translatorze

### 2.2 Co wymaga poprawy

01. **Brak testów jednostkowych** — tylko integracyjne skrypty
02. **Globals w auth.py** — unsynchronized global state
03. **datetime.utcfromtimestamp** — deprecated od Python 3.12
04. **Token refresh poza lockiem** — race condition w accounts_manager
05. **Busy-wait polling** — streaming uses `queue.Queue` + `asyncio.sleep(0.01)`
06. **Brak requests.Session** — każdy request tworzy nowe połączenie TCP
07. **Catch-all route** — gemini_routes łapie wszystko co nie pasuje
08. **Brak rate limiting** — serwer nie limituje incoming requests
09. **Brak metryki** — brak Prometheus/OpenTelemetry
10. **Brak cache'owania** — te same prompty lecą za każdym razem

### 2.3 Statystyki kodu

| Komponent              | Pliki  | LOC (szacunkowo) |
| ---------------------- | ------ | ---------------- |
| server/                | 9      | ~1850            |
| apps/gemini_translator | 7      | ~750             |
| tests/                 | 2      | ~110             |
| config/docs            | 3      | ~200             |
| **Łącznie**            | **21** | **~2910**        |

______________________________________________________________________

## 3. ARCHITEKTURA SYSTEMU

### 3.1 Diagram przepływu danych

```
                    ┌──────────────────┐
                    │   Zewnętrzny     │
                    │   Klient         │
                    │ (SillyTavern,    │
                    │  Open WebUI,     │
                    │  curl, httpx)    │
                    └────────┬─────────┘
                             │
                    HTTP (OpenAI format / Native Gemini)
                             │
                    ┌────────▼─────────┐
                    │   FastAPI Server │
                    │   (port 8888)    │
                    │                  │
                    │  ┌─────────────┐ │
                    │  │ Auth Layer  │ │  ← Bearer/Basic/Key/Header
                    │  └──────┬──────┘ │
                    │         │        │
                    │  ┌──────▼──────┐ │
                    │  │ Router      │ │  ← openai_routes / gemini_routes
                    │  └──────┬──────┘ │
                    │         │        │
                    │  ┌──────▼──────┐ │
                    │  │ Transformer │ │  ← OpenAI ↔ Gemini format
                    │  └──────┬──────┘ │
                    │         │        │
                    │  ┌──────▼──────┐ │
                    │  │ API Client  │ │  ← google_api_client.py
                    │  └──────┬──────┘ │
                    │         │        │
                    │  ┌──────▼──────┐ │
                    │  │ Accounts    │ │  ← round-robin rotation
                    │  │ Manager     │ │  ← 3 konta OAuth
                    │  └──────┬──────┘ │
                    └─────────┼────────┘
                              │
                    requests.post (asyncio.to_thread)
                              │
                    ┌─────────▼────────┐
                    │ Google CodeAssist│
                    │ API              │
                    │ cloudcode-pa.    │
                    │ googleapis.com   │
                    └──────────────────┘
```

### 3.2 Warstwowość

System ma czyste warstwy:

```
Layer 1: CLI Interface        → start.py (argparse)
Layer 2: HTTP Server          → FastAPI + uvicorn
Layer 3: Authentication       → auth.py (multi-method)
Layer 4: Routing              → openai_routes.py, gemini_routes.py
Layer 5: Format Translation   → openai_transformers.py
Layer 6: API Communication    → google_api_client.py
Layer 7: Credentials Mgmt    → accounts_manager.py
Layer 8: Configuration        → config.py
```

### 3.3 Zależności między modułami

```
start.py → server/start.py → server/main.py
server/main.py → auth.py, accounts_manager.py, *_routes.py
openai_routes.py → auth.py, openai_transformers.py, google_api_client.py
gemini_routes.py → auth.py, google_api_client.py
google_api_client.py → auth.py, config.py, utils.py
auth.py → accounts_manager.py, config.py, utils.py
accounts_manager.py → config.py
openai_transformers.py → config.py, models.py
```

### 3.4 Przepływ requestu — krok po kroku (OpenAI endpoint)

01. Klient wysyła `POST /v1/chat/completions` z JSON payload
02. FastAPI parsuje request do `OpenAIChatCompletionRequest` (Pydantic)
03. `authenticate_user()` weryfikuje credentials (Bearer/Basic/Key/Header)
04. `openai_request_to_gemini()` konwertuje format OpenAI → Gemini
    - System messages → `systemInstruction`
    - User/assistant → contents
    - Images → `inlineData`
    - Thinking config → `thinkingConfig`
    - Search → `tools: [googleSearch]`
05. `build_gemini_payload_from_openai()` opakowuje w strukturę `{model, request}`
06. `send_gemini_request()`:
    - Generuje `request_id` (UUID[:8])
    - Pobiera credentials (`get_credentials()` → AccountsManager round-robin)
    - Uruchamia `asyncio.to_thread(_try_send_request_with_creds, ...)`
    - Retry na 403 z następnym kontem
07. `_try_send_request_with_creds()`:
    - Refresh token jeśli expired
    - Pobiera `project_id` (cache / API discovery)
    - Onboarding (jednorazowy per account)
    - `requests.post()` do Google CodeAssist API
    - Timeout: connect=30s, read=300s (non-stream) / 600s (stream)
08. Odpowiedź:
    - Non-streaming: `_handle_non_streaming_response()` → JSON
    - Streaming: `_handle_streaming_response()` → SSE generator
09. Powrót do routera:
    - Non-streaming: `gemini_response_to_openai()` konwertuje format
    - Streaming: `gemini_stream_chunk_to_openai()` dla każdego chunk'a
10. FastAPI zwraca JSON/SSE do klienta

### 3.5 Przepływ requestu — Translator

```
start.py --translate
  └→ apps/gemini_translator/start.py::main()
       ├→ TranslatorConfig() — ładuje ustawienia
       ├→ ensure_server_running() — health check / auto-start
       ├→ Etap 1: TextRefactor — TXT → SRT w input/
       ├→ Etap 2: GeminiTranslator.translate_all_files()
       │    ├→ Znajduje .srt w input/
       │    ├→ shutil.copy2(input, output) — baseline copy
       │    ├→ Dzieli na grupy po translated_line_count (20)
       │    ├→ asyncio.create_task() dla każdej grupy
       │    ├→ Semaphore(concurrent_requests=16) limituje współbieżność
       │    ├→ translate_group() — retry loop z exponential backoff
       │    │    ├→ translate_with_api() → httpx POST do proxy
       │    │    ├→ format_response() — czyści tokeny ◍◍
       │    │    ├→ update_subtitles() — podmienia tekst w SubRipItem
       │    │    └→ subs.save() — async with write_lock
       │    └→ asyncio.gather(*tasks)
       └→ Etap 3: TextRefactor — SRT → TXT w output_txt/
```

______________________________________________________________________

## 4. SERWER PROXY — DEEP DIVE

### 4.1 Plik: `server/config.py` (~225 LOC)

**Odpowiedzialność**: Centralna konfiguracja — ścieżki, stałe, modele, OAuth.

**Kluczowe elementy**:

- `BASE_MODELS` — lista 6 zweryfikowanych modeli
- `SUPPORTED_MODELS` — BASE + search + thinking warianty (20 łącznie)
- `_has_thinking_support()` — centralna logika: które modele wspierają thinking
- `get_thinking_budget()` — budżet tokingowy per model/variant
- `should_include_thoughts()` — czy includeThoughts=true
- `get_base_model_name()` — strip suffixes (-search, -nothinking, -maxthinking)
- `DEFAULT_SAFETY_SETTINGS` — 11 kategorii, wszystkie BLOCK_NONE

**Wzorce**:

- Generatory wariantów (`_generate_search_variants()`, `_generate_thinking_variants()`)
  dynamicznie tworzą modele pochodne z BASE_MODELS
- Sorted output: `SUPPORTED_MODELS = sorted(all_models, key=lambda x: x["name"])`

**Potencjalne ulepszenia**:

- Przeniesienie stałych OAuth (CLIENT_ID/SECRET) do .env
- Walidacja modeli przy starcie (API health check)
- Lazy loading modeli zamiast at-import-time
- Dataclass/Pydantic model zamiast raw dict

### 4.2 Plik: `server/main.py` (~182 LOC)

**Odpowiedzialność**: Aplikacja FastAPI, startup/shutdown, CORS.

**Kluczowe elementy**:

- `lifespan()` async context manager — startup i shutdown
- Startup: AccountsManager, get_credentials, onboard_user
- CORS: allow_origins=["\*"] (dev-friendly, prod-risky)
- Routers: openai_router (pierwszy), gemini_router (catch-all ostatni)
- Root endpoint `/` z info o projekcie
- Health check `/health`
- Options handler dla CORS preflight

**Wzorce**:

- Lifespan context manager (FastAPI 0.109+)
- GlobalAccountsManager instance (module-level singleton)

**Potencjalne ulepszenia**:

- Przenieść startup logic do osobnego `startup.py`
- Dodać middleware: request logging, rate limiting, metrics
- Dodać shutdown hooks: close connections, flush buffers
- Graceful degradation: serwer startuje nawet bez kont

### 4.3 Plik: `server/auth.py` (~466 LOC)

**Odpowiedzialność**: Autentykacja requestów + OAuth flow + credentials management.

**Kluczowe elementy**:

- `authenticate_user()` — 4 metody auth (Bearer, Basic, Key, Header)
- `get_credentials()` — waterfall: AccountsManager → memory → env → file → OAuth
- `onboard_user()` — setupUser via CodeAssist API, per-account tracking
- `get_user_project_id()` — discovery via API + caching
- `_run_oauth_flow()` — interactive browser-based OAuth
- `_OAuthCallbackHandler` — HTTP server na port 8080 dla callback

**Wzorce**:

- Per-account tracking via `_onboarded_accounts: set` (identity-based hashing)
- Waterfall pattern: try method A → try method B → try method C
- Monkeypatching: `oauthlib...validate_token_parameters = lambda p: None`

**Problemy**:

- Global state (`credentials`, `user_project_id`, `onboarding_complete`) bez Lock
- `datetime.utcfromtimestamp()` — deprecated Python 3.12+
- `_onboarded_accounts` uses `id(creds)` — not stable across rotations
- Port 8080 hardcoded — conflict potential

### 4.4 Plik: `server/accounts_manager.py` (~265 LOC)

**Odpowiedzialność**: Multi-account OAuth management z round-robin.

**Kluczowe elementy**:

- `_accounts: List[dict]` — lista kont `{file, creds, project_id}`
- `_current_index` — round-robin counter
- `_thread_lock: threading.Lock` — thread-safe sync rotation
- `_lock: asyncio.Lock` — async rotation (unused currently)
- `get_credentials_sync()` — rotate + auto-refresh
- `add_account_interactive()` — full OAuth flow for new accounts
- `_load_single_account()` — load JSON, normalize fields, auto-refresh

**Wzorce**:

- Round-robin: `_current_index = (idx + 1) % len(accounts)`
- Thread-safe rotation: `with self._thread_lock:`
- Auto-refresh on load: expired tokens refreshed immediately

**Problemy**:

- Token refresh OUTSIDE lock → race condition
- `_save_account()` OUTSIDE lock → concurrent writes
- `datetime.utcfromtimestamp()` — deprecated
- No retry on refresh failure → account becomes dead

### 4.5 Plik: `server/google_api_client.py` (~441 LOC)

**Odpowiedzialność**: Core HTTP communication z Google CodeAssist API.

**Kluczowe elementy**:

- `send_gemini_request()` — async, retry with account rotation
- `_try_send_request_with_creds()` — single attempt with given creds
- `_handle_streaming_response()` — SSE proxy z thread + queue
- `_handle_non_streaming_response()` — JSON extraction
- `build_gemini_payload_from_openai()` — payload builder
- `build_gemini_payload_from_native()` — native Gemini payload
- Timeouts: CONNECT=30s, READ=300s, STREAM=600s
- Request ID tracking: UUID[:8] prefix na wszystkich logach

**Wzorce**:

- `asyncio.to_thread()` — blocking `requests.post` w thread pool
- Streaming: background thread reads `iter_lines()`, pushes to `queue.Queue`
- Async generator polls queue z `asyncio.sleep(0.01)`
- Retry on 403 with next account

**Problemy**:

- `requests` library — synchronous, no connection pooling
- Busy-wait polling: `asyncio.sleep(0.01)` = ~100 polls/sec
- Thread per streaming request — no pool
- No circuit breaker — endless retries on persistent failures

### 4.6 Plik: `server/openai_transformers.py` (~325 LOC)

**Odpowiedzialność**: Dwukierunkowa konwersja OpenAI ↔ Gemini format.

**Kluczowe elementy**:

- `openai_request_to_gemini()` — full conversion:
  - System messages → `systemInstruction`
  - Content parts (text, image_url, inline markdown images)
  - Generation config (temperature, topP, max_tokens, etc.)
  - Thinking config (budget, includeThoughts)
  - Search tool injection
- `gemini_response_to_openai()` — response conversion:
  - Parts → content (text, thought → reasoning_content, images)
  - Finish reason mapping
  - UUID generation for response ID
- `gemini_stream_chunk_to_openai()` — streaming chunk conversion

**Wzorce**:

- Regex-based inline image extraction: `r'!\[[^\]]*\]\(([^)]+)\)'`
- data: URI parsing for base64 images
- Conditional thinking config based on model capabilities

**Problemy**:

- Dupllikacja logiki image parsing (3x ten sam regex)
- Brak walidacji incoming data
- \\n\\n join dla content_parts — może złamać formatowanie
- No caching of compiled regexes

### 4.7 Plik: `server/openai_routes.py` (~240 LOC)

**Odpowiedzialność**: Endpointy OpenAI-compatible.

**Kluczowe elementy**:

- `POST /v1/chat/completions` — main endpoint
  - Streaming: generator function, SSE format
  - Non-streaming: direct JSON response
  - Error handling: JSON error responses always
- `GET /v1/models` — lista modeli w formacie OpenAI

**Wzorce**:

- Streaming via `StreamingResponse` + async generator
- `[DONE]` sentinel na końcu streamu

### 4.8 Plik: `server/gemini_routes.py` (~109 LOC)

**Odpowiedzialność**: Native Gemini API proxy.

**Kluczowe elementy**:

- `GET /v1beta/models` — lista modeli
- `/{full_path:path}` — catch-all proxy
- `_extract_model_from_path()` — parser URL

**Problemy**:

- Catch-all route łapie WSZYSTKO — nawet favicon.ico, robots.txt
- Może konflikować z przyszłymi endpointami

______________________________________________________________________

## 5. TRANSLATOR — DEEP DIVE

### 5.1 Architektura Translatora

```
TranslatorConfig (dataclass)
  └→ determines: model, concurrency, mode, paths, chunks

GeminiTranslator
  ├→ GeminiAPIClient (httpx AsyncClient)
  │    ├→ generate() — text-only prompt
  │    └→ generate_with_image() — multimodal prompt
  ├→ asyncio.Semaphore(concurrent_requests) — throttle
  ├→ asyncio.Lock (write_lock) — file write safety
  └→ Pipeline:
       ├→ translate_all_files() — file discovery
       ├→ translate_srt() — SRT splitting + task creation
       ├→ translate_group() — retry loop per group
       ├→ translate_with_api() — actual API call
       ├→ format_response() — cleanup response tokens
       └→ update_subtitles() — apply translations
```

### 5.2 Tryby pracy

| Tryb       | Input            | Output | Opis                     |
| ---------- | ---------------- | ------ | ------------------------ |
| `text`     | .srt             | .srt   | Standard SRT translation |
| `image`    | .png/.jpg        | .srt   | Image → text via vision  |
| `manga`    | .txt + .png      | .srt   | Manga page translation   |
| `subtitle` | .srt             | .srt   | Subtitle-specific        |
| `ocr`      | folder of images | .txt   | Batch OCR                |

### 5.3 Format tokenów tłumaczeniowych

```
Input:  ◍◍1. Hello world ◍◍◍◍ this is second line @@
        ◍◍2. Goodbye @@
Output: ◍◍1. Cześć świecie ◍◍◍◍ to jest druga linia @@
        ◍◍2. Do widzenia @@
```

Tokeny:

- `◍◍N.` — numer linii (prefix)
- `◍◍◍◍` — separator wewnątrz linii (= newline w SRT)
- `@@` — separator między liniami
- ` @@\n` — separator między wpisami

### 5.4 Strategia retry

```
Attempt 1: wait 1.0s    (1.0 * 2^0)
Attempt 2: wait 2.0s    (1.0 * 2^1)
Attempt 3: wait 4.0s    (1.0 * 2^2)
Attempt 4: wait 8.0s    (1.0 * 2^3)
Attempt 5: wait 16.0s   (1.0 * 2^4)
Attempt 6: wait 32.0s   (1.0 * 2^5)
Attempt 7: wait 60.0s   (min(64, MAX_BACKOFF=60))
Attempt 8: wait 60.0s
Attempt 9: wait 60.0s
Attempt 10: FAIL — save partial if available
```

MAX_RETRIES=10, INITIAL_BACKOFF=1.0, MAX_BACKOFF=60.0

### 5.5 Zabezpieczenia

- `shutil.copy2()` — baseline copy przed tłumaczeniem
- `write_lock` — atomic file writes
- Partial translation save — na ostatniej próbie
- Stats tracking — `_translated_groups` / `_failed_groups`
- Semaphore — limituje równoległe requesty

### 5.6 Potencjalne ulepszenia

01. **Resume/checkpoint** — zapisuj postęp do `.progress.json`
02. **Smart grouping** — grupuj krótkie linie razem, długie osobno
03. **Glossary** — słownik pojęć do zachowania spójności
04. **Post-processing** — walidacja jakości tłumaczenia
05. **Streaming** — strumieniowe tłumaczenie dla szybszego feedback'u
06. **Parallel files** — wiele plików jednocześnie (teraz sekwencyjnie per file)
07. **Cache** — identyczne grupy = cache hit
08. **Dry-run** — preview bez zapisywania
09. **Language detection** — auto-detect source language
10. **Multi-target** — tłumacz na wiele języków jednocześnie

______________________________________________________________________

## 6. SYSTEM AUTENTYKACJI I KONT

### 6.1 Flow autentykacji klienta

```
Request → authenticate_user()
  ├→ 1. Query param: ?key=123456
  ├→ 2. Header: x-goog-api-key: 123456
  ├→ 3. Bearer: Authorization: Bearer 123456
  ├→ 4. Basic: Authorization: Basic base64(user:123456)
  └→ 5. REJECT: 401 Unauthorized
```

### 6.2 Flow autentykacji do Google

```
AccountsManager.get_credentials_sync()
  ├→ Thread-safe rotation (threading.Lock)
  ├→ Pick next account (round-robin)
  ├→ If expired → refresh token
  └→ Return Credentials

Onboarding (jednorazowy per account):
  ├→ POST /v1internal:loadCodeAssist
  ├→ Check currentTier
  ├→ If no tier: POST /v1internal:onboardUser (polling loop)
  └→ Add to _onboarded_accounts set
```

### 6.3 Format pliku konta

```json
{
  "client_id": "681255809395-...apps.googleusercontent.com",
  "client_secret": "GOCSPX-...",
  "token": "ya29.a0...",
  "refresh_token": "1//0e...",
  "scopes": ["https://www.googleapis.com/auth/cloud-platform", ...],
  "token_uri": "https://oauth2.googleapis.com/token",
  "expiry": "2026-02-15T20:28:14.753000+00:00",
  "project_id": "hallowed-node-..."
}
```

### 6.4 Scenariusze awaryjne

| Scenariusz              | Obecne zachowanie             | Idealne zachowanie         |
| ----------------------- | ----------------------------- | -------------------------- |
| Token expired           | Auto-refresh → continue       | OK ✓                       |
| Refresh failed          | Warning log, use stale token  | Remove account, use next   |
| All accounts 403        | Return last 403 to client     | Queue request, retry later |
| OAuth callback timeout  | Server hangs on port 8080     | Timeout + helpful message  |
| Network down            | ConnectionError, 502 response | Retry with backoff         |
| Onboarding timeout      | Exception after 120s          | OK ✓                       |
| New model not onboarded | 403 → next account            | Auto-onboard new project   |

______________________________________________________________________

## 7. MODELE I ICH WARIANTY

### 7.1 Modele bazowe (zweryfikowane)

| Model                    | Input Tokens | Output Tokens | Thinking | Status  |
| ------------------------ | ------------ | ------------- | -------- | ------- |
| `gemini-2.0-flash`       | 1,048,576    | 8,192         | ✗        | ✓ 200   |
| `gemini-2.5-flash`       | 1,048,576    | 65,535        | ✓        | ✓ 200   |
| `gemini-2.5-flash-lite`  | 1,048,576    | 65,535        | ✗        | ✓ 200   |
| `gemini-2.5-pro`         | 1,048,576    | 65,535        | ✓        | ✓ 200   |
| `gemini-3-flash-preview` | 1,048,576    | 65,535        | ✓        | ✓ 200\* |
| `gemini-3-pro-preview`   | 1,048,576    | 65,535        | ✓        | 429\*\* |

\*gemini-3-flash-preview: działa ale ograniczona pojemność
\*\*gemini-3-pro-preview: brak pojemności (Google capacity limit)

### 7.2 System wariantów

Każdy model bazowy generuje warianty:

```
base-model
  ├→ base-model-search          Google Search grounding
  ├→ base-model-nothinking      Thinking budget = 0/128
  └→ base-model-maxthinking     Thinking budget = max
```

Wyjątki:

- `gemini-2.0-flash` — bez thinking (brak wsparcia)
- `gemini-2.5-flash-lite` — bez thinking (brak wsparcia)

### 7.3 Budżety thinkingowe

| Model                    | nothinking | default   | maxthinking |
| ------------------------ | ---------- | --------- | ----------- |
| `gemini-2.5-flash`       | 0          | -1 (auto) | 24,576      |
| `gemini-2.5-pro`         | 128        | -1 (auto) | 32,768      |
| `gemini-3-flash-preview` | 0          | -1 (auto) | 24,576      |
| `gemini-3-pro-preview`   | 128        | -1 (auto) | 45,000      |

### 7.4 Reasoning effort mapping (OpenAI → Gemini)

```
minimal → thinking_budget = 0 (flash) / 128 (pro)
low     → thinking_budget = 1000
medium  → thinking_budget = -1 (auto)
high    → thinking_budget = max
```

______________________________________________________________________

## 8. OBSŁUGA BŁĘDÓW I ODPORNOŚĆ

### 8.1 Warstwy obsługi błędów

```
Layer 1: HTTP Client (requests library)
  → ConnectTimeout (30s), ReadTimeout (300s/600s)
  → ConnectionError, RequestException

Layer 2: Google API Response
  → 200: OK, extract response
  → 403: Forbidden → retry z następnym kontem
  → 404: Model not found → pass through
  → 429: Rate limit → pass through
  → 500+: Server error → pass through

Layer 3: Application Logic
  → JSON parse errors
  → Missing fields in response
  → Empty content

Layer 4: FastAPI Error Handling
  → 400: Invalid request format
  → 401: Authentication failure
  → 500: Unhandled exceptions
```

### 8.2 Formaty błędów

Wszystkie błędy zwracane jako JSON:

```json
{
  "error": {
    "message": "Opis błędu",
    "type": "invalid_request_error | api_error",
    "code": 400
  }
}
```

### 8.3 Request ID Tracking

```
[a1b2c3d4] New request: model=gemini-2.5-flash, stream=false, accounts=3
[a1b2c3d4] Using account #1 (account_1.json)
[a1b2c3d4] Sending request to Google API: model=gemini-2.5-flash
[a1b2c3d4] Request completed successfully
```

### 8.4 Retry Logic

**Serwer**: retry on 403 z account rotation (max = number of accounts)
**Translator**: retry on any error (max=10, exponential backoff 1s → 60s)

### 8.5 Brakujące mechanizmy

1. **Circuit Breaker** — po N failures, stop trying for X seconds
2. **Retry-After** — honor 429 Retry-After header
3. **Graceful Degradation** — fallback do mniejszego modelu
4. **Health monitoring** — periodic ping to Google API
5. **Alert system** — notify when all accounts exhausted

______________________________________________________________________

## 9. WYDAJNOŚĆ I WSPÓŁBIEŻNOŚĆ

### 9.1 Model współbieżności

```
                          ┌─────────────────────┐
                          │ uvicorn event loop   │
                          │ (single process)     │
                          └──────────┬──────────┘
                                     │
            ┌────────────────────────┼────────────────────────┐
            │                        │                        │
    ┌───────▼───────┐      ┌────────▼────────┐     ┌────────▼────────┐
    │ Request 1     │      │ Request 2       │     │ Request 3       │
    │ → to_thread() │      │ → to_thread()   │     │ → to_thread()   │
    └───────┬───────┘      └────────┬────────┘     └────────┬────────┘
            │                        │                        │
    ┌───────▼───────┐      ┌────────▼────────┐     ┌────────▼────────┐
    │ Thread Pool   │      │ Thread Pool     │     │ Thread Pool     │
    │ Worker 1      │      │ Worker 2        │     │ Worker 3        │
    │ requests.post │      │ requests.post   │     │ requests.post   │
    └───────────────┘      └─────────────────┘     └─────────────────┘
```

### 9.2 Bottlenecks

1. **GIL** — Python GIL nie jest problemem (I/O bound, not CPU bound)
2. **requests library** — no connection pooling, new TCP per request
3. **Thread overhead** — nowy thread per request (vs connection pool)
4. **Streaming polling** — `asyncio.sleep(0.01)` = wasted cycles
5. **Account rotation lock** — threading.Lock contention at high load

### 9.3 Benchmarki (z test_concurrency.py)

```
4 równoległe requesty (gemini-2.5-flash):
  - Całkowity czas: ~4.0s (vs ~10.7s sekwencyjnie)
  - Speedup: ~2.6x
  - Limitujący: Google API latency, nie serwer

1 request (gemini-2.0-flash):    ~0.7–1.2s
1 request (gemini-2.5-flash):    ~2.5–3.5s
1 request (gemini-2.5-pro):      ~7–9s
1 request (gemini-3-flash):      ~5–8s
```

### 9.4 Optymalizacje do rozważenia

1. **requests.Session** — connection pooling + keep-alive
2. **httpx zamiast requests** — async native, HTTP/2
3. **Connection pool** — limit concurrent connections
4. **asyncio.Queue** zamiast queue.Queue — no polling needed
5. **uvicorn workers** — multi-process (ale komplikuje state)
6. **Response caching** — identyczne prompty = cache hit
7. **Request batching** — queue + batch send to Google

______________________________________________________________________

## 10. BEZPIECZEŃSTWO

### 10.1 Obecne mechanizmy

| Mechanizm                | Status | Szczegóły                     |
| ------------------------ | ------ | ----------------------------- |
| Auth password            | ✓      | Domyślne "123456", via env    |
| Password masking in logs | ✓      | `****` + last 4 chars         |
| OAuth tokens in files    | ✓      | accounts/\*.json (gitignored) |
| CORS wide open           | ⚠️     | allow_origins=["\*"]          |
| No HTTPS                 | ⚠️     | Tylko HTTP (localhost OK)     |
| No rate limiting         | ⚠️     | DoS possible                  |
| Hardcoded CLIENT_SECRET  | ⚠️     | W config.py (ale Google's)    |
| No input validation      | ⚠️     | Pydantic bazowy + trust proxy |
| .gitignore accounts      | ✓      | accounts/\*.json excluded     |

### 10.2 Rekomendowane ulepszenia

1. **Rate limiting** — per-IP, per-minute (fastapi-limiter)
2. **HTTPS** — certbot / mkcert for localhost
3. **Silne hasło** — wymuszone via env, nie domyślne "123456"
4. **CORS restriction** — whitelist origins w produkcji
5. **Token encryption** — encrypt accounts/\*.json at rest
6. **Audit log** — kto, kiedy, jaki model, ile tokenów
7. **Request sanitization** — limit payload size, validate inputs
8. **Secret management** — Vault / encrypted .env

### 10.3 Threat model

```
Threat: Unauthorized API access
  → Mitigation: Auth password
  → Risk: Low (localhost only)

Threat: OAuth token theft via git
  → Mitigation: .gitignore, separate accounts dir
  → Risk: Low (if gitignore working)

Threat: Man-in-the-middle (local)
  → Mitigation: None (HTTP)
  → Risk: Very low (localhost)

Threat: Denial of Service
  → Mitigation: None
  → Risk: Medium (no rate limiting)

Threat: Google account suspension
  → Mitigation: Multiple accounts
  → Risk: Medium (ToS compliance unclear)
```

______________________________________________________________________

## 11. TESTOWANIE

### 11.1 Obecny stan

| Typ testu          | Pliki               | Pokrycie | Status |
| ------------------ | ------------------- | -------- | ------ |
| Integracyjne       | test_concurrency.py | ~5%      | ✓      |
| Model verification | test_all_models.py  | ~2%      | ✓      |
| Jednostkowe        | —                   | 0%       | ✗      |
| E2E translator     | —                   | 0%       | ✗      |
| Perf/load          | —                   | 0%       | ✗      |

### 11.2 Plan testowania

**Priorytet 1: Jednostkowe (pytest)**

```python
# test_config.py
def test_has_thinking_support():
    assert _has_thinking_support("gemini-2.5-flash") == True
    assert _has_thinking_support("gemini-2.0-flash") == False
    assert _has_thinking_support("gemini-2.5-flash-lite") == False

def test_get_base_model_name():
    assert get_base_model_name("gemini-2.5-flash-search") == "gemini-2.5-flash"
    assert get_base_model_name("gemini-2.5-pro-maxthinking") == "gemini-2.5-pro"

def test_supported_models_count():
    assert len(BASE_MODELS) == 6
    assert len(SUPPORTED_MODELS) == 20

# test_openai_transformers.py
def test_system_message_extraction():
    ...

def test_image_url_parsing():
    ...

def test_thinking_budget_mapping():
    ...

# test_auth.py
def test_authenticate_bearer():
    ...

def test_authenticate_basic():
    ...

def test_authenticate_invalid():
    ...
```

**Priorytet 2: Integracyjne (httpx + running server)**

```python
# test_api_integration.py
async def test_chat_completion_non_streaming():
    ...

async def test_chat_completion_streaming():
    ...

async def test_models_endpoint():
    ...

async def test_system_prompt():
    ...

async def test_image_input():
    ...
```

**Priorytet 3: E2E Translator**

```python
# test_translator_e2e.py
async def test_translate_simple_srt():
    ...

async def test_translate_with_partial_save():
    ...

async def test_translate_resume():
    ...
```

### 11.3 Test infrastructure

```
pytest.ini / pyproject.toml:
  - testpaths = ["tests"]
  - asyncio_mode = "auto"
  - markers: ["slow", "integration", "e2e"]

Fixtures:
  - server_running: start server, yield URL, stop server
  - sample_srt: generate test SRT file
  - mock_google_api: mock responses
```

______________________________________________________________________

## 12. ZNANE PROBLEMY I TECH DEBT

### 12.1 Krityczne

| #   | Problem                    | Plik                   | Wpływ          |
| --- | -------------------------- | ---------------------- | -------------- |
| K1  | Token refresh outside Lock | accounts_manager.py:70 | Race condition |
| K2  | Globals without sync       | auth.py (global vars)  | Data race      |

### 12.2 Wysokie

| #   | Problem                            | Plik                 | Wpływ        |
| --- | ---------------------------------- | -------------------- | ------------ |
| H1  | No requests.Session (no conn pool) | google_api_client.py | Performance  |
| H2  | Busy-wait streaming poll           | google_api_client.py | CPU waste    |
| H3  | Catch-all route                    | gemini_routes.py     | Routing bugs |

### 12.3 Średnie

| #   | Problem                              | Plik                   | Wpływ         |
| --- | ------------------------------------ | ---------------------- | ------------- |
| M1  | datetime.utcfromtimestamp deprecated | auth.py, accounts_mgr  | Depr warning  |
| M2  | Duplicated image regex 3x            | openai_transformers.py | Maintenance   |
| M3  | Port 8080 hardcoded for OAuth        | auth.py                | Port conflict |
| M4  | No input payload size limit          | openai_routes.py       | DoS risk      |

### 12.4 Niskie

| #   | Problem                          | Plik          | Wpływ        |
| --- | -------------------------------- | ------------- | ------------ |
| L1  | oauthlib validation monkeypatch  | auth.py       | Fragile      |
| L2  | No structured logging (JSON)     | everywhere    | Log parsing  |
| L3  | Console print mixed with logging | translator.py | Inconsistent |

### 12.5 Plan naprawy

**Sprint 1 (P0 — blockers)**:

- [ ] K1: Move token refresh inside `_thread_lock` in accounts_manager
- [ ] K2: Add `_auth_lock = threading.Lock()` for global state in auth.py

**Sprint 2 (P1 — performance)**:

- [ ] H1: Replace `requests` with `httpx` or use `requests.Session`
- [ ] H2: Rewrite streaming with `asyncio.Queue` + sentinel pattern
- [ ] H3: Explicit routes instead of catch-all

**Sprint 3 (P2 — cleanup)**:

- [ ] M1: Replace `datetime.utcfromtimestamp` with `datetime.fromtimestamp(ts, tz=UTC)`
- [ ] M2: Extract image parsing to helper function
- [ ] M3: Make OAuth callback port configurable

______________________________________________________________________

## 13. ROADMAP — KRÓTKOTERMINOWA (v2.1)

### Cel: Stabilność i testowanie

**Timeline: 2–4 tygodnie**

1. **Fix critical race conditions**

   - Token refresh in lock (K1)
   - Auth globals synchronization (K2)
   - Estimated: 2h

2. **Replace requests with httpx**

   - Server-side: httpx.AsyncClient with connection pooling
   - Remove asyncio.to_thread (httpx is natively async)
   - Streaming: native async iteration
   - Estimated: 4h

3. **Unit tests**

   - config.py: 100% coverage
   - openai_transformers.py: 80%+ coverage
   - auth.py: mock-based tests
   - Estimated: 8h

4. **Structured logging**

   - JSON format with structlog
   - Request ID, model, latency, tokens in every log
   - Estimated: 3h

5. **Fix deprecated APIs**

   - datetime.utcfromtimestamp → fromtimestamp(ts, tz=UTC)
   - Estimated: 30min

6. **Config validation**

   - Pydantic settings model
   - .env.example file
   - Startup validation
   - Estimated: 2h

______________________________________________________________________

## 14. ROADMAP — ŚREDNIOTERMINOWA (v3.0)

### Cel: Produkcyjna jakość

**Timeline: 1–3 miesiące**

1. **Admin Dashboard (Web UI)**

   ```
   ┌─────────────────────────────────────┐
   │ geminicli2api Dashboard             │
   ├─────────────────────────────────────┤
   │ Accounts: 3/3 active    ⟲ Refresh  │
   │ ┌─────┬────────┬────────┬────────┐ │
   │ │ #   │ Email  │ Status │ Reqs   │ │
   │ ├─────┼────────┼────────┼────────┤ │
   │ │ 1   │ a@g.co │ ✓ OK   │ 142    │ │
   │ │ 2   │ b@g.co │ ✓ OK   │ 138    │ │
   │ │ 3   │ c@g.co │ ⚠ 429  │ 86     │ │
   │ └─────┴────────┴────────┴────────┘ │
   │                                     │
   │ Recent Requests (last 50)           │
   │ ┌──────┬──────────┬───────┬──────┐ │
   │ │ Time │ Model    │ Tokens│Status│ │
   │ ├──────┼──────────┼───────┼──────┤ │
   │ │ 21:28│ 2.5-flash│ 1,234 │ 200  │ │
   │ │ 21:27│ 2.5-pro  │ 8,901 │ 200  │ │
   │ └──────┴──────────┴───────┴──────┘ │
   └─────────────────────────────────────┘
   ```

2. **Request Queue System**

   - In-memory queue (asyncio.Queue)
   - Priority: pro > flash > lite
   - Backpressure: reject when queue full
   - Metrics: queue depth, wait time

3. **Response Caching**

   - Key: hash(model + messages + config)
   - Storage: SQLite / shelve
   - TTL: configurable (default 24h)
   - Cache-Control header support

4. **Plugin System**

   - Pre-request hooks
   - Post-response hooks
   - Custom auth providers
   - Model routing rules

5. **Metrics & Monitoring**

   - Prometheus metrics endpoint
   - Request latency histogram
   - Token usage counters
   - Account health checks
   - Grafana dashboards

6. **Rate Limiting**

   - Per-IP limits
   - Per-model limits
   - Token-based budgets
   - Sliding window algorithm

7. **Multi-language Translator**

   - Auto-detect source language
   - Support 50+ target languages
   - Custom prompt templates per language pair
   - Quality scoring

______________________________________________________________________

## 15. ROADMAP — DŁUGOTERMINOWA (v4.0+)

### Cel: Platform + Ecosystem

**Timeline: 3–6 miesięcy**

1. **Docker / Docker Compose**

   ```yaml
   services:
     proxy:
       build: .
       ports:
         - "8888:8888"
       volumes:
         - ./accounts:/app/accounts
       environment:
         - GEMINI_AUTH_PASSWORD=strong_pass
   ```

2. **Web-based Translator UI**

   - React / Svelte frontend
   - Drag & drop file upload
   - Real-time translation progress
   - Side-by-side original/translated view
   - Glossary management

3. **Multi-provider Support**

   - Google Gemini (current)
   - Google AI Studio (API keys)
   - Anthropic Claude (via Vertex)
   - OpenAI GPT (pass-through)
   - Local models (Ollama integration)

4. **Account Marketplace**

   - Sell/share proxy access
   - Token-based billing
   - Usage dashboard per user
   - API key management (not just password)

5. **Auto-scaling**

   - Multiple proxy instances
   - Load balancer (nginx / caddy)
   - Shared account pool (Redis)
   - Health-based routing

6. **CLI Enhancement**

   - Interactive TUI (textual/rich)
   - Config wizard
   - Real-time server monitoring
   - Log tailing

7. **SDK / Library**

   ```python
   from geminicli2api import GeminiClient

   client = GeminiClient("http://localhost:8888", api_key="123456")
   response = client.chat("Hello!", model="gemini-2.5-flash")
   print(response.text)
   ```

______________________________________________________________________

## 16. POMYSŁY NA NOWE FUNKCJE

### 16.1 Quick Wins (1-2h each)

1. **`--test-models` CLI flag** — ping all models, report status
2. **`--status` CLI flag** — show server status, accounts, queues
3. **Health check enhancement** — include model availability
4. **Request logging to file** — `--log-file requests.log`
5. **Version endpoint** — `GET /version`
6. **Config reload** — `POST /admin/reload` (hot reload config)
7. **`.env.example`** — dokumentacja zmiennych środowiskowych
8. **Colored logs** — rich/colorama for server logs

### 16.2 Medium Effort (4-8h each)

1. **Prompt caching** — Gemini supports cached system prompts
2. **Batch API** — submit multiple prompts, get results later
3. **Embeddings endpoint** — `/v1/embeddings` for text-embedding-004
4. **File upload** — temporary file storage for multimodal
5. **Conversation memory** — track multi-turn conversations
6. **Custom model aliases** — `fast` → `gemini-2.5-flash`, `best` → `gemini-2.5-pro`
7. **Request replay** — save & replay failed requests
8. **Model fallback chain** — if pro fails, try flash, then lite

### 16.3 Big Features (1-2 weeks each)

1. **Function calling** — full tool/function support
2. **Code execution** — Gemini code execution capability
3. **Video/audio input** — multimodal beyond images
4. **PDF processing** — extract + translate PDFs
5. **Real-time translation** — WebSocket-based live translation
6. **Translation memory (TM)** — database of previous translations
7. **Quality estimation** — auto-score translation quality
8. **A/B testing** — compare translations from different models

### 16.4 Eksperymenty

1. **Speculative decoding** — send to 2 models, return faster one
2. **Ensembling** — average translations from multiple models
3. **Fine-tuning pipeline** — user corrections → better prompts
4. **Active learning** — ask user to validate uncertain translations
5. **Bilingual summary** — generate summary in both languages

______________________________________________________________________

## 17. ALTERNATYWNE PODEJŚCIA

### 17.1 Architektura

| Podejście          | Pros                        | Cons                         | Wybrany?  |
| ------------------ | --------------------------- | ---------------------------- | --------- |
| FastAPI + requests | Prosty, działa              | No async, no pooling         | ✓ (teraz) |
| FastAPI + httpx    | Async native, HTTP/2        | Minor migration effort       | → v2.1    |
| aiohttp            | Mature async                | Different API, less popular  | ✗         |
| Go (net/http)      | Performance, goroutines     | Rewrite, no Python ecosystem | ✗         |
| Node.js (Express)  | Async native, npm ecosystem | Rewrite, less suited         | ✗         |
| Rust (actix-web)   | Maximum performance         | Rewrite, steep learning      | ✗         |

### 17.2 Google API Access

| Metoda                 | Darmowy? | Stabilny? | Ryzyko? | Wybrany?  |
| ---------------------- | -------- | --------- | ------- | --------- |
| CodeAssist (CLI proxy) | ✓        | ~         | Medium  | ✓ (teraz) |
| AI Studio API keys     | ✓ (free) | ✓         | Low     | Fallback  |
| Vertex AI              | ✗ (paid) | ✓         | Low     | ✗         |
| Web scraping           | ✓        | ✗         | High    | ✗         |
| Extension API          | ✓        | ~         | Medium  | Consider  |

### 17.3 Translator Backend

| Podejście            | Pros                   | Cons                      |
| -------------------- | ---------------------- | ------------------------- |
| Per-file sequential  | Simple, predictable    | Slow                      |
| Per-group concurrent | Fast, good parallelism | Complex error handling    |
| Batch API            | Efficient, one request | Latency, token limits     |
| Streaming + parse    | Real-time feedback     | Complex parsing           |
| Queue-based          | Backpressure, priority | Infrastructure complexity |

______________________________________________________________________

## 18. PORÓWNANIE Z INNYMI PROJEKTAMI

### 18.1 Konkurenci

| Projekt    | Opis                    | Differences                 |
| ---------- | ----------------------- | --------------------------- |
| gemini-cli | Official Google CLI     | No API, just CLI chat       |
| litellm    | Universal LLM proxy     | Paid models, no OAuth trick |
| one-api    | OpenAI-compatible proxy | Supports many providers     |
| OpenRouter | Commercial LLM router   | Paid, multi-provider        |
| ollama     | Local model serving     | Local only, different scope |
| lm-studio  | Local model UI + server | Local only, GUI-focused     |

### 18.2 Unikalna wartość geminicli2api

1. **Darmowe Gemini** — jedyny projekt dający darmowy API access
2. **Multi-account** — round-robin rotation = higher throughput
3. **Dual format** — OpenAI-compatible + native Gemini
4. **Integrated translator** — not just proxy, but full app on top
5. **Thinking control** — fine-grained thinking budget management
6. **Search grounding** — Google Search as tool, not available elsewhere free

______________________________________________________________________

## 19. DEPLOYMENT I HOSTING

### 19.1 Obecny setup

```
OS: Windows 10/11 (dev machine)
Python: 3.11+ (3.13.11 confirmed)
Package manager: uv
Host: localhost only (127.0.0.1:8888)
Process: foreground terminal
```

### 19.2 Opcje deployment'u

| Opcja               | Difficulty | Cost   | Persistence | Remote Access |
| ------------------- | ---------- | ------ | ----------- | ------------- |
| Local terminal      | Easy       | Free   | No          | No            |
| Systemd service     | Medium     | Free   | Yes         | Local only    |
| Docker              | Medium     | Free   | Yes         | Configurable  |
| Docker + Cloudflare | Medium     | Free   | Yes         | Yes (tunnel)  |
| VPS (Hetzner/DO)    | Medium     | ~5€/mo | Yes         | Yes           |
| Railway / Render    | Easy       | ~7€/mo | Yes         | Yes           |
| Home server         | Hard       | Free   | Yes         | With DDNS     |

### 19.3 Docker Compose (proponowany)

```yaml
version: "3.8"

services:
  geminicli2api:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8888:8888"
    volumes:
      - ./accounts:/app/accounts:ro
      - ./working_space:/app/working_space
    environment:
      - HOST=0.0.0.0
      - PORT=8888
      - GEMINI_AUTH_PASSWORD=${GEMINI_AUTH_PASSWORD}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8888/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### 19.4 Dockerfile (proponowany)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev

COPY server/ server/
COPY apps/ apps/
COPY start.py .

EXPOSE 8888

CMD ["uv", "run", "start.py"]
```

______________________________________________________________________

## 20. DOKUMENTACJA I DX

### 20.1 Istniejąca dokumentacja

| Dokument     | Status  | Jakość |
| ------------ | ------- | ------ |
| README.md    | ✓       | 8/10   |
| Code docs    | Partial | 6/10   |
| API docs     | Auto    | 7/10   |
| CHANGELOG    | ✗       | —      |
| CONTRIBUTING | ✗       | —      |

### 20.2 Potrzebne dokumenty

1. **CHANGELOG.md** — historia zmian per wersja
2. **CONTRIBUTING.md** — jak kontrybuować
3. **API.md** — pełna dokumentacja endpointów z przykładami
4. **ARCHITECTURE.md** — diagram klas, sequence diagrams
5. **TROUBLESHOOTING.md** — FAQ + typowe problemy
6. **SECURITY.md** — polityka bezpieczeństwa
7. **`.env.example`** — template zmiennych środowiskowych

### 20.3 DX (Developer Experience) improvements

1. **Makefile / Justfile** — `make dev`, `make test`, `make lint`
2. **Pre-commit hooks** — ruff, mypy, pytest
3. **CI/CD** — GitHub Actions (lint, test, build)
4. **Devcontainer** — VS Code remote containers
5. **Hot reload** — uvicorn --reload w dev mode
6. **Debug config** — launch.json for VS Code

### 20.4 Proponowany `.env.example`

```env
# Server
HOST=127.0.0.1
PORT=8888
GEMINI_AUTH_PASSWORD=change_me_to_strong_password

# Optional: Override credential file path
# GOOGLE_APPLICATION_CREDENTIALS=oauth_creds.json

# Optional: Inline credentials JSON
# GEMINI_CREDENTIALS={"refresh_token": "...", ...}

# Optional: Google Cloud Project ID
# GOOGLE_CLOUD_PROJECT=my-project-123
```

______________________________________________________________________

## 21. PODSUMOWANIE I WNIOSKI

### 21.1 Co zostało zrobione w tej sesji

1. ✅ **Zaktualizowano modele** — usunięto 7 wycofanych preview modeli, zostawiono 6 zweryfikowanych
2. ✅ **Dodano `--list-models`** — CLI command do wylistowania modeli i wariantów
3. ✅ **Hardened server** — timeouty, request_id, JSON errors, lepsze logi
4. ✅ **Hardened translator** — MAX_RETRIES=10, write_lock, shutil copy, partial saves
5. ✅ **Bug audit** — naprawiono 6+ bugów (onboarding timeout, systemInstruction, thinkingConfig, removesuffix, password masking, timeouts)
6. ✅ **Przetestowano modele** — 5/6 działa (gemini-3-pro-preview 429 = Google capacity)
7. ✅ **Napisano .gitignore** — kompletny, chroni secrets i dane robocze
8. ✅ **Napisano ten brainstorm** — ~1000 linii analizy i planów

### 21.2 Top 5 priorytetów na przyszłość

1. **Fix race conditions** — token refresh/save in lock, auth globals sync
2. **Replace requests → httpx** — native async, connection pooling
3. **Unit tests** — minimum 50 testów, pokrycie krytycznych ścieżek
4. **Docker** — containerization dla łatwego deploymentu
5. **Web UI** — dashboard do monitoringu + translator frontend

### 21.3 Architektoniczne decyzje do podjęcia

| Decyzja       | Opcje                 | Rekomendacja        |
| ------------- | --------------------- | ------------------- |
| HTTP library  | requests vs httpx     | httpx (async)       |
| Logging       | stdlib vs structlog   | structlog (JSON)    |
| Config        | dataclass vs pydantic | pydantic-settings   |
| DB (cache/TM) | SQLite vs Redis       | SQLite (simple)     |
| Frontend      | React vs Svelte       | Svelte (simple)     |
| Deployment    | Docker vs systemd     | Docker              |
| CI            | GH Actions vs none    | GH Actions          |
| Auth          | Password vs API keys  | API keys (per user) |

### 21.4 Końcowa ocena projektu

**Mocne strony**:

- Innowacyjny koncept (darmowe Gemini API)
- Czysta architektura warstwowa
- Działający multi-account z rotation
- Dual format (OpenAI + Gemini native)
- Zintegrowany translator

**Słabe strony**:

- Brak testów jednostkowych
- Synchronous HTTP library (requests)
- Race conditions w auth/accounts
- Brak dokumentacji technicznej
- Brak CI/CD

**Ocena**: **7/10** — solidny PoC, potrzebuje production-grade hardening

**Potencjał**: **9/10** — unikalny na rynku, duże możliwości rozwoju

______________________________________________________________________

## APPENDIX A: PEŁNA LISTA PLIKÓW

```
geminicli2api/
├── .env                           ← Zmienne środowiskowe (gitignored)
├── .gitignore                     ← Nowy, kompletny
├── pyproject.toml                 ← Konfiguracja projektu (uv)
├── README.md                      ← Dokumentacja użytkownika
├── start.py                       ← Root launcher (argparse)
├── test_all_models.py             ← Test wszystkich modeli (gitignored)
├── test_concurrency.py            ← Test współbieżności (gitignored)
├── uv.lock                        ← Lock file (gitignored)
│
├── accounts/                      ← OAuth credentials (gitignored)
│   ├── .gitkeep
│   ├── account_1.json
│   ├── account_2.json
│   └── account_3.json
│
├── server/                        ← Proxy API (FastAPI)
│   ├── __init__.py
│   ├── config.py                  ← Konfiguracja centralna (~225 LOC)
│   ├── main.py                    ← Aplikacja FastAPI (~182 LOC)
│   ├── start.py                   ← Server launcher (~60 LOC)
│   ├── auth.py                    ← Autentykacja + OAuth (~466 LOC)
│   ├── accounts_manager.py        ← Multi-account rotation (~265 LOC)
│   ├── google_api_client.py       ← Google API communication (~441 LOC)
│   ├── openai_transformers.py     ← OpenAI ↔ Gemini conversion (~325 LOC)
│   ├── openai_routes.py           ← /v1/chat/completions (~240 LOC)
│   ├── gemini_routes.py           ← /v1beta/* proxy (~109 LOC)
│   ├── models.py                  ← Pydantic models
│   └── utils.py                   ← User agent, metadata helpers
│
├── apps/gemini_translator/        ← Translator CLI
│   ├── __init__.py
│   ├── config.py                  ← TranslatorConfig dataclass (~90 LOC)
│   ├── start.py                   ← Orkiestrator + pipeline (~200 LOC)
│   ├── prompts/                   ← Prompt templates
│   │   ├── prompt_main.txt
│   │   └── prompt_helper.txt
│   └── src/
│       ├── translator.py          ← Core translation engine (~400 LOC)
│       ├── api_client.py          ← httpx client (~155 LOC)
│       ├── formatter.py           ← SRT/TXT processing
│       ├── text_chunker.py        ← Text chunking
│       ├── number_in_words.py     ← Numbers → Polish words
│       └── utils/
│           ├── console.py         ← Rich console
│           └── execution_timer.py ← Timer context manager
│
├── working_space/                 ← User data (gitignored contents)
│   ├── input/                     ← Pliki do tłumaczenia
│   ├── output/                    ← Przetłumaczone SRT
│   ├── output_txt/                ← Przetłumaczone TXT
│   └── temp/                      ← Pliki tymczasowe
│
└── temp/
    └── brain_storm/               ← Ten i inne dokumenty planistyczne
        ├── BRAINSTORM.md           ← Ten plik
        └── BRAINSTORM_SUMMARY.md  ← Skrócone podsumowanie
```

## APPENDIX B: KOMENDY DEVELOPERSKIE

```bash
# Instalacja
uv sync

# Uruchomienie serwera
uv run start.py

# Dodanie konta
uv run start.py --add-account

# Translator
uv run start.py --translate

# Lista modeli
uv run start.py --list-models

# Testy
uv run python test_all_models.py
uv run python test_concurrency.py

# Linting (jeśli zainstalowane)
uv run ruff check .
uv run ruff format .

# Type checking (jeśli zainstalowane)
uv run mypy server/
```

## APPENDIX C: ENVIRONMENT VARIABLES

| Variable                         | Default          | Opis                       |
| -------------------------------- | ---------------- | -------------------------- |
| `HOST`                           | 127.0.0.1        | Server bind address        |
| `PORT`                           | 8888             | Server port                |
| `GEMINI_AUTH_PASSWORD`           | 123456           | API access password        |
| `GOOGLE_APPLICATION_CREDENTIALS` | oauth_creds.json | Legacy single-account file |
| `GEMINI_CREDENTIALS`             | —                | Inline credentials JSON    |
| `GOOGLE_CLOUD_PROJECT`           | —                | Override GCP project ID    |

______________________________________________________________________

*Wygenerowano: 2026-02-15*
*Wersja projektu: 2.0.0*
*Modele: 6 bazowych, 20 wariantów*
*LOC: ~2910*
