"""
geminicli2api Server Launcher

Usage:
    uv run server/start.py                  — Start the API server
    uv run server/start.py --add-account    — Add a new Google account via OAuth
"""
from dotenv import load_dotenv
import sys
import os

# Ensure project root is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

load_dotenv(os.path.join(ROOT_DIR, ".env"))


def add_account():
    """Interactive OAuth flow to add a new Google account."""
    from server.config import ACCOUNTS_DIR, CREDENTIAL_FILE
    from server.accounts_manager import AccountsManager

    os.makedirs(ACCOUNTS_DIR, exist_ok=True)

    manager = AccountsManager(str(ACCOUNTS_DIR))
    print(f"\nCurrently loaded accounts: {manager.count}")
    print("Starting OAuth flow to add a new account...\n")
    manager.add_account_interactive()
    print(f"\nTotal accounts after addition: {manager.count}")


def start_server():
    """Start the uvicorn server."""
    import uvicorn
    from server.config import HOST, PORT

    print(f"\n{'=' * 60}")
    print(f"  geminicli2api — Universal Gemini API Proxy")
    print(f"  Starting on http://{HOST}:{PORT}")
    print(f"{'=' * 60}\n")

    uvicorn.run(
        "server.main:app",
        host=HOST,
        port=int(PORT),
        log_level="info",
        reload=False,
    )


def main():
    if "--add-account" in sys.argv:
        add_account()
    else:
        start_server()


if __name__ == "__main__":
    main()
