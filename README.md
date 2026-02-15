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
uv run start.py --add-account
```

Otworzy się przeglądarka → zaloguj się na konto Google → gotowe.
Dane konta zapisują się w `accounts/`. Możesz dodać wiele kont.

### 3. Uruchomienie serwera proxy

```bash
uv run start.py
```

Serwer startuje na `http://127.0.0.1:8888`.

### 4. Tłumaczenie tekstu

Wrzuć pliki `.txt` lub `.srt` do `working_space/input/`, potem:

```bash
uv run start.py --translate
```

Translator:
1. Automatycznie uruchomi serwer proxy (jeśli nie działa)
2. Sformatuje pliki wejściowe (TXT → SRT z chunkowaniem)
3. Przetłumaczy asynchronicznie (domyślnie 4 równoległe requesty)
4. Zapisze wynik do `working_space/output/`

## Komendy

| Komenda | Opis |
|---------|------|
| `uv run start.py` | Uruchom serwer proxy (port 8888) |
| `uv run start.py --add-account` | Dodaj konto Google (OAuth flow) |
| `uv run start.py --translate` | Uruchom translator CLI |
| `uv run start.py --list-models` | Wyświetl listę wszystkich dostępnych modeli |
| `uv run start.py --help` | Pomoc |

## Konfiguracja translatora

Edytuj `apps/gemini_translator/config.py`:

```python
@dataclass
class TranslatorConfig:
    # Proxy
    proxy_url: str = "http://127.0.0.1:8888"
    proxy_api_key: str = "123456"

    # Model
    model_name: str = "gemini-2.5-flash"     # lub gemini-2.5-pro
    temperature: float = 0.3
    max_output_tokens: int = 65536

    # Tłumaczenie
    translated_line_count: int = 20          # ile linii na grupę
    concurrent_requests: int = 4             # ile równoległych tłumaczeń
    mode: str = "text"                       # text | image | manga | ocr

    # Formatter
    convert_numbers: bool = True             # 1 → jeden, 2 → dwa
    chunk_method: str = "word"               # metoda chunkowania
    chunk_limit: int = 250                   # max znaków na chunk
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

## Struktura projektu

```
geminicli2api/
├── start.py                           ← Root launcher
├── pyproject.toml
├── accounts/                          ← Konta Google OAuth
├── working_space/
│   ├── input/                         ← Pliki do tłumaczenia
│   └── output/                        ← Przetłumaczone pliki
├── server/                            ← Proxy API (FastAPI)
│   ├── main.py                        ← Aplikacja FastAPI
│   ├── config.py                      ← Konfiguracja serwera
│   ├── accounts_manager.py            ← Multi-account rotation
│   ├── auth.py                        ← OAuth + autentykacja
│   ├── google_api_client.py           ← Komunikacja z Gemini
│   ├── openai_routes.py               ← /v1/chat/completions
│   ├── openai_transformers.py         ← OpenAI ↔ Gemini konwersja
│   ├── gemini_routes.py               ← /v1beta/* proxy
│   ├── models.py                      ← Modele Pydantic
│   └── utils.py
└── apps/gemini_translator/            ← Translator CLI
    ├── start.py                       ← Orkiestrator
    ├── config.py                      ← Konfiguracja translatora
    ├── prompts/                       ← Prompty tłumaczeniowe
    └── src/
        ├── translator.py              ← Silnik tłumaczenia
        ├── api_client.py              ← Klient HTTP (httpx)
        ├── formatter.py               ← SRT/TXT processing
        ├── text_chunker.py            ← Chunkowanie tekstu
        └── number_in_words.py         ← Liczby → słowa (PL)
```

## Dostępne modele

| Model | Opis |
|-------|------|
| `gemini-2.5-pro` | Najlepszy do tłumaczeń |
| `gemini-2.5-flash` | Szybki, dobry do testów |
| `gemini-2.0-flash` | Starszy, szybki |
| `gemini-2.5-pro-search` | Z wyszukiwaniem |
| `gemini-2.5-flash-search` | Flash z wyszukiwaniem |

Pełna lista z CLI: `uv run start.py --list-models`
Pełna lista via API: `GET /v1/models`

## Autentykacja API

Serwer akceptuje 4 metody autentykacji:

1. **Bearer token**: `Authorization: Bearer 123456`
2. **Basic auth**: `Authorization: Basic base64(user:123456)`
3. **Query param**: `?key=123456`
4. **Header**: `x-goog-api-key: 123456`

Domyślne hasło: `123456` (zmień via `GEMINI_AUTH_PASSWORD` w `.env`)

## Licencja

MIT