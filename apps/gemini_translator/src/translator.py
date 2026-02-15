"""
GeminiTranslator — translates files via the geminicli2api proxy server.

Adapted from GeminiTranslatorCOTE.py:
- Replaces google.generativeai SDK with httpx calls to local proxy
- No API keys needed — proxy handles all OAuth/auth
- Supports: text (SRT), image, manga, subtitle, OCR modes
"""
import os
import re
import asyncio
import shutil
import time
from pathlib import Path
from typing import List, Deque
from collections import deque

import pysrt
from natsort import natsorted

from apps.gemini_translator.src.api_client import GeminiAPIClient
from apps.gemini_translator.src.utils.console import console

# Constants
MAX_RETRIES = 100
INITIAL_BACKOFF = 1.0
MAX_BACKOFF = 60.0


class GeminiTranslator:
    def __init__(
        self,
        input_folder: str,
        output_folder: str,
        prompts_folder: str,
        proxy_url: str = "http://127.0.0.1:8888",
        proxy_api_key: str = "123456",
        temperature: float = 0.3,
        top_p: float = 1.0,
        max_output_tokens: int = 65536,
        translated_line_count: int = 20,
        model_name: str = "gemini-2.5-pro",
        mode: str = "text",
        concurrent_requests: int = 2,
    ):
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.prompts_folder = prompts_folder
        self.temperature = temperature
        self.top_p = top_p
        self.max_output_tokens = max_output_tokens
        self.translated_line_count = translated_line_count
        self.model_name = model_name
        self.mode = mode
        self.concurrent_requests = concurrent_requests

        # API client — talks to our proxy
        self.api_client = GeminiAPIClient(
            base_url=proxy_url,
            api_key=proxy_api_key,
            timeout=300.0,
        )

        # Concurrency controls
        self.semaphore = asyncio.Semaphore(concurrent_requests)
        self.write_lock = asyncio.Lock()
        self.file_queue: Deque[str] = deque()

        # Stats
        self._translated_groups = 0
        self._failed_groups = 0

        self.supported_image_extensions = (
            '.png', '.jpg', '.jpeg', '.webp', '.heic', '.heif')

    async def close(self):
        """Close the HTTP client."""
        await self.api_client.close()

    def _get_mime_type(self, path: str) -> str:
        extension = path.lower().split('.')[-1]
        mime_types = {
            'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
            'png': 'image/png', 'webp': 'image/webp',
            'heic': 'image/heic', 'heif': 'image/heif'
        }
        return mime_types.get(extension, 'application/octet-stream')

    async def translate_with_api(self, text: str, prompt_main: str, prompt_helper: str, image_path: str = None) -> str:
        """Send translation request via proxy."""
        full_prompt = f"{prompt_main}\n\n{prompt_helper}\n\n{text}"

        if image_path:
            try:
                console.print(
                    f"Processing image: {image_path}", style="purple_bold")
                with open(image_path, "rb") as f:
                    image_data = f.read()
                mime_type = self._get_mime_type(image_path)
                response = await self.api_client.generate_with_image(
                    model=self.model_name,
                    prompt=full_prompt,
                    image_data=image_data,
                    mime_type=mime_type,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    max_tokens=self.max_output_tokens,
                )
            except Exception as e:
                console.print(f"Error loading image: {e}", style="red_bold")
                return ""
        else:
            response = await self.api_client.generate(
                model=self.model_name,
                prompt=full_prompt,
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_output_tokens,
            )

        return response.strip()

    # --- OCR mode ---

    async def ocr_image(self, image_path: str, prompt_main: str, prompt_helper: str, output_file: str) -> str:
        async with self.semaphore:
            for attempt in range(MAX_RETRIES):
                try:
                    response = await self.translate_with_api("", prompt_main, prompt_helper, image_path)
                    console.print(
                        f"\n[green_bold]OCR tekst:[/green_bold]\n{response}", style='white_bold')

                    async with self.write_lock:
                        with open(output_file, 'a', encoding='utf-8') as f:
                            f.write(response + "\n\n")
                    return response
                except Exception as e:
                    await self.handle_translation_error(e, attempt)
            self._failed_groups += 1
            console.print(f"BŁĄD: OCR nie powiodło się po {MAX_RETRIES} próbach: {image_path}", style="red_bold")
            return ""

    async def process_folder_ocr(self, folder_path: str) -> None:
        files = []
        for file in os.listdir(folder_path):
            if file.lower().endswith(self.supported_image_extensions):
                files.append(os.path.join(folder_path, file))

        files = natsorted(files)
        folder_name = os.path.basename(folder_path)
        output_file = os.path.join(self.output_folder, f"{folder_name}.txt")
        os.makedirs(self.output_folder, exist_ok=True)
        open(output_file, 'w', encoding='utf-8').close()

        prompt_main, prompt_helper = self.load_prompts()
        tasks = [asyncio.create_task(self.ocr_image(
            ip, prompt_main, prompt_helper, output_file)) for ip in files]
        await asyncio.gather(*tasks)
        console.print(
            f"Saved OCR results for {folder_name} to {output_file}", style="green_bold")

    async def process_all_folders_ocr(self):
        tasks = [asyncio.create_task(self.process_folder_ocr(
            root)) for root, dirs, _ in os.walk(self.input_folder)]
        await asyncio.gather(*tasks)

    # --- SRT translation ---

    async def translate_group(self, text: str, prompt_main: str, prompt_helper: str, group: List[pysrt.SubRipItem], subs: pysrt.SubRipFile, output_path: str, image_path: str = None):
        async with self.semaphore:
            for attempt in range(MAX_RETRIES):
                try:
                    console.print(
                        "[yellow_bold]Napisy do tłumaczenia:[/yellow_bold]\n" + text)
                    response = await self.translate_with_api(text, prompt_main, prompt_helper, image_path)
                    console.print(
                        f"\n[green_bold]Przetłumaczone napisy:[/green_bold]\n{response}", style='white_bold')

                    translated_text = self.format_response(response)
                    if translated_text:
                        translated_lines = translated_text.split(" @@\n")
                        if len(translated_lines) != len(group):
                            console.print(
                                f"BŁĄD: liczba napisów po tłumaczeniu ({len(translated_lines)}) != przed ({len(group)}) [próba {attempt + 1}/{MAX_RETRIES}]",
                                style="red_bold"
                            )
                            # On last attempt — save whatever we got (partial is better than nothing)
                            if attempt == MAX_RETRIES - 1:
                                console.print(
                                    "Ostatnia próba — zapisuję częściowy wynik",
                                    style="yellow_bold"
                                )
                                self._apply_partial_translation(group, translated_lines)
                                async with self.write_lock:
                                    subs.save(output_path, encoding='utf-8')
                                self._failed_groups += 1
                                return
                            continue
                        else:
                            self.update_subtitles(group, translated_lines)
                            async with self.write_lock:
                                subs.save(output_path, encoding='utf-8')
                            self._translated_groups += 1
                            return
                except Exception as e:
                    await self.handle_translation_error(e, attempt)
            self._failed_groups += 1
            console.print(
                f"BŁĄD: Nie udało się przetłumaczyć grupy po {MAX_RETRIES} próbach.",
                style="red_bold"
            )

    # --- Image / Manga modes ---

    async def translate_image(self, prompt_main: str, prompt_helper: str, image_path: str, output_path: str):
        async with self.semaphore:
            for attempt in range(MAX_RETRIES):
                try:
                    response = await self.translate_with_api("", prompt_main, prompt_helper, image_path)
                    console.print(
                        f"\n[green_bold]Przetłumaczony obraz:[/green_bold]\n{response}", style='white_bold')
                    translated_text = self.format_response(response)
                    if translated_text:
                        self.save_image_translation_as_srt(
                            translated_text, output_path)
                        return
                except Exception as e:
                    await self.handle_translation_error(e, attempt)
            self._failed_groups += 1
            console.print(f"BŁĄD: Nie udało się przetłumaczyć obrazu po {MAX_RETRIES} próbach.", style="red_bold")

    async def translate_manga(self, prompt_main: str, prompt_helper: str, text: str, image_path: str, output_path: str):
        async with self.semaphore:
            for attempt in range(MAX_RETRIES):
                try:
                    console.print(
                        "[yellow_bold]Tekst do tłumaczenia:[/yellow_bold]\n" + text)
                    response = await self.translate_with_api(text, prompt_main, prompt_helper, image_path)
                    console.print(
                        f"\n[green_bold]Przetłumaczony tekst:[/green_bold]\n{response}", style='white_bold')
                    translated_text = self.format_response(response)
                    if translated_text:
                        self.save_image_translation_as_srt(
                            translated_text, output_path.replace('.txt', '.srt'))
                        return
                except Exception as e:
                    await self.handle_translation_error(e, attempt)
            self._failed_groups += 1
            console.print(f"BŁĄD: Nie udało się przetłumaczyć mangi po {MAX_RETRIES} próbach.", style="red_bold")

    # --- Helpers ---

    def format_response(self, response: str) -> str:
        translated_text = response.rstrip(" @@")
        translated_text = re.sub(r"◍◍\d+\. ", "", translated_text)
        translated_text = translated_text.replace(" ◍◍◍◍, ", ",\n")
        translated_text = translated_text.replace(" ◍◍◍◍ ", "\n")
        translated_text = translated_text.replace(" ◍◍◍◍", "")
        return translated_text

    def update_subtitles(self, group: List[pysrt.SubRipItem], translated_lines: List[str]):
        for sub, trans_text in zip(group, translated_lines):
            sub.text = trans_text

    def _apply_partial_translation(self, group: List[pysrt.SubRipItem], translated_lines: List[str]):
        """Apply partial translation — fill as many subs as we have translations for."""
        for i, trans_text in enumerate(translated_lines):
            if i < len(group):
                group[i].text = trans_text

    def save_image_translation_as_srt(self, translated_text: str, output_path: str):
        lines = translated_text.split(' @@\n')
        subs = pysrt.SubRipFile()
        for i, line in enumerate(lines, start=1):
            start_time = pysrt.SubRipTime(0, 0, 0)
            end_time = pysrt.SubRipTime(0, 0, 0)
            item = pysrt.SubRipItem(
                index=i, start=start_time, end=end_time, text=line)
            subs.append(item)
        subs.save(output_path, encoding='utf-8')

    async def handle_translation_error(self, e: Exception, attempt: int):
        error_message = str(e)
        console.print(
            f"Wystąpił błąd podczas tłumaczenia (próba {attempt + 1}/{MAX_RETRIES}): {error_message}",
            style="red_bold"
        )

        if attempt >= MAX_RETRIES - 1:
            console.print(
                f"Nie udało się przetłumaczyć po {MAX_RETRIES} próbach.", style="red_bold")
            return

        wait_time = min(INITIAL_BACKOFF * (2 ** attempt), MAX_BACKOFF)
        console.print(f"Czekam {wait_time:.1f}s przed ponowną próbą...", style="yellow_bold")
        await asyncio.sleep(wait_time)

    # --- Main translation flow ---

    async def translate_srt(self, input_path: str, output_path: str, translated_line_count: int, image_path: str = None):
        prompt_main, prompt_helper = self.load_prompts()

        if self.mode == 'image':
            await self.translate_image(prompt_main, prompt_helper, input_path, output_path.replace('.png', '.srt'))
            return
        elif self.mode == 'manga':
            with open(input_path, 'r', encoding='utf-8') as f:
                text = f.read()
            await self.translate_manga(prompt_main, prompt_helper, text, image_path, output_path)
            return
        elif self.mode == 'ocr':
            await self.process_all_folders_ocr()
            return

        # Copy input to output first — so on Ctrl+C there's always a file
        if not os.path.exists(output_path):
            shutil.copy2(input_path, output_path)

        subs = pysrt.open(output_path, encoding='utf-8')
        groups = [subs[i:i+translated_line_count]
                  for i in range(0, len(subs), translated_line_count)]

        tasks = []
        counter = 1
        for group in groups:
            text = self.prepare_text_for_translation(group, counter)
            counter += len(group)
            task = asyncio.create_task(self.translate_group(
                text, prompt_main, prompt_helper, group, subs, output_path, image_path))
            tasks.append(task)

        await asyncio.gather(*tasks)
        console.print(
            f"\n[blue_bold]Statystyki: {self._translated_groups} grup OK, "
            f"{self._failed_groups} nieudanych (z {len(groups)} łącznie)[/blue_bold]"
        )

    def load_prompts(self):
        prompt_files = {
            'text': ('prompt_main.txt', 'prompt_helper.txt'),
            'image': ('prompt_main_image.txt', 'prompt_helper_image.txt'),
            'manga': ('prompt_main_manga.txt', 'prompt_helper_manga.txt'),
            'subtitle': ('prompt_main_subtitle.txt', 'prompt_helper_subtitle.txt'),
            'ocr': ('prompt_main_ocr.txt', 'prompt_helper_ocr.txt')
        }

        main_file, helper_file = prompt_files.get(
            self.mode, ('prompt_main.txt', 'prompt_helper.txt'))

        with open(os.path.join(self.prompts_folder, main_file), 'r', encoding='utf-8') as f:
            prompt_main = f.read()
        with open(os.path.join(self.prompts_folder, helper_file), 'r', encoding='utf-8') as f:
            prompt_helper = f.read()

        return prompt_main, prompt_helper

    def prepare_text_for_translation(self, group: List[pysrt.SubRipItem], counter: int) -> str:
        text = ""
        for sub in group:
            text += "◍◍{}. {}".format(counter,
                                      sub.text.replace('\n', ' ◍◍◍◍ ')) + " @@\n"
            counter += 1
        return text.removesuffix(' @@\n') if text.endswith(' @@\n') else text

    async def translate_file(self, input_path: str, output_path: str):
        try:
            image_path = None
            if self.mode == 'manga':
                image_path = input_path.replace(
                    'transcription', 'transcription_images').replace('.txt', '.png')
                with open(input_path, 'r', encoding='utf-8') as f:
                    text_content = f.read()
                prompts = self.load_prompts()
                await self.translate_manga(prompts[0], prompts[1], text_content, image_path, output_path)
            elif self.mode == 'image':
                image_path = input_path
                prompts = self.load_prompts()
                await self.translate_image(prompts[0], prompts[1], image_path, output_path.replace('.png', '.srt'))
            elif self.mode == 'ocr':
                await self.process_all_folders_ocr()
            else:
                await self.translate_srt(input_path, output_path, self.translated_line_count, image_path)
            console.print(
                f"Zakończono tłumaczenie pliku: {input_path}", style="green_bold")
        except Exception as e:
            console.print(
                f"Błąd podczas tłumaczenia pliku {input_path}: {str(e)}", style="red_bold")

    async def process_file(self, file_path: str):
        if self.mode == 'manga':
            input_path = os.path.join(
                self.input_folder, 'transcription', file_path)
        else:
            input_path = os.path.join(self.input_folder, file_path)
        relative_path = os.path.relpath(
            os.path.dirname(input_path), self.input_folder)
        output_subdir = os.path.join(self.output_folder, relative_path)
        os.makedirs(output_subdir, exist_ok=True)
        output_path = os.path.join(output_subdir, os.path.basename(file_path))

        console.print(
            f"Rozpoczęto tłumaczenie pliku: {input_path}", style="blue_bold")
        await self.translate_file(input_path, output_path)

    async def translate_all_files(self):
        if self.mode == 'ocr':
            await self.process_all_folders_ocr()
            return

        all_files = []
        if self.mode == 'manga':
            input_folder = os.path.join(self.input_folder, 'transcription')
        elif self.mode == 'image':
            input_folder = self.input_folder
        else:
            input_folder = self.input_folder

        for root, _, files in os.walk(input_folder):
            for file in files:
                if self.mode == 'image':
                    if file.lower().endswith(self.supported_image_extensions):
                        relative_path = os.path.relpath(
                            os.path.join(root, file), input_folder)
                        all_files.append(relative_path)
                elif self.mode == 'manga':
                    if file.endswith('.txt'):
                        relative_path = os.path.relpath(
                            os.path.join(root, file), input_folder)
                        all_files.append(relative_path)
                elif file.endswith('.srt'):
                    relative_path = os.path.relpath(
                        os.path.join(root, file), input_folder)
                    all_files.append(relative_path)

        sorted_files = natsorted(all_files)

        tasks = []
        for file in sorted_files:
            task = asyncio.create_task(self.process_file(file))
            tasks.append(task)

        await asyncio.gather(*tasks)
