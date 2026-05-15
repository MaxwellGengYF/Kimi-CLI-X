from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import orjson

from kimix.base import print_info, print_success, print_warning
default_config = '''
{
    "model_name": "kimi-for-coding",
    "name": "moonshot",
    "model": "kimi-for-coding",
    "max_context_size": 262144,
    "capabilities": ["thinking"],
    "url": "https://api.kimi.com/coding/v1",
    "type": "kimi",
    "max_tokens": 131072,
    "show_thinking_stream": true,
    "thinking_effort": "max",
    "temperature": 1.0
}
'''
_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "default_config.json"
_SECOND_CONFIG_PATH = Path(__file__).parent.parent / "second_config.json"

_CONTEXT_SIZE_OPTIONS: dict[str, int] = {
    "128k": 131072,
    "200k": 204800,
    "256k": 262144,
    "512k": 524288,
    "1M": 1048576,
}

_VALID_TYPES = (
    "kimi",
    "openai_legacy",
    "openai_responses",
    "anthropic",
    "google_genai",
    "gemini",
    "vertexai",
)

_VALID_THINKING_EFFORTS = ('off', 'low', 'medium', 'high', 'xhigh', 'max')

_VALID_CAPABILITIES = ("thinking", "always_thinking", "image_in", "video_in")



def _load_default_config() -> dict[str, Any]:
    if _DEFAULT_CONFIG_PATH.exists():
        with open(_DEFAULT_CONFIG_PATH, "rb") as f:
            return orjson.loads(f.read())
    return orjson.loads(default_config)


def _save_config(config: dict[str, Any]) -> None:
    with open(_DEFAULT_CONFIG_PATH, "wb") as f:
        f.write(orjson.dumps(config, option=orjson.OPT_INDENT_2))


def _save_second_config(config: dict[str, Any]) -> None:
    with open(_SECOND_CONFIG_PATH, "wb") as f:
        f.write(orjson.dumps(config, option=orjson.OPT_INDENT_2))


def _ask(prompt: str, default: str) -> str:
    print_info(f"{prompt} [{default}]: ", end="")
    value = input().strip()
    return value if value else default


def _ask_model_name(default: str = "kimi-for-coding") -> str:
    return _ask("Enter model name", default)


def _ask_model_type(default: str = "kimi") -> str:
    options_str = ", ".join(_VALID_TYPES)
    while True:
        value = _ask(f"Enter model type ({options_str})", default)
        if value in _VALID_TYPES:
            return value
        print_warning(f"Invalid type '{value}', please choose from: {options_str}")


def _ask_api_key() -> str:
    skip = False
    if os.environ.get("KIMI_API_KEY"):
        print_info("API key already set in environment variable KIMI_API_KEY.")
        skip = True
    if os.environ.get("KIMIX_API_KEY"):
        print_info("API key already set in environment variable KIMIX_API_KEY.")
        skip = True
    print_info("Enter API key (usually required, or set KIMI_API_KEY/KIMIX_API_KEY env var): ", end="")
    value = input().strip()
    if not skip and not value:
        print_warning("API key is usually required. Press Enter again to skip.")
        print_info("Enter API key: ", end="")
        value = input().strip()
    return value


def _ask_context_size(default: str = "256k") -> int:
    options_str = ", ".join(_CONTEXT_SIZE_OPTIONS.keys())
    while True:
        value = _ask(f"Enter model context size ({options_str} or a number)", default)
        if value in _CONTEXT_SIZE_OPTIONS:
            return _CONTEXT_SIZE_OPTIONS[value]
        try:
            num = int(value)
        except ValueError:
            print_warning(f"Invalid size '{value}', please choose from: {options_str} or enter a specific number")
            continue
        if num <= 1:
            print_warning(f"Context size must be larger than 1, got {num}")
            continue
        num = max(num, 1.)
        return num


def _ask_thinking_effort(default: str = "max") -> str:
    options_str = ", ".join(_VALID_THINKING_EFFORTS)
    while True:
        value = _ask(f"Enter thinking effort ({options_str})", default)
        if value in _VALID_THINKING_EFFORTS:
            return value
        print_warning(f"Invalid effort '{value}', please choose from: {options_str}")


def _ask_capabilities(default: tuple[str, ...] = ("thinking",)) -> list[str]:
    options_str = ", ".join(_VALID_CAPABILITIES)
    prompt = f"Enter capabilities ({options_str}), multiple allowed, 'none' for empty"
    default_str = ", ".join(default)
    while True:
        value = _ask(prompt, default_str).strip()
        if not value:
            return list(default)
        if value.lower() == "none":
            return []
        parts = [p.strip() for p in value.replace(",", " ").split()]
        invalid = [p for p in parts if p not in _VALID_CAPABILITIES]
        if invalid:
            print_warning(f"Invalid capabilities: {', '.join(invalid)}, please choose from: {options_str}")
            continue
        return parts


def _ask_url(default: str = "https://api.kimi.com/coding/v1") -> str:
    return _ask("Enter model URL", default)


def _ask_temperature(default: float = 1.0) -> float:
    while True:
        value = _ask("Enter temperature", str(default)).strip()
        if not value:
            return default
        try:
            num = float(value)
        except ValueError:
            print_warning(f"Invalid number '{value}', using default {default}")
            return default
        if num < 0.0 or num > 2.0:
            print_warning(f"Value {num} out of range [0.0, 2.0], using default {default}")
            return default
        return num


