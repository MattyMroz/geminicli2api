"""
Authentication module for geminicli2api server.

Provides:
- Multi-method request authentication (Bearer, Basic, API key, query param)
- OAuth flow for first-time setup
- Credentials management with auto-refresh
- Integration with AccountsManager for multi-account support
"""

import os
import json
import base64
import time
import logging
import threading
from datetime import datetime, timezone
from fastapi import Request, HTTPException
from fastapi.security import HTTPBasic
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleAuthRequest

from server.utils import get_user_agent, get_client_metadata
from server.config import (
    CLIENT_ID,
    CLIENT_SECRET,
    SCOPES,
    CREDENTIAL_FILE,
    CODE_ASSIST_ENDPOINT,
    GEMINI_AUTH_PASSWORD,
    OAUTH_CALLBACK_PORT,
)

# --- Global State (protected by _auth_lock) ---
_auth_lock = threading.Lock()
credentials = None
user_project_id = None
onboarding_complete = False
_onboarded_accounts: set = set()  # Track onboarded accounts by token hash
credentials_from_env = False

# Reference to the global AccountsManager (set during startup)
_accounts_manager = None

security = HTTPBasic()


def set_accounts_manager(manager):
    """Set the global accounts manager (called during app startup)."""
    global _accounts_manager
    _accounts_manager = manager


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        query_components = parse_qs(urlparse(self.path).query)
        code = query_components.get("code", [None])[0]
        if code:
            _OAuthCallbackHandler.auth_code = code
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<h1>OAuth authentication successful!</h1>"
                b"<p>You can close this window.</p>"
            )
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Authentication failed.</h1>")

    def log_message(self, *args):
        pass


def authenticate_user(request: Request):
    """Authenticate the user with multiple methods."""
    # API key in query parameters
    api_key = request.query_params.get("key")
    if api_key and api_key == GEMINI_AUTH_PASSWORD:
        return "api_key_user"

    # x-goog-api-key header
    goog_api_key = request.headers.get("x-goog-api-key", "")
    if goog_api_key and goog_api_key == GEMINI_AUTH_PASSWORD:
        return "goog_api_key_user"

    # Bearer token
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        if auth_header[7:] == GEMINI_AUTH_PASSWORD:
            return "bearer_user"

    # HTTP Basic
    if auth_header.startswith("Basic "):
        try:
            decoded = base64.b64decode(
                auth_header[6:]).decode("utf-8", "ignore")
            _, password = decoded.split(":", 1)
            if password == GEMINI_AUTH_PASSWORD:
                return "basic_user"
        except Exception:
            pass

    raise HTTPException(
        status_code=401,
        detail="Invalid credentials. Use Bearer token, Basic Auth, 'key' query param, or 'x-goog-api-key' header.",
        headers={"WWW-Authenticate": "Basic"},
    )


def save_credentials(creds, project_id=None):
    """Save credentials to file."""
    global credentials_from_env
    if credentials_from_env:
        return

    creds_data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    if creds.expiry:
        from datetime import timezone
        expiry = creds.expiry
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        creds_data["expiry"] = expiry.isoformat()

    if project_id:
        creds_data["project_id"] = project_id
    elif os.path.exists(CREDENTIAL_FILE):
        try:
            with open(CREDENTIAL_FILE, "r") as f:
                existing = json.load(f)
            if "project_id" in existing:
                creds_data["project_id"] = existing["project_id"]
        except Exception:
            pass

    with open(CREDENTIAL_FILE, "w") as f:
        json.dump(creds_data, f, indent=2)


