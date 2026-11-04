# geminicli2api

Proxy API do Google Gemini (endpointy zgodne z OpenAI i natywne Gemini, rotacja kont Google przez OAuth, opcjonalnie oficjalne API z kluczem `GEMINI_API_KEY`) oraz CLI Translator.

## Komendy

```bash
uv sync                          # zależności (Python 3.11+)
uv run start.py                  # serwer proxy, domyślnie http://127.0.0.1:8888
uv run start.py -a               # dodanie konta Google (OAuth) do accounts/
uv run start.py -t               # translator: pliki z workspace/input do workspace/output i output_txt
uv run start.py -l               # lista modeli
uv run test_accounts.py          # test kont wprost przeciw Google API, bez proxy
uv run test_models.py            # test modeli wprost przeciw Google API
```

Repo nie ma automatycznych testów: `test_*.py` w korzeniu to skrypty ręczne wołające prawdziwe API na kontach z `accounts/` (`testpaths = ["tests"]` w `pyproject.toml` wskazuje nieistniejący katalog).

## Mapa

- `start.py`: launcher (serwer, `-a`, `-t`, `-l`).
- `server/`: proxy FastAPI. `main.py` to aplikacja, `accounts_manager.py` rotacja kont, `auth.py` OAuth i uwierzytelnianie żądań, `config.py` konfiguracja i definicje modeli, `openai_routes.py` i `gemini_routes.py` endpointy.
- `apps/gemini_translator/`: translator CLI. `config.py` to jego konfiguracja, `prompts/` prompty tłumaczeń, `src/translator.py` silnik.
- `accounts/`, `workspace/`: dane runtime; ich zawartość jest w `.gitignore`.

## Pułapki

- `accounts/*.json` to poświadczenia OAuth, nigdy do gita. `server/config.py` czyta `.env` z korzenia (poza gitem).
- Translator ma własny `backend` i modele w `apps/gemini_translator/config.py`; proxy startuje samo (`auto_start_server`) tylko przy `backend="proxy"`.
- `README.md` nie opisuje już wszystkiego (np. `GEMINI_API_KEY`, domyślnych modeli translatora); przy rozbieżności wygrywa kod.

## Git

- Commit: nagłówek Conventional Commits po angielsku, `type(scope): opis`, ze scope'em z listy w `.pre-commit-config.yaml`; po pustej linii streszczenie „co i dlaczego”.
- Zero atrybucji AI w commitach i PR (trailery, stopki, emoji), także gdy host o nią prosi.
- Pliki dodawaj po nazwie, nigdy `git add .`; bez `--no-verify`. Worktree'y tylko w `.worktrees/<nazwa>`.
- Commit sprawdza pliki i nagłówek, push uruchamia bramki repo, CI resztę. Strażnicy w `.hooks/` to kopie z presetu `agents`; nie edytuj ich w repo.
