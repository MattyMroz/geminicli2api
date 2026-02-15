"""
Gemini Translator — start.py (Orchestrator)

Flow:
    1. Check / auto-start proxy server
    2. Pre-processing: TXT → SRT saved in input_folder (alongside original .txt)
    3. Translation:    SRT from input_folder → translated SRT saved in output_folder
    4. Post-processing: translated SRT → TXT saved in output_txt_folder

Folders:
    working_space/input/      — original TXT + generated SRT
    working_space/output/     — translated SRT
    working_space/output_txt/ — translated TXT
"""
from apps.gemini_translator.src.utils.execution_timer import ExecutionTimer
from apps.gemini_translator.src.utils.console import console
from apps.gemini_translator.src.api_client import GeminiAPIClient
from apps.gemini_translator.src.formatter import TextRefactor
from apps.gemini_translator.src.translator import GeminiTranslator
from apps.gemini_translator.config import TranslatorConfig
import sys
import os
import signal
import asyncio
import subprocess
import time
from pathlib import Path

# Ensure project root on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))


# --- Graceful shutdown ---
_shutdown_event = asyncio.Event() if hasattr(asyncio, 'Event') else None
_server_proc: subprocess.Popen | None = None


def _handle_sigint(sig, frame):
    """Handle Ctrl+C gracefully — no ugly tracebacks."""
    console.print(
        "\n[yellow_bold]⟳ Przerwanie (Ctrl+C) — zamykam...[/yellow_bold]")
    if _server_proc is not None:
        try:
            _server_proc.terminate()
        except Exception:
            pass
    # Force exit cleanly
    os._exit(0)


# Install signal handler immediately
signal.signal(signal.SIGINT, _handle_sigint)


async def ensure_server_running(config: TranslatorConfig) -> subprocess.Popen | None:
    """
    Check if the proxy server is healthy.
    If not, start it as a subprocess and wait until it's ready.
    Returns the process handle if we started it, else None.
    """
    global _server_proc
    client = GeminiAPIClient(base_url=config.proxy_url,
                             api_key=config.proxy_api_key)

    try:
        healthy = await client.health_check()
        if healthy:
            console.print(
                "[green_bold]✓ Serwer proxy jest już uruchomiony[/green_bold]")
            await client.close()
            return None
    except Exception:
        pass
    finally:
        await client.close()

    if not config.auto_start_server:
        console.print(
            "[red_bold]✗ Serwer proxy nie jest uruchomiony. Uruchom go ręcznie: uv run server/start.py[/red_bold]")
        sys.exit(1)

    console.print("[yellow_bold]⟳ Uruchamiam serwer proxy...[/yellow_bold]")
    server_script = ROOT_DIR / "server" / "start.py"

    proc = subprocess.Popen(
        [sys.executable, str(server_script)],
        cwd=str(ROOT_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _server_proc = proc

    # Wait for server to become healthy
    client = GeminiAPIClient(base_url=config.proxy_url,
                             api_key=config.proxy_api_key)
    start_time = time.time()
    while time.time() - start_time < config.server_startup_timeout:
        try:
            healthy = await client.health_check()
            if healthy:
                console.print(
                    "[green_bold]✓ Serwer proxy uruchomiony pomyślnie[/green_bold]")
                await client.close()
                return proc
        except Exception:
            pass
        await asyncio.sleep(config.server_health_check_interval)

    await client.close()
    console.print(
        "[red_bold]✗ Nie udało się uruchomić serwera proxy w wyznaczonym czasie[/red_bold]")
    proc.terminate()
    sys.exit(1)


async def run_translation(config: TranslatorConfig):
    """Main translation pipeline — reads SRT from input, saves to output."""
    translator = GeminiTranslator(
        input_folder=config.input_folder,    # read SRT from input
        output_folder=config.output_folder,  # save translated SRT to output
        prompts_folder=config.prompts_folder,
        proxy_url=config.proxy_url,
        proxy_api_key=config.proxy_api_key,
        temperature=config.temperature,
        top_p=config.top_p,
        max_output_tokens=config.max_output_tokens,
        translated_line_count=config.translated_line_count,
        model_name=config.model_name,
        mode=config.mode,
        concurrent_requests=config.concurrent_requests,
    )

    try:
        await translator.translate_all_files()
    finally:
        await translator.close()


async def main():
    config = TranslatorConfig()
    config.display()

    # 1. Ensure server is running
    server_proc = await ensure_server_running(config)

    try:
        # ═══ Etap 1: Pre-processing — TXT → SRT in input_folder ═══
        console.print(
            "\n[blue_bold]═══ Etap 1: Formatowanie (TXT → SRT w input/) ═══[/blue_bold]")
        refactor_in = TextRefactor(
            input_folder=config.input_folder,
            output_folder=config.input_folder,   # SRT saved alongside TXT in input/
            convert_numbers=config.convert_numbers,
            output_format="srt",
            chunk_method=config.chunk_method,
            chunk_limit=config.chunk_limit,
            sentence_length=config.sentence_length,
        )
        refactor_in.process_files()
        console.print(
            "[green_bold]✓ Pliki sformatowane (SRT w input/)[/green_bold]")

        # ═══ Etap 2: Translation — SRT from input/ → translated SRT in output/ ═══
        console.print(
            "\n[blue_bold]═══ Etap 2: Tłumaczenie (input/ → output/) ═══[/blue_bold]")
        with ExecutionTimer(description="Tłumaczenie"):
            await run_translation(config)

        # ═══ Etap 3: Post-processing — translated SRT → TXT in output_txt/ ═══
        console.print(
            "\n[blue_bold]═══ Etap 3: Post-processing (SRT → TXT w output_txt/) ═══[/blue_bold]")
        refactor_out = TextRefactor(
            input_folder=config.output_folder,       # read translated SRT from output/
            output_folder=config.output_txt_folder,   # save TXT to output_txt/
            convert_numbers=False,
            output_format="txt",
        )
        refactor_out.process_files()
        console.print(
            "[green_bold]✓ Post-processing zakończony (TXT w output_txt/)[/green_bold]")

        console.print(
            "\n[green_bold]✓ Tłumaczenie zakończone pomyślnie![/green_bold]")
        console.print(
            f"  Przetłumaczone SRT: [blue]{config.output_folder}[/blue]")
        console.print(
            f"  Przetłumaczone TXT: [blue]{config.output_txt_folder}[/blue]")

    except KeyboardInterrupt:
        console.print("\n[yellow_bold]⟳ Przerwanie — zamykam...[/yellow_bold]")

    finally:
        # 5. Cleanup — stop server if we started it
        if server_proc is not None:
            console.print(
                "[yellow_bold]⟳ Zamykam serwer proxy...[/yellow_bold]")
            try:
                server_proc.terminate()
                server_proc.wait(timeout=5)
            except Exception:
                pass
            console.print("[green_bold]✓ Serwer proxy zamknięty[/green_bold]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