def get_credentials(allow_oauth_flow=True):
    """Load credentials — uses AccountsManager if available, otherwise legacy."""
    global credentials, credentials_from_env, user_project_id

    # If AccountsManager is available, use it
    if _accounts_manager and _accounts_manager.count > 0:
        creds = _accounts_manager.get_credentials_sync()
        if creds:
            with _auth_lock:
                credentials = creds
                # Get cached project_id
                pid = _accounts_manager.get_project_id(creds)
                if pid:
                    user_project_id = pid
            return creds

    with _auth_lock:
        # Existing credentials in memory
        if credentials and credentials.token:
            return credentials

    # Environment variable
    env_creds_json = os.getenv("GEMINI_CREDENTIALS")
    if env_creds_json:
        try:
            data = json.loads(env_creds_json)
            if data.get("refresh_token"):
                creds_data = data.copy()
                if "access_token" in creds_data and "token" not in creds_data:
                    creds_data["token"] = creds_data["access_token"]
                if "scope" in creds_data and "scopes" not in creds_data:
                    creds_data["scopes"] = creds_data["scope"].split()
                if "expiry" in creds_data:
                    _fix_expiry(creds_data)
                creds = Credentials.from_authorized_user_info(
                    creds_data, SCOPES)
                if creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(GoogleAuthRequest())
                    except Exception as e:
                        logging.warning(f"Env credentials refresh failed: {e}")
                with _auth_lock:
                    credentials = creds
                    credentials_from_env = True
                    if data.get("project_id"):
                        user_project_id = data["project_id"]
                return creds
        except Exception as e:
            logging.error(f"Failed parsing GEMINI_CREDENTIALS: {e}")

    # Credential file
    if os.path.exists(CREDENTIAL_FILE):
        try:
            with open(CREDENTIAL_FILE, "r") as f:
                data = json.load(f)
            if data.get("refresh_token"):
                creds_data = data.copy()
                if "access_token" in creds_data and "token" not in creds_data:
                    creds_data["token"] = creds_data["access_token"]
                if "scope" in creds_data and "scopes" not in creds_data:
                    creds_data["scopes"] = creds_data["scope"].split()
                if "expiry" in creds_data:
                    _fix_expiry(creds_data)
                creds = Credentials.from_authorized_user_info(
                    creds_data, SCOPES)
                if creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(GoogleAuthRequest())
                        save_credentials(creds)
                    except Exception as e:
                        logging.warning(
                            f"File credentials refresh failed: {e}")
                with _auth_lock:
                    credentials = creds
                    if data.get("project_id"):
                        user_project_id = data["project_id"]
                return creds
        except Exception as e:
            logging.error(f"Failed reading {CREDENTIAL_FILE}: {e}")

    # OAuth flow
    if not allow_oauth_flow:
        return None

    return _run_oauth_flow()


