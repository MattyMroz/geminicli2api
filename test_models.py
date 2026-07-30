"""
Test modeli — bezpośredni (bez proxy, bez rotacji).

Sprawdza, które modele Gemini faktycznie odpowiadają przez Google CodeAssist API.
Używa pierwszego działającego konta z accounts/. Każdy model testowany osobno
przez generateContent.

    uv run test_models.py                  → wszystkie modele bazowe z config + z README
    uv run test_models.py gemini-2.5-pro   → tylko wskazane modele
"""

import glob
import json
import os
import platform
import sys
import time

import requests
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials

# --- Konfiguracja ---
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_DIR = os.path.join(ROOT_DIR, "accounts")
ENDPOINT = "https://cloudcode-pa.googleapis.com"
TIMEOUT = 60
CLI_VERSION = "0.1.5"
SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

# Modele bazowe pobierane z server/config.py (źródło prawdy proxy).
# Dodatkowo dorzucamy modele wymienione w README, ale nieobecne w config,
# żeby zweryfikować rozbieżność dokumentacji vs. realnej dostępności.
sys.path.insert(0, os.path.join(ROOT_DIR, "server"))
try:
    import config as server_config
    CONFIG_MODELS = [m["name"].replace("models/", "") for m in server_config.BASE_MODELS]
except Exception:
    CONFIG_MODELS = []

README_ONLY = ["gemini-2.0-flash"]  # w README, brak w config.BASE_MODELS

_UA = f"GeminiCLI/{CLI_VERSION} ({platform.system()}; {platform.machine()})"
_PLAT_MAP = {
    ("DARWIN", True): "DARWIN_ARM64", ("DARWIN", False): "DARWIN_AMD64",
    ("LINUX", True): "LINUX_ARM64", ("LINUX", False): "LINUX_AMD64",
    ("WINDOWS", False): "WINDOWS_AMD64",
}
_PLAT = _PLAT_MAP.get(
    (platform.system().upper(), platform.machine().upper() in ("ARM64", "AARCH64")),
    "PLATFORM_UNSPECIFIED",
)


def _meta(project_id=None):
    return {"ideType": "IDE_UNSPECIFIED", "platform": _PLAT, "pluginType": "GEMINI", "duetProject": project_id}


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": _UA}


# --- Ładowanie konta (jak w test_accounts.py) ---

def load_account(filepath: str):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not data.get("refresh_token"):
        return None, None
    cd = data.copy()
    if "access_token" in cd and "token" not in cd:
        cd["token"] = cd["access_token"]
    if "scope" in cd and "scopes" not in cd:
        cd["scopes"] = cd["scope"].split()
    if "expiry" in cd:
        exp = cd["expiry"]
        if isinstance(exp, str) and ("+00:00" in exp or "Z" in exp):
            try:
                from datetime import datetime, timezone
                parsed = datetime.fromisoformat(exp.replace("Z", "+00:00") if exp.endswith("Z") else exp)
                cd["expiry"] = parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                del cd["expiry"]
    creds = Credentials.from_authorized_user_info(cd, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
    return creds, data.get("project_id")


def discover_project_id(creds):
    r = requests.post(
        f"{ENDPOINT}/v1internal:loadCodeAssist",
        json={"metadata": _meta()}, headers=_headers(creds.token), timeout=30,
    )
    r.raise_for_status()
    pid = r.json().get("cloudaicompanionProject")
    if not pid:
        raise ValueError("Brak cloudaicompanionProject w odpowiedzi")
    return pid


def onboard(creds, project_id):
    r = requests.post(
        f"{ENDPOINT}/v1internal:loadCodeAssist",
        json={"cloudaicompanionProject": project_id, "metadata": _meta(project_id)},
        headers=_headers(creds.token), timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("currentTier"):
        return
    tier = next((t for t in data.get("allowedTiers", []) if t.get("isDefault")), None)
    if not tier:
        tier = {"id": "legacy-tier", "userDefinedCloudaicompanionProject": True}
    payload = {"tierId": tier.get("id"), "cloudaicompanionProject": project_id, "metadata": _meta(project_id)}
    for _ in range(24):
        resp = requests.post(
            f"{ENDPOINT}/v1internal:onboardUser",
            json=payload, headers=_headers(creds.token), timeout=30,
        )
        resp.raise_for_status()
        if resp.json().get("done"):
            return
        time.sleep(5)
    raise TimeoutError("Onboarding timeout")


def test_model(creds, project_id, model: str):
    """Wyślij testowy generateContent dla danego modelu. Zwraca (ok, info)."""
    payload = {
        "model": model,
        "project": project_id,
        "request": {
            "contents": [{"role": "user", "parts": [{"text": "Say hi"}]}],
            "generationConfig": {"maxOutputTokens": 16},
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
        },
    }
    r = requests.post(
        f"{ENDPOINT}/v1internal:generateContent",
        json=payload, headers=_headers(creds.token), timeout=TIMEOUT,
    )
    if r.status_code != 200:
        try:
            body = r.json()
            msg = body.get("error", {}).get("message", "")
            status = body.get("error", {}).get("status", "")
            return False, f"HTTP {r.status_code} {status}: {msg[:70]}"
        except Exception:
            return False, f"HTTP {r.status_code}: {r.text[:70]}"
    parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = next((p["text"].strip()[:40] for p in parts if p.get("text")), "(ok, brak tekstu)")
    return True, text


def pick_account():
    """Załaduj pierwsze działające konto. Onboarding nieblokujący —
    konto z gotowym project_id i tak próbujemy użyć do generateContent."""
    files = sorted(glob.glob(os.path.join(ACCOUNTS_DIR, "*.json")))
    for fp in files:
        try:
            creds, project_id = load_account(fp)
            if not creds:
                continue
            if not project_id:
                project_id = discover_project_id(creds)
            try:
                onboard(creds, project_id)
            except Exception as e:
                print(f" (onboarding {os.path.basename(fp)} nieudany, próbuję dalej: {str(e)[:80]})")
            return os.path.basename(fp), creds, project_id
        except Exception as e:
            print(f" (pomijam {os.path.basename(fp)}: {str(e)[:80]})")
    return None, None, None


def main():
    args = sys.argv[1:]
    if args:
        models = args
    else:
        # config + README-only, bez duplikatów, zachowując kolejność
        seen = set()
        models = []
        for m in CONFIG_MODELS + README_ONLY:
            if m not in seen:
                seen.add(m)
                models.append(m)

    if not models:
        print("Brak modeli do przetestowania.")
        exit(1)

    name, creds, project_id = pick_account()
    if not creds:
        print("Brak działającego konta w accounts/")
        exit(1)

    print(f"\n Test {len(models)} modeli  konto: {name}  project: {project_id}\n")
    ok = 0
    t0 = time.perf_counter()
    for model in models:
        src = "config" if model in CONFIG_MODELS else "README"
        t1 = time.perf_counter()
        try:
            success, info = test_model(creds, project_id, model)
        except Exception as e:
            success, info = False, str(e)[:70]
        dt = time.perf_counter() - t1
        mark = "v" if success else "x"
        if success:
            ok += 1
        print(f" {mark}  {dt:>4.1f}s  [{src:>6}]  {model:<32}  {info}")

    print(f"\n {ok}/{len(models)} OK  {time.perf_counter() - t0:.0f}s\n")
    exit(0 if ok == len(models) else 1)


if __name__ == "__main__":
    main()
