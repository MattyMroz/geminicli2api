#!/usr/bin/env python3
"""
Konwertuje plik SRT na plik TXT z każdym napisem w osobnej linii.
"""

import re
from pathlib import Path


def srt_to_txt(srt_file: str, output_file: str) -> None:
    """
    Czyta plik SRT i zapisuje napisy jako pojedyncze linie w pliku TXT.

    Args:
        srt_file: Ścieżka do pliku SRT
        output_file: Ścieżka do wyjściowego pliku TXT
    """
    srt_path = Path(srt_file)
    if not srt_path.exists():
        raise FileNotFoundError(f"Plik nie istnieje: {srt_file}")

    # Odczytaj zawartość SRT
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Podziel na bloki (każdy napis to osobny blok oddzielony pustą linią)
    blocks = content.strip().split("\n\n")

    subtitles = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) >= 3:
            # Pomij index (linia 0) i timestamp (linia 1), weź resztę tekstu
            text = " ".join(lines[2:]).strip()
            if text:
                subtitles.append(text)

    # Zapisz do pliku TXT - wszystkie napisy w jednej linii
    output_path = Path(output_file)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(" ".join(subtitles))

    print(f"✓ Przetworzono {len(subtitles)} napisów")
    print(f"✓ Zapisano do: {output_path}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 2:
        srt_file = sys.argv[1]
        output_file = sys.argv[2]
    else:
        # Domyślnie przetwórz plik z workspace
        srt_file = "workspace/output/SS_2976-3000.srt"
        output_file = "workspace/output/SS_2976-3000_merged.txt"

    try:
        srt_to_txt(srt_file, output_file)
    except Exception as e:
        print(f"✗ Błąd: {e}", file=sys.stderr)
        sys.exit(1)
