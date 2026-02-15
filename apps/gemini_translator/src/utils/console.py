"""Rich console setup for gemini_translator."""
from rich.console import Console
from rich.theme import Theme

custom_theme = Theme({
    "green_bold": "bold green",
    "red_bold": "bold red",
    "yellow_bold": "bold yellow",
    "blue_bold": "bold blue",
    "purple_bold": "bold purple",
    "white_bold": "bold white",
})

console = Console(theme=custom_theme)
