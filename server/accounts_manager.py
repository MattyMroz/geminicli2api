"""
AccountsManager — multi-account Google OAuth credentials management.

Loads all *.json credential files from the accounts/ folder,
provides round-robin rotation, auto-refreshes expired tokens,
and supports interactive addition of new accounts.
"""

import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from typing import List, Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request as GoogleAuthRequest

from server.config import (
    ACCOUNTS_DIR,
    CLIENT_ID,
    CLIENT_SECRET,
    CREDENTIAL_FILE,
    SCOPES,
)

logger = logging.getLogger(__name__)


class AccountsManager:
    """Manages multiple Google OAuth accounts with round-robin rotation."""

    def __init__(self, accounts_dir: Optional[str] = None):
        self._accounts_dir = Path(accounts_dir) if accounts_dir else ACCOUNTS_DIR
        self._accounts: List[dict] = []  # [{"file": Path, "creds": Credentials, "project_id": str|None}]
        self._current_index: int = 0
        self._lock = asyncio.Lock()
        self._thread_lock = threading.Lock()  # Thread-safe lock for sync rotation
        self._load_accounts()

    # --- Public API ---

    @property
    def count(self) -> int:
        return len(self._accounts)

    def get_credentials_sync(self) -> Optional[Credentials]:
        """Synchronous version — returns next credentials (rotates). Thread-safe."""
        if not self._accounts:
            return None
        with self._thread_lock:
            account = self._accounts[self._current_index]
            idx = self._current_index
            self._current_index = (self._current_index + 1) % len(self._accounts)
        creds = account["creds"]
        logger.info(f"Using account #{idx + 1} ({account['file'].name})")
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(GoogleAuthRequest())
                self._save_account(account)
                logger.info(f"Refreshed credentials for {account['file'].name}")
            except Exception as e:
                logger.warning(f"Failed to refresh {account['file'].name}: {e}")
        return creds

    async def get_next_credentials(self) -> Optional[Credentials]:
        """Async round-robin rotation with auto-refresh."""
        async with self._lock:
            return self.get_credentials_sync()

    def get_project_id(self, creds: Credentials) -> Optional[str]:
        """Get cached project_id for given credentials."""
        for account in self._accounts:
            if account["creds"] is creds:
                return account.get("project_id")
        return None

    def set_project_id(self, creds: Credentials, project_id: str):
        """Cache project_id for given credentials."""
        for account in self._accounts:
            if account["creds"] is creds:
                account["project_id"] = project_id
                self._save_account(account)
                break

    # --- Loading ---

    def _load_accounts(self):
        """Load all account JSON files from accounts/ directory + legacy oauth_creds.json."""
        self._accounts_dir.mkdir(parents=True, exist_ok=True)

        # Load from accounts/ folder
        json_files = sorted(self._accounts_dir.glob("*.json"))
        for json_file in json_files:
            account = self._load_single_account(json_file)
            if account:
                self._accounts.append(account)
                logger.info(f"Loaded account: {json_file.name}")

        # Fallback: load legacy oauth_creds.json if no accounts found
        if not self._accounts and os.path.exists(CREDENTIAL_FILE):
            account = self._load_single_account(Path(CREDENTIAL_FILE))
            if account:
                self._accounts.append(account)
                logger.info(f"Loaded legacy credentials: {CREDENTIAL_FILE}")

        logger.info(f"AccountsManager: {len(self._accounts)} account(s) loaded")

    def _load_single_account(self, filepath: Path) -> Optional[dict]:
        """Load a single credential JSON file."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not data.get("refresh_token"):
                logger.warning(f"No refresh_token in {filepath.name}, skipping")
                return None

            creds_data = data.copy()

            # Normalize fields
            if "access_token" in creds_data and "token" not in creds_data:
                creds_data["token"] = creds_data["access_token"]
            if "scope" in creds_data and "scopes" not in creds_data:
                creds_data["scopes"] = creds_data["scope"].split()

            # Handle expiry format
            if "expiry" in creds_data:
                expiry_str = creds_data["expiry"]
                if isinstance(expiry_str, str) and ("+00:00" in expiry_str or "Z" in expiry_str):
                    try:
                        from datetime import datetime
                        if "+00:00" in expiry_str:
                            parsed = datetime.fromisoformat(expiry_str)
                        elif expiry_str.endswith("Z"):
                            parsed = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
                        else:
                            parsed = datetime.fromisoformat(expiry_str)
                        import time as _time
                        ts = parsed.timestamp()
                        creds_data["expiry"] = datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ")
                    except Exception:
                        del creds_data["expiry"]

            creds = Credentials.from_authorized_user_info(creds_data, SCOPES)

            # Auto-refresh if expired
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(GoogleAuthRequest())
                    logger.info(f"Auto-refreshed {filepath.name}")
                except Exception as e:
                    logger.warning(f"Could not refresh {filepath.name}: {e}")

            return {
                "file": filepath,
                "creds": creds,
                "project_id": data.get("project_id"),
            }

        except Exception as e:
            logger.error(f"Failed to load {filepath}: {e}")
            return None

    def _save_account(self, account: dict):
        """Save updated credentials back to the JSON file."""
        creds = account["creds"]
        data = {
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
            data["expiry"] = expiry.isoformat()
        if account.get("project_id"):
            data["project_id"] = account["project_id"]
        try:
            with open(account["file"], "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save {account['file']}: {e}")

    # --- Add new account (interactive OAuth flow) ---

    def add_account_interactive(self) -> bool:
        """Run OAuth flow interactively to add a new account."""
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from urllib.parse import urlparse, parse_qs

        class _Handler(BaseHTTPRequestHandler):
            auth_code = None
            def do_GET(self):
                q = parse_qs(urlparse(self.path).query)
                code = q.get("code", [None])[0]
                if code:
                    _Handler.auth_code = code
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<h1>OK! Account added. You can close this window.</h1>")
                else:
                    self.send_response(400)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"<h1>Failed</h1>")
            def log_message(self, *args):
                pass  # silence logs

        client_config = {
            "installed": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

        flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri="http://localhost:8080")
        auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")

        print(f"\n{'=' * 60}")
        print("🔑 DODAWANIE NOWEGO KONTA GOOGLE")
        print(f"{'=' * 60}")
        print(f"Otwórz ten URL w przeglądarce:\n{auth_url}")
        print(f"{'=' * 60}\n")

        server = HTTPServer(("", 8080), _Handler)
        server.handle_request()

        if not _Handler.auth_code:
            print("❌ Nie udało się uzyskać kodu autoryzacji.")
            return False

        # Patch validation
        import oauthlib.oauth2.rfc6749.parameters
        orig = oauthlib.oauth2.rfc6749.parameters.validate_token_parameters
        oauthlib.oauth2.rfc6749.parameters.validate_token_parameters = lambda p: None

        try:
            flow.fetch_token(code=_Handler.auth_code)
            creds = flow.credentials

            # Determine next account number
            self._accounts_dir.mkdir(parents=True, exist_ok=True)
            existing = list(self._accounts_dir.glob("account_*.json"))
            next_num = len(existing) + 1
            filepath = self._accounts_dir / f"account_{next_num}.json"

            account = {"file": filepath, "creds": creds, "project_id": None}
            self._save_account(account)
            self._accounts.append(account)

            print(f"✅ Konto dodane jako: {filepath}")
            print(f"📊 Łącznie kont: {len(self._accounts)}")
            return True
        except Exception as e:
            print(f"❌ Błąd: {e}")
            return False
        finally:
            oauthlib.oauth2.rfc6749.parameters.validate_token_parameters = orig
