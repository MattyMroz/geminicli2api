"""
Configuration for the Gemini Translator application.

All parameters are set here for easy modification.
In the future, a UI can dynamically adjust these parameters.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path


# Root of the entire project (geminicli2api/)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
# Root of this app
APP_DIR = Path(__file__).resolve().parent


@dataclass
class TranslatorConfig:
    """All translator settings in one place."""

    # --- Proxy connection ---
    proxy_url: str = "http://127.0.0.1:8888"
    proxy_api_key: str = "123456"

    # --- Model ---
    model_name: str = "gemini-2.5-pro"
    temperature: float = 0.3
    top_p: float = 1.0
    max_output_tokens: int = 65536

    # --- Translation ---
    translated_line_count: int = 20
    concurrent_requests: int = 20
    mode: str = "text"  # text | image | manga | subtitle | ocr

    # --- Formatter / pre-processing ---
    convert_numbers: bool = True
    chunk_method: str = "word"
    chunk_limit: int = 250
    sentence_length: int = 750

    # --- Paths ---
    input_folder: str = field(default_factory=lambda: str(
        ROOT_DIR / "working_space" / "input"))
    output_folder: str = field(default_factory=lambda: str(
        ROOT_DIR / "working_space" / "output"))
    output_txt_folder: str = field(default_factory=lambda: str(
        ROOT_DIR / "working_space" / "output_txt"))
    prompts_folder: str = field(
        default_factory=lambda: str(APP_DIR / "prompts"))

    # --- Server management ---
    auto_start_server: bool = True
    server_startup_timeout: int = 15  # seconds to wait for server to start
    server_health_check_interval: float = 0.5  # seconds between health checks

    def __post_init__(self):
        """Ensure directories exist."""
        os.makedirs(self.input_folder, exist_ok=True)
        os.makedirs(self.output_folder, exist_ok=True)
        os.makedirs(self.output_txt_folder, exist_ok=True)

    def display(self):
        """Print current config to console."""
        from apps.gemini_translator.src.utils.console import console
        console.print(
            "\n[blue_bold]═══ Konfiguracja translatora ═══[/blue_bold]")
        console.print(f"  Model:              {self.model_name}")
        console.print(f"  Tryb:               {self.mode}")
        console.print(f"  Temperatura:        {self.temperature}")
        console.print(f"  Top P:              {self.top_p}")
        console.print(f"  Max tokenów:        {self.max_output_tokens}")
        console.print(f"  Linie na grupę:     {self.translated_line_count}")
        console.print(f"  Współbieżność:      {self.concurrent_requests}")
        console.print(f"  Konwersja liczb:    {self.convert_numbers}")
        console.print(f"  Chunk method:       {self.chunk_method}")
        console.print(f"  Chunk limit:        {self.chunk_limit}")
        console.print(f"  Sentence length:    {self.sentence_length}")
        console.print(f"  Proxy:              {self.proxy_url}")
        console.print(f"  Input:              {self.input_folder}")
        console.print(f"  Output (SRT):       {self.output_folder}")
        console.print(f"  Output (TXT):       {self.output_txt_folder}")
        console.print(f"  Prompty:            {self.prompts_folder}")
        console.print(
            "[blue_bold]════════════════════════════════[/blue_bold]\n")
