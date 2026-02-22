"""
Test kont — bezpośredni (bez proxy, bez rotacji).

Każde konto ładowane osobno z pliku JSON i testowane wprost z Google API.

    uv run test_accounts.py         → wszystkie konta
    uv run test_accounts.py 4       → tylko #4
    uv run test_accounts.py 2 5 8   → #2, #5, #8
"""

import json
import glob
import os
import platform
import re
import sys
import time

import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest

# --- Konfiguracja ---
ACCOUNTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "accounts")
ENDPOINT = "https://cloudcode-pa.googleapis.com"
MODEL = "gemini-2.5-flash"
TIMEOUT = 60
CLI_VERSION = "0.1.5"
SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

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


# --- Ładowanie konta ---

def load_account(filepath: str):
    """Załaduj credentials i project_id z pliku JSON."""
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


# --- API Google ---

def discover_project_id(creds):
    """Odkryj project_id przez loadCodeAssist."""
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
    """Onboarding konta."""
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


def send_request(creds, project_id):
    """Wyślij testowy generateContent. Raises ValidationRequiredError przy 403 VALIDATION_REQUIRED."""
    payload = {
        "model": MODEL,
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
    if r.status_code == 403:
        body = r.json()
        for detail in body.get("error", {}).get("details", []):
            if detail.get("reason") == "VALIDATION_REQUIRED":
                url = detail.get("metadata", {}).get("validation_url", "")
                raise ValidationRequiredError(url)
    r.raise_for_status()
    parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return next((p["text"].strip()[:60] for p in parts if p.get("text")), "(ok)")


class ValidationRequiredError(Exception):
    def __init__(self, url: str):
        self.url = url
        super().__init__("Wymagana weryfikacja konta Google")


# --- Test ---

def test_account(filepath: str, num: int) -> bool:
    name = os.path.basename(filepath)
    t0 = time.perf_counter()
    try:
        creds, project_id = load_account(filepath)
        if not creds:
            print(f" x #{num:>2}  {name}  brak refresh_token")
            return False

        if not project_id:
            project_id = discover_project_id(creds)

        onboard(creds, project_id)
        text = send_request(creds, project_id)
        dt = time.perf_counter() - t0
        print(f" v #{num:>2}  {dt:.1f}s  {name}  {text}")
        return True

    except ValidationRequiredError as e:
        dt = time.perf_counter() - t0
        print(f" x #{num:>2}  {dt:.1f}s  {name}  Wymagana weryfikacja konta Google")
        if e.url:
            print(f"        Otworz w przegladarce (zalogowany na to konto):")
            print(f"        {e.url}")
        return False

    except Exception as e:
        dt = time.perf_counter() - t0
        print(f" x #{num:>2}  {dt:.1f}s  {name}  {str(e)[:80]}")
        return False


def _natural_sort_key(path):
    """Sortowanie numeryczne: account_2 < account_10 < account_11."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', os.path.basename(path))]


def main():
    files = sorted(glob.glob(os.path.join(ACCOUNTS_DIR, "*.json")), key=_natural_sort_key)
    total = len(files)
    if total == 0:
        print("Brak kont w accounts/")
        exit(1)

    args = sys.argv[1:]
    if args:
        targets = [int(a) for a in args if a.isdigit() and 1 <= int(a) <= total]
        if not targets:
            print(f"Podaj nr konta 1-{total}")
            exit(1)
    else:
        targets = list(range(1, total + 1))

    print(f"\n Test {len(targets)}/{total} kont  {MODEL}\n")
    ok = 0
    t0 = time.perf_counter()

    for num in targets:
        if test_account(files[num - 1], num):
            ok += 1

    print(f"\n {ok}/{len(targets)} OK  {time.perf_counter() - t0:.0f}s\n")
    exit(0 if ok == len(targets) else 1)


if __name__ == "__main__":
    main()
