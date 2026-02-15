"""
ExecutionTimer — measures execution time of code blocks.

Usage as context manager:
    with ExecutionTimer():
        main()

Usage as decorator:
    @execution_timer
    def main():
        pass
"""

from datetime import datetime
from time import perf_counter_ns
from dataclasses import dataclass

from apps.gemini_translator.src.utils.console import console


@dataclass(slots=True)
class ExecutionTimer:
    """Context manager that measures execution time."""

    description: str = ""
    start_date: datetime = None
    end_date: datetime = None
    start_time_ns: int = None
    end_time_ns: int = None

    def __post_init__(self):
        self.start_date = datetime.now()
        self.start_time_ns = perf_counter_ns()

    def __enter__(self) -> 'ExecutionTimer':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.end_date = datetime.now()
            self.end_time_ns = perf_counter_ns()
            self.display_time()
        except AttributeError:
            print('An error occurred: __exit__')

    @staticmethod
    def current_datetime(date: datetime) -> str:
        return f'[yellow]{date.year}-{date.month:02d}-{date.day:02d}' \
               f' [white bold]{date.hour:02d}:{date.minute:02d}:{date.second:02d}'

    def calculate_duration(self) -> str:
        duration_ns: int = self.end_time_ns - self.start_time_ns
        duration_s, duration_ns = map(int, divmod(duration_ns, 1_000_000_000))
        duration_ms, duration_ns = map(int, divmod(duration_ns, 1_000_000))
        duration_us, duration_ns = map(int, divmod(duration_ns, 1_000))

        hours, remainder = map(int, divmod(duration_s, 3600))
        minutes, seconds = map(int, divmod(remainder, 60))

        return f'[white bold]{hours:02d}:{minutes:02d}:{seconds:02d}:' \
               f'{duration_ms:03d}:{duration_us:03d}:{duration_ns:03d}'

    def calculate_duration_alt(self) -> tuple[float, ...]:
        duration_ns: int = self.end_time_ns - self.start_time_ns
        hours_alt: float = duration_ns / 1_000_000_000 / 60 / 60
        minutes_alt: float = duration_ns / 1_000_000_000 / 60
        seconds_alt: float = duration_ns / 1_000_000_000
        return hours_alt, minutes_alt, seconds_alt

    def display_time(self):
        start_date_str = self.current_datetime(self.start_date)
        end_date_str = self.current_datetime(self.end_date)
        duration = self.calculate_duration()
        hours_alt, minutes_alt, seconds_alt = map(float, self.calculate_duration_alt())

        label = f' ({self.description})' if self.description else ''
        console.print(f'\n[bold white]╚═══════════ EXECUTION TIME{label} ═══════════╝')
        console.print('[bold bright_yellow]        YYYY-MM-DD HH:MM:SS:ms :µs :ns')
        console.print(f'[bright_red bold][[bold white]START[bright_red bold]] {start_date_str}')
        console.print(f'[bright_red bold][[bold white]END[bright_red bold]]   {end_date_str}')
        console.print(f'[bright_red bold][[bold white]TIME[bright_red bold]]  [bold bright_yellow]YYYY-MM-DD {duration}')
        console.print('[bright_red bold]                   ^^^^^^^^^^^^')
        console.print(f'[bright_red bold][[bold white]TIME[bright_red bold]]  [white bold]{hours_alt:.9f} hours')
        console.print(f'[bright_red bold][[bold white]TIME[bright_red bold]]  [white bold]{minutes_alt:.9f} minutes')
        console.print(f'[bright_red bold][[bold white]TIME[bright_red bold]]  [white bold]{seconds_alt:.9f} seconds')


def execution_timer(func):
    """Decorator that measures execution time."""
    def wrapper(*args, **kwargs):
        with ExecutionTimer():
            result = func(*args, **kwargs)
        return result
    return wrapper
