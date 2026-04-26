# -*- coding: utf-8 -*-
"""Configuration management for Kimix Lark Bot."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
import logging
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    app_id: str = ""
    app_secret: str = ""
    base_port: int = 8896
    max_sessions: int = 10
    callback_timeout: int = 300
    auto_restart: bool = False
    config_path: Optional[str] = None
    projects: List[Dict[str, str]] = field(default_factory=list)
    admin_chat_id: Optional[str] = None
    default_chat_id: Optional[str] = None

    def validate(self) -> List[str]:
        warnings = []
        if not self.app_id:
            warnings.append("app_id is empty - Feishu connection will fail")
        if not self.app_secret:
            warnings.append("app_secret is empty - Feishu connection will fail")
        if not (1024 <= self.base_port <= 65535):
            warnings.append(f"base_port {self.base_port} out of range [1024, 65535]")
        for p in self.projects:
            path = p.get("path", "")
            if path:
                try:
                    resolved = Path(path).expanduser()
                    if not resolved.exists():
                        warnings.append(f"Project path does not exist: {path}")
                except Exception:
                    warnings.append(f"Invalid project path: {path}")
        return warnings


def load_config(config_path: str) -> AgentConfig:
    config = AgentConfig(config_path=config_path)
    p = Path(config_path)
    if not p.exists():
        return config
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        config.app_id = data.get("app_id", "")
        config.app_secret = data.get("app_secret", "")
        config.base_port = data.get("base_port", 8896)
        config.max_sessions = data.get("max_sessions", 10)
        config.callback_timeout = data.get("callback_timeout", 300)
        config.auto_restart = data.get("auto_restart", False)
        raw_projects = data.get("projects", [])
        config.projects = [
            {
                "slug": p.get("slug", ""),
                "path": p.get("path", ""),
                "label": p.get("label", ""),
            }
            for p in raw_projects
            if p.get("path")
        ]
        config.admin_chat_id = data.get("admin_chat_id") or None
        config.default_chat_id = data.get("default_chat_id") or None

        warnings = config.validate()
        for w in warnings:
            logger.warning("Config: %s", w)
    except Exception as exc:
        logger.error("Failed to load config %s: %s", config_path, exc)
    return config


def create_default_config(config_path: str, app_id: str = "", app_secret: str = "") -> None:
    p = Path(config_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    content = f"""\
# Kimix Lark Bot Configuration

# Feishu App Credentials (Required)
app_id: "{app_id}"
app_secret: "{app_secret}"

# Optional: Named project shortcuts
projects:
  - slug: "myproject"
    path: "~/projects/myproject"
    label: "My Project"

# Kimix server settings
base_port: 8896
max_sessions: 10
callback_timeout: 300
auto_restart: false

# Optional: Admin notification settings
# admin_chat_id: "oc_xxxxxxxxxxxxxxxx"
# default_chat_id: "oc_xxxxxxxxxxxxxxxx"
"""
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Created config: {config_path}")
