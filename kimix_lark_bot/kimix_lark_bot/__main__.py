# -*- coding: utf-8 -*-
"""Main entry point for Kimix Lark Bot."""

import argparse
import logging
import sys
from pathlib import Path

from kimix_lark_bot.config import load_config, create_default_config
from kimix_lark_bot.agent import FeishuBotAgent

DEFAULT_CONFIG_PATH = Path.home() / ".kimix_lark_bot.yaml"


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _interactive_setup(config_path: Path) -> None:
    """Prompt user for Feishu credentials and create a config file."""
    print("=" * 60)
    print("  Kimix Lark Bot - 首次配置")
    print("=" * 60)
    print()
    print("未找到配置文件。你需要一个飞书自定义机器人。")
    print("创建指南: https://open.feishu.cn/app")
    print()

    app_id = input("请输入飞书 App ID: ").strip()
    app_secret = input("请输入飞书 App Secret: ").strip()

    if not app_id or not app_secret:
        print("错误: App ID 和 App Secret 不能为空。")
        sys.exit(1)

    create_default_config(str(config_path), app_id=app_id, app_secret=app_secret)
    print()
    print(f"配置已保存到: {config_path}")
    print("你可以随时编辑该文件添加项目快捷名等设置。")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Kimix Lark Bot")
    parser.add_argument(
        "-c", "--config",
        default=None,
        help="Config file path (default: ~/.kimix_lark_bot.yaml)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    if args.config:
        config_path = Path(args.config)
    else:
        config_path = DEFAULT_CONFIG_PATH

    if not config_path.exists():
        _interactive_setup(config_path)

    config = load_config(str(config_path))

    if not config.app_id or not config.app_secret:
        print("错误: 配置文件中缺少 app_id 或 app_secret。")
        print(f"请编辑配置文件: {config_path}")
        return 1

    agent = FeishuBotAgent(config)
    return agent.run()


if __name__ == "__main__":
    sys.exit(main())
