"""
geminicli2api — Root launcher.

Usage:
    uv run start.py                    → Start the proxy server
    uv run start.py --add-account      → Add a new Google account (OAuth)
    uv run start.py --translate        → Run Gemini Translator (auto-starts server)
    uv run start.py --help             → Show help
"""
import sys
import argparse
from pathlib import Path

# Ensure project root on sys.path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))


def main():
    parser = argparse.ArgumentParser(
        description="geminicli2api — Universal Gemini API Proxy + Translator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run start.py                  Start the proxy server on port 8888
  uv run start.py --add-account    Add a Google OAuth account
  uv run start.py --translate      Run the Gemini Translator CLI
        """,
    )
    parser.add_argument(
        "--add-account",
        action="store_true",
        help="Interactively add a new Google OAuth account",
    )
    parser.add_argument(
        "--translate",
        action="store_true",
        help="Run the Gemini Translator (auto-starts server if needed)",
    )

    args = parser.parse_args()

    if args.add_account:
        from server.start import add_account
        add_account()
    elif args.translate:
        import asyncio
        from apps.gemini_translator.start import main as translator_main
        asyncio.run(translator_main())
    else:
        from server.start import start_server
        start_server()


if __name__ == "__main__":
    main()
