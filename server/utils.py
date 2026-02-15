import platform
from server.config import CLI_VERSION


def get_user_agent() -> str:
    """Generate User-Agent string matching gemini-cli format."""
    system = platform.system()
    arch = platform.machine()
    return f"GeminiCLI/{CLI_VERSION} ({system}; {arch})"


def get_platform_string() -> str:
    system = platform.system().upper()
    arch = platform.machine().upper()
    mapping = {
        ("DARWIN", True): "DARWIN_ARM64",
        ("DARWIN", False): "DARWIN_AMD64",
        ("LINUX", True): "LINUX_ARM64",
        ("LINUX", False): "LINUX_AMD64",
        ("WINDOWS", False): "WINDOWS_AMD64",
    }
    is_arm = arch in ("ARM64", "AARCH64")
    return mapping.get((system, is_arm), "PLATFORM_UNSPECIFIED")


def get_client_metadata(project_id=None):
    return {
        "ideType": "IDE_UNSPECIFIED",
        "platform": get_platform_string(),
        "pluginType": "GEMINI",
        "duetProject": project_id,
    }