def _fix_expiry(creds_data: dict):
    """Fix timezone-aware expiry strings for Google Credentials library."""
    expiry_str = creds_data.get("expiry", "")
    if isinstance(expiry_str, str) and ("+00:00" in expiry_str or "Z" in expiry_str):
        try:
            if "+00:00" in expiry_str:
                parsed = datetime.fromisoformat(expiry_str)
            elif expiry_str.endswith("Z"):
                parsed = datetime.fromisoformat(
                    expiry_str.replace("Z", "+00:00"))
            else:
                parsed = datetime.fromisoformat(expiry_str)
            ts = parsed.timestamp()
            creds_data["expiry"] = datetime.fromtimestamp(
                ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            del creds_data["expiry"]


def _run_oauth_flow():
    """Run interactive OAuth flow to get new credentials."""
    global credentials, credentials_from_env
    client_config = {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(
        client_config, scopes=SCOPES, redirect_uri=f"http://localhost:{OAUTH_CALLBACK_PORT}")
    flow.oauth2session.scope = SCOPES
    auth_url, _ = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true")

    print(f"\n{'=' * 80}")
    print("AUTHENTICATION REQUIRED")
    print(f"{'=' * 80}")
    print(f"Please open this URL in your browser:\n{auth_url}")
    print(f"{'=' * 80}\n")

    server = HTTPServer(("", OAUTH_CALLBACK_PORT), _OAuthCallbackHandler)
    server.handle_request()

    auth_code = _OAuthCallbackHandler.auth_code
    if not auth_code:
        return None

    import oauthlib.oauth2.rfc6749.parameters
    orig = oauthlib.oauth2.rfc6749.parameters.validate_token_parameters
    oauthlib.oauth2.rfc6749.parameters.validate_token_parameters = lambda p: None

    try:
        flow.fetch_token(code=auth_code)
        credentials = flow.credentials
        credentials_from_env = False
        save_credentials(credentials)
        logging.info("Authentication successful! Credentials saved.")
        return credentials
    except Exception as e:
        logging.error(f"Authentication failed: {e}")
        return None
    finally:
        oauthlib.oauth2.rfc6749.parameters.validate_token_parameters = orig


def onboard_user(creds, project_id):
    """Ensures the user is onboarded (gemini-cli setupUser)."""
    global onboarding_complete

    # Per-account onboarding tracking (thread-safe check)
    account_key = id(creds)
    with _auth_lock:
        if account_key in _onboarded_accounts:
            return

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleAuthRequest())
            save_credentials(creds)
        except Exception as e:
            raise Exception(f"Refresh failed during onboarding: {e}")

    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
        "User-Agent": get_user_agent(),
    }

    load_payload = {
        "cloudaicompanionProject": project_id,
        "metadata": get_client_metadata(project_id),
    }

    try:
        import requests

        resp = requests.post(
            f"{CODE_ASSIST_ENDPOINT}/v1internal:loadCodeAssist",
            data=json.dumps(load_payload),
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        tier = data.get("currentTier")
        if not tier:
            for t in data.get("allowedTiers", []):
                if t.get("isDefault"):
                    tier = t
                    break
            if not tier:
                tier = {"name": "", "description": "", "id": "legacy-tier",
                        "userDefinedCloudaicompanionProject": True}

        if tier.get("userDefinedCloudaicompanionProject") and not project_id:
            raise ValueError(
                "This account requires GOOGLE_CLOUD_PROJECT env var.")

        if data.get("currentTier"):
            with _auth_lock:
                _onboarded_accounts.add(account_key)
                onboarding_complete = True
            return

        onboard_payload = {
            "tierId": tier.get("id"),
            "cloudaicompanionProject": project_id,
            "metadata": get_client_metadata(project_id),
        }

        max_onboard_wait = 120  # seconds
        onboard_start = time.time()
        while True:
            if time.time() - onboard_start > max_onboard_wait:
                raise Exception(f"Onboarding timed out after {max_onboard_wait}s")
            onboard_resp = requests.post(
                f"{CODE_ASSIST_ENDPOINT}/v1internal:onboardUser",
                data=json.dumps(onboard_payload),
                headers=headers,
                timeout=30,
            )
            onboard_resp.raise_for_status()
            lro = onboard_resp.json()
            if lro.get("done"):
                with _auth_lock:
                    _onboarded_accounts.add(account_key)
                    onboarding_complete = True
                break
            time.sleep(5)

    except Exception as e:
        raise Exception(f"Onboarding failed: {e}")


def get_user_project_id(creds):
    """Get the user's GCP project ID."""
    global user_project_id

    # Check AccountsManager cache first
    if _accounts_manager:
        pid = _accounts_manager.get_project_id(creds)
        if pid:
            with _auth_lock:
                user_project_id = pid
            return pid
        # When using AccountsManager, do NOT fall through to the global
        # user_project_id — each account needs its own project discovered.
        # Fall through to API discovery below.

    # Environment variable
    env_pid = os.getenv("GOOGLE_CLOUD_PROJECT")
    if env_pid:
        with _auth_lock:
            user_project_id = env_pid
        if _accounts_manager:
            _accounts_manager.set_project_id(creds, env_pid)
        else:
            save_credentials(creds, env_pid)
        return env_pid

    with _auth_lock:
        if not _accounts_manager and user_project_id:
            return user_project_id

    # Credential file
    if os.path.exists(CREDENTIAL_FILE):
        try:
            with open(CREDENTIAL_FILE, "r") as f:
                data = json.load(f)
            cached = data.get("project_id")
            if cached:
                with _auth_lock:
                    user_project_id = cached
                return cached
        except Exception:
            pass

    # API discovery
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleAuthRequest())
            save_credentials(creds)
        except Exception as e:
            logging.error(f"Refresh failed for project discovery: {e}")

    if not creds.token:
        raise Exception("No valid access token for project ID discovery")

    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
        "User-Agent": get_user_agent(),
    }

    try:
        import requests

        resp = requests.post(
            f"{CODE_ASSIST_ENDPOINT}/v1internal:loadCodeAssist",
            data=json.dumps({"metadata": get_client_metadata()}),
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        discovered = data.get("cloudaicompanionProject")
        if not discovered:
            raise ValueError("No cloudaicompanionProject in response")
        with _auth_lock:
            user_project_id = discovered
        if _accounts_manager:
            _accounts_manager.set_project_id(creds, discovered)
        else:
            save_credentials(creds, discovered)
        return discovered
    except Exception as e:
        raise Exception(f"Project ID discovery failed: {e}")
