"""
Configuration constants for the geminicli2api proxy server.
Centralizes all configuration to avoid duplication across modules.
"""
import os
from pathlib import Path

# --- Paths ---
ROOT_DIR = Path(__file__).resolve().parent.parent
SERVER_DIR = Path(__file__).resolve().parent
ACCOUNTS_DIR = ROOT_DIR / "accounts"

# API Endpoints
CODE_ASSIST_ENDPOINT = "https://cloudcode-pa.googleapis.com"

# Client Configuration
CLI_VERSION = "0.1.5"

# OAuth Configuration
CLIENT_ID = "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
CLIENT_SECRET = "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"
SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

# File Paths — legacy single-account (for backward compat)
CREDENTIAL_FILE = str(
    ROOT_DIR / os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "oauth_creds.json"))

# Authentication
GEMINI_AUTH_PASSWORD = os.getenv("GEMINI_AUTH_PASSWORD", "123456")

# Server
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8888"))

# Default Safety Settings for Google API
DEFAULT_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_IMAGE_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_IMAGE_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_IMAGE_HATE", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_IMAGE_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_UNSPECIFIED", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_JAILBREAK", "threshold": "BLOCK_NONE"},
]

# Base Models (only models verified to exist on Google's CodeAssist endpoint)
BASE_MODELS = [
    {
        "name": "models/gemini-2.0-flash",
        "version": "001",
        "displayName": "Gemini 2.0 Flash",
        "description": "Fast multimodal model from Gemini 2.0 generation",
        "inputTokenLimit": 1048576,
        "outputTokenLimit": 8192,
        "supportedGenerationMethods": ["generateContent", "streamGenerateContent"],
        "temperature": 1.0,
        "maxTemperature": 2.0,
        "topP": 0.95,
        "topK": 64,
    },
    {
        "name": "models/gemini-2.5-flash",
        "version": "001",
        "displayName": "Gemini 2.5 Flash",
        "description": "Fast and efficient multimodal model with latest improvements",
        "inputTokenLimit": 1048576,
        "outputTokenLimit": 65535,
        "supportedGenerationMethods": ["generateContent", "streamGenerateContent"],
        "temperature": 1.0,
        "maxTemperature": 2.0,
        "topP": 0.95,
        "topK": 64,
    },
    {
        "name": "models/gemini-2.5-flash-lite",
        "version": "001",
        "displayName": "Gemini 2.5 Flash Lite",
        "description": "Lightweight version of Gemini 2.5 Flash — fast and cost-efficient",
        "inputTokenLimit": 1048576,
        "outputTokenLimit": 65535,
        "supportedGenerationMethods": ["generateContent", "streamGenerateContent"],
        "temperature": 1.0,
        "maxTemperature": 2.0,
        "topP": 0.95,
        "topK": 64,
    },
    {
        "name": "models/gemini-2.5-pro",
        "version": "001",
        "displayName": "Gemini 2.5 Pro",
        "description": "Advanced multimodal model with enhanced capabilities",
        "inputTokenLimit": 1048576,
        "outputTokenLimit": 65535,
        "supportedGenerationMethods": ["generateContent", "streamGenerateContent"],
        "temperature": 1.0,
        "maxTemperature": 2.0,
        "topP": 0.95,
        "topK": 64,
    },
    {
        "name": "models/gemini-3-flash-preview",
        "version": "001",
        "displayName": "Gemini 3.0 Flash Preview",
        "description": "Preview version of Gemini 3.0 Flash — latest generation",
        "inputTokenLimit": 1048576,
        "outputTokenLimit": 65535,
        "supportedGenerationMethods": ["generateContent", "streamGenerateContent"],
        "temperature": 1.0,
        "maxTemperature": 2.0,
        "topP": 0.95,
        "topK": 64,
    },
    {
        "name": "models/gemini-3-pro-preview",
        "version": "001",
        "displayName": "Gemini 3.0 Pro Preview",
        "description": "Preview version of Gemini 3.0 Pro — most capable model",
        "inputTokenLimit": 1048576,
        "outputTokenLimit": 65535,
        "supportedGenerationMethods": ["generateContent", "streamGenerateContent"],
        "temperature": 1.0,
        "maxTemperature": 2.0,
        "topP": 0.95,
        "topK": 64,
    },
]


# --- Model variant generators ---

def _generate_search_variants():
    search_models = []
    for model in BASE_MODELS:
        if "generateContent" in model["supportedGenerationMethods"]:
            variant = model.copy()
            variant["name"] = model["name"] + "-search"
            variant["displayName"] = model["displayName"] + \
                " with Google Search"
            variant["description"] = model["description"] + \
                " (includes Google Search grounding)"
            search_models.append(variant)
    return search_models


def _has_thinking_support(model_name: str) -> bool:
    """Check if a model supports thinking budget configuration."""
    name = model_name.lower()
    # Exclude models without thinking support
    if "gemini-2.0-" in name:
        return False
    if "gemini-2.5-flash-lite" in name:
        return False
    # Include models with thinking
    if any(x in name for x in ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-pro", "gemini-3-flash"]):
        return True
    return False


def _generate_thinking_variants():
    thinking_models = []
    for model in BASE_MODELS:
        if _has_thinking_support(model["name"]) and "generateContent" in model["supportedGenerationMethods"]:
            nothinking = model.copy()
            nothinking["name"] = model["name"] + "-nothinking"
            nothinking["displayName"] = model["displayName"] + " (No Thinking)"
            nothinking["description"] = model["description"] + \
                " (thinking disabled)"
            thinking_models.append(nothinking)

            maxthinking = model.copy()
            maxthinking["name"] = model["name"] + "-maxthinking"
            maxthinking["displayName"] = model["displayName"] + \
                " (Max Thinking)"
            maxthinking["description"] = model["description"] + \
                " (maximum thinking budget)"
            thinking_models.append(maxthinking)
    return thinking_models


all_models = BASE_MODELS + _generate_search_variants() + \
    _generate_thinking_variants()
SUPPORTED_MODELS = sorted(all_models, key=lambda x: x["name"])


# --- Helper functions ---

def get_base_model_name(model_name: str) -> str:
    for suffix in ["-maxthinking", "-nothinking", "-search"]:
        if model_name.endswith(suffix):
            return model_name[: -len(suffix)]
    return model_name


def is_search_model(model_name: str) -> bool:
    return "-search" in model_name


def is_nothinking_model(model_name: str) -> bool:
    return "-nothinking" in model_name


def is_maxthinking_model(model_name: str) -> bool:
    return "-maxthinking" in model_name


def get_thinking_budget(model_name: str) -> int:
    base_model = get_base_model_name(model_name)
    if is_nothinking_model(model_name):
        if "gemini-2.5-flash" in base_model and "lite" not in base_model:
            return 0
        elif "gemini-2.5-pro" in base_model or "gemini-3-pro" in base_model:
            return 128
        elif "gemini-3-flash" in base_model:
            return 0
    elif is_maxthinking_model(model_name):
        if "gemini-2.5-flash" in base_model and "lite" not in base_model:
            return 24576
        elif "gemini-2.5-pro" in base_model:
            return 32768
        elif "gemini-3-pro" in base_model:
            return 45000
        elif "gemini-3-flash" in base_model:
            return 24576
    return -1


def should_include_thoughts(model_name: str) -> bool:
    if is_nothinking_model(model_name):
        base_model = get_base_model_name(model_name)
        return "gemini-2.5-pro" in base_model or "gemini-3-pro" in base_model or "gemini-3-flash" in base_model
    return True
