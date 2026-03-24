# geminicli2api v2.0

Uniwersalny proxy API do Google Gemini z multi-account OAuth + CLI Translator.

**Darmowe korzystanie z Gemini** — bez kluczy API, tylko konta Google.

## Wymagania

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — menedżer pakietów

```bash
pip install uv
```

## Szybki start

### 1. Instalacja zależności

```bash
cd geminicli2api
uv sync
```

### 2. Dodanie konta Google (OAuth)

```bash
uv run start.py --add-account   # lub: uv run start.py -a
```

Otworzy się przeglądarka → zaloguj się na konto Google → gotowe.
Dane konta zapisują się w `accounts/`. Możesz dodać wiele kont.

### 3. Uruchomienie serwera proxy

```bash
uv run start.py
```

Serwer startuje na `http://127.0.0.1:8888`.

### 4. Tłumaczenie tekstu

Wrzuć pliki `.txt` lub `.srt` do `workspace/input/`, potem:

```bash
uv run start.py --translate   # lub: uv run start.py -t
```

Translator:
1. Automatycznie uruchomi serwer proxy (jeśli nie działa)
2. Sformatuje pliki wejściowe (TXT → SRT z chunkowaniem)
3. Przetłumaczy asynchronicznie (domyślnie 20 równoległych requestów)
4. Zapisze wynik do `workspace/output/` (SRT) i `workspace/output_txt/` (TXT)

## Komendy

| Komenda | Skrót | Opis |
|---------|-------|------|
| `uv run start.py` | — | Uruchom serwer proxy (port 8888) |
| `uv run start.py --add-account` | `-a` | Dodaj konto Google (OAuth flow) |
| `uv run start.py --translate` | `-t` | Uruchom translator CLI |
| `uv run start.py --list-models` | `-l` | Wyświetl listę wszystkich dostępnych modeli |
| `uv run start.py --help` | `-h` | Pomoc |

> **Tip**: Używaj skrótów dla szybszego wywołania, np. `uv run start.py -t` zamiast `uv run start.py --translate`.

## Konfiguracja translatora

Edytuj `apps/gemini_translator/config.py`:

```python
@dataclass
class TranslatorConfig:
    # Proxy
    proxy_url: str = "http://127.0.0.1:8888"
    proxy_api_key: str = "123456"

    # Model
    model_name: str = "gemini-2.5-pro"
    temperature: float = 0.3
    top_p: float = 1.0
    max_output_tokens: int = 65536

    # Tłumaczenie
    translated_line_count: int = 20          # ile linii na grupę
    concurrent_requests: int = 20            # ile równoległych tłumaczeń
    mode: str = "text"                       # text | image | manga | subtitle | ocr

    # Formatter / pre-processing
    convert_numbers: bool = True             # 1 → jeden, 2 → dwa
    chunk_method: str = "word"               # metoda chunkowania
    chunk_limit: int = 250                   # max znaków na chunk
    sentence_length: int = 750               # max długość zdania

    # Ścieżki
    input_folder: str = "workspace/input"
    output_folder: str = "workspace/output"
    output_txt_folder: str = "workspace/output_txt"
    prompts_folder: str = "apps/gemini_translator/prompts"

    # Zarządzanie serwerem
    auto_start_server: bool = True           # automatyczny start proxy
    server_startup_timeout: int = 15         # timeout na start serwera (sek.)
```

## API Endpoints

### OpenAI-compatible

```bash
# Chat Completions
curl http://127.0.0.1:8888/v1/chat/completions \
  -H "Authorization: Bearer 123456" \
  -H "Content-Type: application/json" \
  -d '{"model": "gemini-2.5-flash", "messages": [{"role": "user", "content": "Hello"}]}'

# Lista modeli
curl http://127.0.0.1:8888/v1/models -H "Authorization: Bearer 123456"
```

### Native Gemini

```bash
curl http://127.0.0.1:8888/v1beta/models -H "x-goog-api-key: 123456"
```

### Health check

```bash
curl http://127.0.0.1:8888/health
```

## Multi-account

Dodaj wiele kont Google, serwer automatycznie rotuje między nimi (round-robin):

```bash
uv run start.py --add-account   # konto 1
uv run start.py --add-account   # konto 2
uv run start.py --add-account   # konto 3
```

Pliki kont: `accounts/*.json`

### Wymagania konta Google

> **Nie potrzebujesz** Google Cloud Console, AI Studio (`ai.dev`), kluczy API ani żadnych projektów GCP tworzonych ręcznie. Wszystko działa wyłącznie przez konto Google.

By konto działało, muszą być spełnione **wszystkie** poniższe warunki:

1. **Konto Google z numerem telefonu** — Google wymaga weryfikacji SMS lub przez urządzenie Android przy pierwszym użyciu API. Konta bez numeru telefonu lub niezweryfikowane zwracają błąd `403 Verify your account to continue`.

2. **Aktywacja Gemini Code Assist** — konto musi być zarejestrowane w programie *Gemini Code Assist for individuals* (free tier). Odbywa się to automatycznie przy `uv run start.py -a`.

3. **`project_id` w pliku JSON** — każde konto po onboardingu otrzymuje identyfikator projektu GCP **przydzielany automatycznie przez Google** (nie tworzysz go sam). Jest on zapisywany automatycznie w `accounts/account_N.json`.

4. **Akceptacja warunków Gemini Code Assist** — przy pierwszym logowaniu przez `start.py -a` przeglądarka przeprowadzi przez ten proces automatycznie.