def _ask_max_token(context_size: int, reserved: int, default: int) -> int:
    max_allowed = context_size - reserved
    prompt = f"Enter max tokens (max {max_allowed})"
    while True:
        value = _ask(prompt, str(default)).strip()
        if not value:
            return default
        try:
            num = int(value)
        except ValueError:
            print_warning(f"Invalid number '{value}', using default {default}")
            return default
        if num <= 0 or num > max_allowed:
            print_warning(f"Value {num} out of range, using default {default}")
            return default
        return num


def _ask_sub_provider(defaults: dict[str, Any] | None = None) -> dict[str, Any] | None:
    print_info("Configure a sub-agent provider? (y/n)")
    v = input().strip().lower()
    if v != 'y':
        return None

    def _default(key: str, fallback: Any) -> Any:
        if defaults is None:
            return fallback
        return defaults.get(key, fallback)

    _CONTEXT_SIZE_BY_INT = {v: k for k, v in _CONTEXT_SIZE_OPTIONS.items()}

    print_info("--- Sub-provider configuration ---")
    sub: dict[str, Any] = {}

    model = _ask_model_name(_default("model", "kimi-for-coding"))
    sub["model"] = model

    model_type = _ask_model_type(_default("type", "kimi"))
    sub["type"] = model_type

    url = _ask_url(_default("url", "https://api.kimi.com/coding/v1"))
    sub["url"] = url

    api_key = _ask_api_key()
    sub["api_key"] = api_key

    temperature = _ask_temperature(_default("temperature", 1.0))
    sub["temperature"] = temperature

    ctx_default = _default("max_context_size", 262144)
    ctx_str = _CONTEXT_SIZE_BY_INT.get(ctx_default, "256k")
    context_size = _ask_context_size(ctx_str)
    sub["max_context_size"] = context_size

    thinking = _ask_thinking_effort("off")
    sub["thinking_effort"] = thinking

    caps = _default("capabilities", ("thinking",))
    if isinstance(caps, list):
        caps = tuple(caps)
    elif isinstance(caps, str):
        caps = (caps,)
    caps = _ask_capabilities(caps)
    if "always_thinking" in caps and "thinking" in caps:
        caps.remove("thinking")
    sub["capabilities"] = caps

    reserved = 50000
    max_tokens = _ask_max_token(context_size, reserved, _default("max_tokens", 128000))
    sub["max_tokens"] = max_tokens

    # Ensure loop_control for sub-provider disables ralph
    sub["loop_control"] = {
        "max_steps_per_turn": 5000,
        "max_retries_per_step": 3,
        "max_ralph_iterations": 0,
        "reserved_context_size": 50000,
        "compaction_trigger_ratio": 0.85,
    }

    sub["name"] = model_type
    sub["model_name"] = model

    print_success("Sub-provider configuration complete.")
    return sub


def init(initialize: bool = True) -> None:
    if not initialize:
        v = input('default config not found, initialize? you can use /init any time. (y/n)').strip().lower() 
        initialize = v == 'y' or not v
    config = _load_default_config()
    defaults = orjson.loads(default_config)
    # Merge loaded config over defaults so missing keys are filled in
    for key, value in defaults.items():
        if key not in config:
            config[key] = value
        elif isinstance(value, dict) and key in config and isinstance(config[key], dict):
            for sub_key, sub_value in value.items():
                if sub_key not in config[key]:
                    config[key][sub_key] = sub_value
    try:
        if initialize:
            model = _ask_model_name(config.get("model", "kimi-for-coding"))
            config["model"] = model

            model_type = _ask_model_type(config.get("type", "kimi"))
            config["type"] = model_type

            api_key = _ask_api_key()
            config["api_key"] = api_key

            context_size = _ask_context_size()
            config["max_context_size"] = context_size

            reserved = config.get("loop_control", {}).get("reserved_context_size", 50000)
            max_tokens = _ask_max_token(context_size, reserved, 131072)
            config["max_tokens"] = max_tokens

            thinking = _ask_thinking_effort(config.get("thinking_effort", "low"))
            config["thinking_effort"] = thinking

            caps = config.get("capabilities", ["thinking"])
            if isinstance(caps, str):
                caps = (caps,)
            capabilities = _ask_capabilities(tuple(caps))
            if "always_thinking" in capabilities and "thinking" in capabilities:
                capabilities.remove("thinking")
            config["capabilities"] = capabilities

            url = _ask_url(config.get("url", "https://api.kimi.com/coding/v1"))
            config["url"] = url

            temperature = _ask_temperature(config.get("temperature", 1.0))
            config["temperature"] = temperature

            sub_provider = _ask_sub_provider(config)
            if sub_provider is not None:
                _save_second_config(sub_provider)
            elif _SECOND_CONFIG_PATH.exists():
                _SECOND_CONFIG_PATH.unlink()
    except KeyboardInterrupt:
        print_warning('keyboard interruped.')
        return
    _save_config(config)
    if initialize:
        print_success(f"Configuration saved successfully to {_DEFAULT_CONFIG_PATH}.")
        if _SECOND_CONFIG_PATH.exists():
            print_success(f"Sub-provider configuration saved to {_SECOND_CONFIG_PATH}.")
    if sys.platform == "win32":
        os.startfile(str(_DEFAULT_CONFIG_PATH))
    elif sys.platform == "darwin":
        subprocess.run(["open", str(_DEFAULT_CONFIG_PATH)])
    else:
        subprocess.run(["xdg-open", str(_DEFAULT_CONFIG_PATH)])
