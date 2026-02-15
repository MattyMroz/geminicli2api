"""
geminicli2api — Root launcher.

Usage:
    uv run start.py                    → Start the proxy server
    uv run start.py --add-account      → Add a new Google account (OAuth)
    uv run start.py --translate        → Run Gemini Translator (auto-starts server)
    uv run start.py --list-models      → List all supported models
    uv run start.py --help             → Show help
"""
import sys
import argparse
from pathlib import Path

# Ensure project root on sys.path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))


def list_models():
    """List all supported models with details."""
    from server.config import BASE_MODELS, SUPPORTED_MODELS

    print(f"\n{'=' * 70}")
    print("  geminicli2api — Supported Models")
    print(f"{'=' * 70}")

    # Base models
    print(f"\n  BASE MODELS ({len(BASE_MODELS)}):")
    print(f"  {'─' * 66}")
    for m in sorted(BASE_MODELS, key=lambda x: x["name"]):
        name = m["name"].replace("models/", "")
        tokens_in = f"{m['inputTokenLimit']:,}"
        tokens_out = f"{m['outputTokenLimit']:,}"
        print(f"  • {name:<45} in:{tokens_in:>10}  out:{tokens_out:>7}")

    # All variants
    print(f"\n  ALL VARIANTS (incl. -search, -nothinking, -maxthinking): {len(SUPPORTED_MODELS)}")
    print(f"  {'─' * 66}")
    for m in SUPPORTED_MODELS:
        name = m["name"].replace("models/", "")
        suffix = ""
        if "-search" in name:
            suffix = " [search]"
        elif "-nothinking" in name:
            suffix = " [no-think]"
        elif "-maxthinking" in name:
            suffix = " [max-think]"
        print(f"  • {name}{suffix}")

    print(f"\n{'=' * 70}\n")


def main():
    parser = argparse.ArgumentParser(
        description="geminicli2api — Universal Gemini API Proxy + Translator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run start.py                  Start the proxy server on port 8888
  uv run start.py --add-account    Add a Google OAuth account
  uv run start.py --translate      Run the Gemini Translator CLI
  uv run start.py --list-models    List all available models
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
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List all supported Gemini models and variants",
    )

    args = parser.parse_args()

    if args.add_account:
        from server.start import add_account
        add_account()
    elif args.translate:
        import asyncio
        from apps.gemini_translator.start import main as translator_main
        asyncio.run(translator_main())
    elif args.list_models:
        list_models()
    else:
        from server.start import start_server
        start_server()


if __name__ == "__main__":
    main()