### Testowanie kont

```bash
uv run test_accounts.py         # sprawdź wszystkie konta
uv run test_accounts.py 3       # sprawdź tylko konto #3
uv run test_accounts.py 1 4 7   # sprawdź konta #1, #4, #7
```

Test łączy się **bezpośrednio** z Google API (z pominięciem proxy) — każde konto testowane osobno, bez rotacji.

Przykładowy wynik:

```
 Test 3/3 kont  gemini-2.5-flash

 v # 1  2.1s  account_1.json  Hi there!
 v # 2  1.8s  account_2.json  Hi there!
 x # 3  1.2s  account_3.json  Wymagana weryfikacja konta Google
        Otworz w przegladarce (zalogowany na to konto):
        https://accounts.google.com/signin/continue?...

 2/3 OK  5s
```

Jeśli konto wymaga weryfikacji — otwórz podany link w przeglądarce zalogowanej na to konto Google i przejdź weryfikację SMS. Po weryfikacji konto działa od razu.

## Struktura projektu

```
geminicli2api/
├── start.py                           ← Root launcher
├── test_accounts.py                   ← Test kont Google (bezposredni, bez proxy)
├── pyproject.toml
├── .env                               ← Zmienne środowiskowe
├── accounts/                          ← Konta Google OAuth
├── workspace/
│   ├── input/                         ← Pliki do tłumaczenia
│   ├── output/                        ← Przetłumaczone pliki (SRT)
│   └── output_txt/                    ← Przetłumaczone pliki (TXT)
├── server/                            ← Proxy API (FastAPI)
│   ├── main.py                        ← Aplikacja FastAPI
│   ├── start.py                       ← Start/stop serwera
│   ├── config.py                      ← Konfiguracja + definicje modeli
│   ├── accounts_manager.py            ← Multi-account rotation
│   ├── auth.py                        ← OAuth + autentykacja
│   ├── google_api_client.py           ← Komunikacja z Gemini API
│   ├── openai_routes.py               ← /v1/chat/completions, /v1/models
│   ├── openai_transformers.py         ← OpenAI ↔ Gemini konwersja
│   ├── gemini_routes.py               ← /v1beta/* proxy
│   ├── models.py                      ← Modele Pydantic
│   └── utils.py                       ← Narzędzia pomocnicze
└── apps/gemini_translator/            ← Translator CLI
    ├── start.py                       ← Orkiestrator
    ├── config.py                      ← Konfiguracja translatora
    ├── prompts/                       ← Prompty tłumaczeniowe
    │   ├── prompt_main.txt            ← Główny prompt
    │   └── prompt_helper.txt          ← Prompt pomocniczy
    └── src/
        ├── translator.py              ← Silnik tłumaczenia
        ├── api_client.py              ← Klient HTTP (httpx)
        ├── formatter.py               ← SRT/TXT processing
        ├── text_chunker.py            ← Chunkowanie tekstu
        ├── number_in_words.py         ← Liczby → słowa (PL)
        └── utils/
            ├── console.py             ← Rich console setup
            └── execution_timer.py     ← Timer wykonania
```

## Dostępne modele

### Modele bazowe

| Model | Opis |
|-------|------|
| `gemini-2.0-flash` | Starszy, szybki multimodalny |
| `gemini-2.5-flash` | Szybki, dobry do testów |
| `gemini-2.5-flash-lite` | Lekka wersja Flash — najszybszy |
| `gemini-2.5-pro` | Najlepszy do tłumaczeń |
| `gemini-3-flash-preview` | Preview nowej generacji Flash |
| `gemini-3-pro-preview` | Preview najsilniejszego modelu |

### Warianty

Każdy model bazowy (oprócz `gemini-2.0-flash` i `gemini-2.5-flash-lite`) ma warianty thinking:

| Sufiks | Opis |
|--------|------|
| `-search` | Z wyszukiwaniem Google (grounding) |
| `-nothinking` | Wyłączony tryb myślenia (szybsze odpowiedzi) |
| `-maxthinking` | Maksymalny budżet myślenia (najlepsze odpowiedzi) |

Przykłady: `gemini-2.5-pro-search`, `gemini-2.5-flash-nothinking`, `gemini-3-pro-preview-maxthinking`

Pełna lista z CLI: `uv run start.py --list-models`
Pełna lista via API: `GET /v1/models`

## Zmienne środowiskowe

Konfiguracja w pliku `.env`:

| Zmienna | Domyślnie | Opis |
|---------|-----------|------|
| `GEMINI_AUTH_PASSWORD` | `123456` | Hasło do autentykacji API |
| `HOST` | `127.0.0.1` | Adres serwera |
| `PORT` | `8888` | Port serwera |
| `OAUTH_CALLBACK_PORT` | `8080` | Port callback OAuth |
| `GOOGLE_APPLICATION_CREDENTIALS` | `oauth_creds.json` | Ścieżka do pliku credentials (legacy) |
| `GEMINI_CREDENTIALS` | — | JSON credentials bezpośrednio w zmiennej (opcjonalnie) |

## Autentykacja API

Serwer akceptuje 4 metody autentykacji:

1. **Bearer token**: `Authorization: Bearer 123456`
2. **Basic auth**: `Authorization: Basic base64(user:123456)`
3. **Query param**: `?key=123456`
4. **Header**: `x-goog-api-key: 123456`

Domyślne hasło: `123456` (zmień via `GEMINI_AUTH_PASSWORD` w `.env`)

## Licencja

MIT