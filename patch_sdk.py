#!/usr/bin/env python3
"""
Patch script to copy kimi-agent-sdk and kimi-cli source to current Python's site-packages.
Also upgrades the 'kosong' package to the latest version.
"""

import sys
import shutil
import subprocess
from pathlib import Path
import sysconfig


def get_site_packages() -> Path:
    """Get the current Python's site-packages directory."""
    return Path(sysconfig.get_path("purelib"))


def copy_directory(src: Path, dst: Path) -> None:
    """Copy a directory from src to dst, removing dst if it already exists."""
    if dst.exists():
        print(f"Removing existing directory: {dst}")
        shutil.rmtree(dst)
    print(f"Copying {src} -> {dst}")
    shutil.copytree(src, dst)


def upgrade_package(package_name: str) -> None:
    """Upgrade a package to the latest version using pip."""
    print(f"Upgrading package: {package_name}")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", package_name])


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python patch_sdk.py <kimi-agent-sdk-path> <kimi-cli-path>")
        print("Example: python patch_sdk.py D:\\kimi-agent-sdk D:\\kimi-cli")
        sys.exit(1)

    sdk_repo_path = Path(sys.argv[1]).resolve()
    cli_repo_path = Path(sys.argv[2]).resolve()

    # Validate input paths
    if not sdk_repo_path.exists():
        print(f"Error: SDK repo path does not exist: {sdk_repo_path}")
        sys.exit(1)
    if not cli_repo_path.exists():
        print(f"Error: CLI repo path does not exist: {cli_repo_path}")
        sys.exit(1)

    # Define source paths
    sdk_src = sdk_repo_path / "python" / "src" / "kimi_agent_sdk"
    cli_src = cli_repo_path / "src" / "kimi_cli"
    kaos_src = cli_repo_path / "packages" / "kaos" / "src" / "kaos"
    kosong_src = cli_repo_path / "packages" / "kosong" / "src" / "kosong"

    if not sdk_src.exists():
        print(f"Error: SDK source path does not exist: {sdk_src}")
        sys.exit(1)
    if not cli_src.exists():
        print(f"Error: CLI source path does not exist: {cli_src}")
        sys.exit(1)
    if not kaos_src.exists():
        print(f"Error: Kaos source path does not exist: {kaos_src}")
        sys.exit(1)
    if not kosong_src.exists():
        print(f"Error: Kosong source path does not exist: {kosong_src}")
        sys.exit(1)

    # Get site-packages directory
    site_packages = get_site_packages()
    print(f"Target site-packages: {site_packages}")

    # Define destination paths
    sdk_dst = site_packages / "kimi_agent_sdk"
    cli_dst = site_packages / "kimi_cli"
    kaos_dst = site_packages / "kaos"
    kosong_dst = site_packages / "kosong"

    # Copy SDK files
    copy_directory(sdk_src, sdk_dst)

    # Copy CLI files
    copy_directory(cli_src, cli_dst)

    # Copy Kaos files
    copy_directory(kaos_src, kaos_dst)

    # Copy Kosong files
    copy_directory(kosong_src, kosong_dst)

    print("\nPatch completed successfully!")


if __name__ == "__main__":
    main()
