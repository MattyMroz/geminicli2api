"""
TextRefactor — SRT/TXT file processing with number conversion and chunking.
"""
import os
import re
from dataclasses import dataclass, field
from typing import List
from natsort import natsorted
from pysubs2 import SSAEvent, SSAFile

from apps.gemini_translator.src.number_in_words import NumberInWords
from apps.gemini_translator.src.text_chunker import chunk_text
from apps.gemini_translator.src.utils.console import console


@dataclass(slots=True)
class TextRefactor:
    input_folder: str
    output_folder: str
    convert_numbers: bool
    output_format: str
    chunk_method: str = field(default='word')
    chunk_limit: int = field(default=250)
    sentence_length: int = field(default=750)

    def process_files(self) -> None:
        try:
            self._create_output_folders()
            self._process_directory(self.input_folder)
        except Exception as e:
            console.print(
                f"Wystąpił błąd podczas przetwarzania plików: {str(e)}", style="red_bold")

    def _create_output_folders(self) -> None:
        os.makedirs(self.output_folder, exist_ok=True)

    def _process_directory(self, directory: str) -> None:
        # Collect files first to avoid issues when input == output folder
        files_to_process = []
        for root, dirs, files in os.walk(directory):
            for file in natsorted(files):
                if file.endswith(('.txt', '.srt')):
                    input_path = os.path.join(root, file)
                    relative_path = os.path.relpath(root, self.input_folder)
                    output_dir = os.path.join(
                        self.output_folder, relative_path)
                    files_to_process.append((input_path, output_dir, file))

        for input_path, output_dir, file in files_to_process:
            os.makedirs(output_dir, exist_ok=True)

            if file.endswith('.txt') and self.output_format == 'srt':
                self._txt_to_srt(input_path, output_dir)
            elif file.endswith('.srt') and self.output_format == 'txt':
                self._srt_to_txt(input_path, output_dir)
            elif file.endswith('.srt') and self.output_format == 'srt':
                self._process_input_srt(input_path, output_dir)
            elif file.endswith('.txt') and self.output_format == 'txt':
                self._process_input_txt(input_path, output_dir)

    def _txt_to_srt(self, input_path: str, output_dir: str) -> None:
        try:
            output_srt_path = os.path.join(
                output_dir, os.path.basename(input_path).replace('.txt', '.srt'))

            with open(input_path, 'r', encoding='utf-8') as file:
                text = file.read()

            if not text.strip():
                text = "."

            text = text.replace('\n\n', '\n').replace('\n', ' ')

            if self.convert_numbers:
                number_converter = NumberInWords()
                text = number_converter.convert_numbers_in_text(text)

            text = re.sub(r'\s+\.', '.', text)

            initial_chunks = chunk_text(
                text, method=self.chunk_method, limit=self.chunk_limit)
            captions = self._create_captions(initial_chunks)

            subs = SSAFile()
            for caption in captions:
                event = SSAEvent(start=0, end=0, text=caption.strip())
                subs.append(event)

            subs.save(output_srt_path, encoding='utf-8')
        except Exception as e:
            console.print(
                f"Błąd podczas przetwarzania pliku {input_path}: {str(e)}", style="red_bold")

    def _process_input_srt(self, input_path: str, output_dir: str) -> None:
        try:
            output_srt_path = os.path.join(
                output_dir, os.path.basename(input_path))
            subs = SSAFile.load(input_path)

            if self.convert_numbers:
                number_converter = NumberInWords()
                for event in subs:
                    event.text = number_converter.convert_numbers_in_text(
                        event.text)
                    event.text = re.sub(r'\s+\.', '.', event.text)
            subs.save(output_srt_path)
        except Exception as e:
            console.print(
                f"Błąd podczas przetwarzania pliku {input_path}: {str(e)}", style="red_bold")

    def _srt_to_txt(self, input_path: str, output_dir: str) -> None:
        try:
            output_txt_path = os.path.join(
                output_dir, os.path.basename(input_path).replace('.srt', '.txt'))
            subs = SSAFile.load(input_path)

            full_text = '\n'.join(event.text.replace('\\N', '\n')
                                  for event in subs)
            if not full_text.strip():
                full_text = "."

            sentences = chunk_text(full_text, method='word', limit=100)

            with open(output_txt_path, 'w', encoding='utf-8') as file:
                for sentence in sentences:
                    file.write(f"{sentence.strip()}\n")
        except Exception as e:
            console.print(
                f"Błąd podczas przetwarzania pliku {input_path}: {str(e)}", style="red_bold")

    def _process_input_txt(self, input_path: str, output_dir: str) -> None:
        try:
            output_txt_path = os.path.join(
                output_dir, os.path.basename(input_path))
            with open(input_path, 'r', encoding='utf-8') as file:
                text = file.read()

            if not text.strip():
                text = "."

            if self.convert_numbers:
                number_converter = NumberInWords()
                text = number_converter.convert_numbers_in_text(text)

            text = re.sub(r'\s+\.', '.', text)

            sentences = chunk_text(text, method='word', limit=100)

            with open(output_txt_path, 'w', encoding='utf-8') as file:
                for sentence in sentences:
                    file.write(f"{sentence.strip()}\n")
        except Exception as e:
            console.print(
                f"Błąd podczas przetwarzania pliku {input_path}: {str(e)}", style="red_bold")

    def _create_captions(self, initial_chunks: List[str]) -> List[str]:
        if self.sentence_length == 0:
            return initial_chunks

        captions = []
        current_caption = ""

        def add_chunk_to_caption(chunk: str) -> None:
            nonlocal current_caption
            if len(current_caption) + len(chunk) <= self.sentence_length:
                current_caption += " " + chunk if current_caption else chunk
            else:
                captions.append(current_caption)
                current_caption = chunk

        for chunk in initial_chunks:
            if len(chunk) <= self.sentence_length:
                add_chunk_to_caption(chunk)
            else:
                sub_chunks = chunk_text(
                    chunk, method=self.chunk_method, limit=self.sentence_length // 2)
                for sub_chunk in sub_chunks:
                    add_chunk_to_caption(sub_chunk)

        if current_caption:
            captions.append(current_caption)

        return captions
