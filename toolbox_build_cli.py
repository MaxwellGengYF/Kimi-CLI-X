#!/usr/bin/env python3
"""
Build script for kimi_cli project.
Recursively finds all pyproject.toml files under the project directory and installs dependencies.
"""

import argparse
import subprocess
import sysconfig
import sys
import tomllib
from pathlib import Path
import shutil
import zipfile
# Cull list: packages that should NOT be installed
CULL_LIST = ['kimi-agent-sdk', 'kimi-cli', 'kaos', 'kosong']

# Global array to collect all dependencies
collected_deps = []


def is_culled(dep: str) -> bool:
    """
    Check if a dependency is in the cull list.
    
    Args:
        dep: Dependency string (e.g., 'package-name>=1.0')
        
    Returns:
        True if the dependency should be culled (not installed)
    """
    # Extract package name from dependency string (remove version specifiers)
    dep_name = dep.split('[')[0].split('=')[0].split('<')[0].split('>')[0].split('!')[0].split(';')[0].strip().lower()
    return dep_name in CULL_LIST


def find_pyproject_files(project_dir: str) -> list[Path]:
    """
    Recursively find all pyproject.toml files under the project directory.
    
    Args:
        project_dir: Path to the project directory
        
    Returns:
        List of paths to pyproject.toml files
    """
    project_path = Path(project_dir).resolve()
    
    if not project_path.exists():
        print(f"Error: Directory '{project_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)
    
    if not project_path.is_dir():
        print(f"Error: '{project_dir}' is not a directory.", file=sys.stderr)
        sys.exit(1)
    
    # Recursively find all pyproject.toml files
    pyproject_files = list(project_path.rglob("pyproject.toml"))
    
    # Sort for consistent output
    pyproject_files.sort()
    
    return pyproject_files


def parse_dependencies(pyproject_path: Path) -> dict[str, list[str]]:
    """
    Parse pyproject.toml and extract dependencies.
    
    Args:
        pyproject_path: Path to pyproject.toml file
        
    Returns:
        Dictionary with 'dependencies' and 'optional' keys
    """
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    
    project = data.get("project", {})
    
    # Get main dependencies
    dependencies = project.get("dependencies", [])
    
    # Get optional dependencies (extras)
    optional_deps = project.get("optional-dependencies", {})
    
    return {
        "dependencies": dependencies,
        "optional": optional_deps
    }


def install_dependencies(deps: list[str], package_name: str = "unknown") -> bool:
    """
    Install dependencies using pip.
    
    Args:
        deps: List of dependency strings
        package_name: Name of the package being installed (for logging)
        
    Returns:
        True if installation succeeded, False otherwise
    """
    if not deps:
        return True
    
    # Filter out culled dependencies
    deps = [dep for dep in deps if not is_culled(dep)]
    
    if not deps:
        print(f"\n  All dependencies culled, nothing to install")
        return True
    
    print(f"\n  Installing {len(deps)} dependency(ies)...")
    
    for dep in deps:
        print(f"    - {dep}")
        collected_deps.append(dep)
    
    # Run pip install
    cmd = [sys.executable, "-m", "pip", "install"] + deps
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            print(f"  [OK] Dependencies installed successfully")
            return True
        else:
            print(f"  [FAIL] Failed to install dependencies", file=sys.stderr)
            if result.stderr:
                print(f"    Error: {result.stderr}", file=sys.stderr)
            return False
            
    except Exception as e:
        print(f"  [FAIL] Error running pip: {e}", file=sys.stderr)
        return False



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
    subprocess.check_call([sys.executable, "-m", "pip",
                          "install", "--upgrade", package_name])


def copy_package(sdk_repo_path, cli_repo_path, packages_path) -> None:

    packages_path = Path(packages_path).resolve()
    sdk_repo_path = Path(sdk_repo_path).resolve()
    cli_repo_path = Path(cli_repo_path).resolve()

    # Validate input paths
    if not sdk_repo_path.exists():
        print(f"Error: SDK repo path does not exist: {sdk_repo_path}")
        sys.exit(1)
    if not packages_path.exists():
        print(f"Error: package path does not exist: {packages_path}")
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
    print(f"Target site-packages: {packages_path}")

    # Define destination paths
    sdk_dst = packages_path / "kimi_agent_sdk"
    cli_dst = packages_path / "kimi_cli"
    kaos_dst = packages_path / "kaos"
    kosong_dst = packages_path / "kosong"

    # Copy SDK files
    copy_directory(sdk_src, sdk_dst)

    # Copy CLI files
    copy_directory(cli_src, cli_dst)

    # Copy Kaos files
    copy_directory(kaos_src, kaos_dst)

    # Copy Kosong files
    copy_directory(kosong_src, kosong_dst)

    print("\nPatch completed successfully!")


def package_project(target_dir: str, output_name: str) -> None:
    """
    Zip all folders and scripts under current directory to a target directory.
    
    Args:
        target_dir: Path to the target directory for the zip file
        output_name: Name of the output zip file (without extension)
    """
    target_path = Path(target_dir).resolve()
    current_dir = Path.cwd()
    
    # Create target directory if it doesn't exist
    target_path.mkdir(parents=True, exist_ok=True)
    
    # Define output zip file path
    zip_file_path = target_path / f"{output_name}.zip"
    
    # Remove existing zip file if it exists
    if zip_file_path.exists():
        print(f"Removing existing zip file: {zip_file_path}")
        zip_file_path.unlink()
    
    # Exclusion list
    excluded_files = {"toolbox_build_cli.py", '.gitignore', '.gitmodule'}
    excluded_dirs = {"__pycache__", '.git', '.pytest_cache', '.agents'}
    
    print(f"Packaging contents of: {current_dir}")
    print(f"Output zip: {zip_file_path}")
    print("-" * 50)
    dirs = []
    for i in current_dir.iterdir():
        dirs.append(i)
    with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for item in dirs:
            # Skip the target directory itself (to avoid recursion if target is under current dir)
            if item.resolve() == target_path.resolve():
                continue
            
            if item.is_file():
                # Skip excluded files
                if item.name in excluded_files:
                    print(f"  [SKIP] File: {item.name}")
                    continue
                print(f"  [ADD] File: {item.name}")
                zipf.write(item, item.name)
            elif item.is_dir():
                # Skip excluded directories
                if item.name in excluded_dirs:
                    print(f"  [SKIP] Dir:  {item.name}/")
                    continue
                print(f"  [ADD] Dir:  {item.name}/")
                # Recursively add directory contents
                for file_path in item.rglob("*"):
                    # Skip __pycache__ directories anywhere in the tree
                    if "__pycache__" in file_path.parts:
                        continue
                    # Skip excluded files
                    if file_path.name in excluded_files:
                        continue
                    arcname = file_path.relative_to(current_dir)
                    zipf.write(file_path, arcname)
    
    print("-" * 50)
    print(f"[OK] Package created successfully: {zip_file_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Build script for kimi_cli project."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Build command
    build_parser = subparsers.add_parser(
        "build",
        help="Find all pyproject.toml files recursively and install dependencies."
    )
    build_parser.add_argument(
        "project_dir",
        help="Path to the kimi_cli project directory"
    )
    build_parser.add_argument(
        "--with-optional",
        action="store_true",
        help="Also install optional dependencies (extras)"
    )
    build_parser.add_argument(
        "--optional-groups",
        nargs="+",
        default=[],
        help="Specific optional dependency groups to install (e.g., 'dev', 'test')"
    )
    
    # Copy command
    copy_parser = subparsers.add_parser(
        "copy",
        help="Copy packages from source repos to site-packages."
    )
    copy_parser.add_argument(
        "sdk_repo_path",
        help="Path to the kimi-agent-sdk repository"
    )
    copy_parser.add_argument(
        "cli_repo_path",
        help="Path to the kimi-cli repository"
    )
    copy_parser.add_argument(
        "packages_path",
        help="Path to the target site-packages directory"
    )
    
    # Package command
    package_parser = subparsers.add_parser(
        "package",
        help="Zip all folders and scripts to a target directory."
    )
    package_parser.add_argument(
        "target_dir",
        help="Path to the target directory for the zip file"
    )
    package_parser.add_argument(
        "--output-name",
        default="package",
        help="Name of the output zip file (without extension)"
    )
    
    args = parser.parse_args()
    
    if args.command == "copy":
        copy_package(args.sdk_repo_path, args.cli_repo_path, args.packages_path)
    elif args.command == "package":
        package_project(args.target_dir, args.output_name)
    elif args.command == "build":
        print(f"Scanning project directory: {args.project_dir}")
        print("-" * 50)
        
        pyproject_files = find_pyproject_files(args.project_dir)
        
        if not pyproject_files:
            print("No pyproject.toml files found.")
            return
        
        print(f"Found {len(pyproject_files)} pyproject.toml file(s)\n")
        
        all_success = True
        
        for i, file_path in enumerate(pyproject_files, 1):
            # Get relative path from project root for cleaner output
            rel_path = file_path.relative_to(Path(args.project_dir).resolve())
            print(f"[{i}/{len(pyproject_files)}] Processing: {rel_path}")
            
            # Parse dependencies
            deps_info = parse_dependencies(file_path)
            
            # Install main dependencies
            if deps_info["dependencies"]:
                print(f"  Main dependencies:")
                success = install_dependencies(deps_info["dependencies"])
                if not success:
                    all_success = False
            else:
                print(f"  No main dependencies to install")
            
            # Install optional dependencies if requested
            if args.with_optional or args.optional_groups:
                optional_deps = deps_info["optional"]
                
                if not optional_deps:
                    print(f"  No optional dependencies defined")
                else:
                    for group_name, group_deps in optional_deps.items():
                        # Install if --with-optional or specific group requested
                        if args.with_optional or group_name in args.optional_groups:
                            print(f"\n  Optional dependencies [{group_name}]:")
                            success = install_dependencies(group_deps, package_name=group_name)
                            if not success:
                                all_success = False
            
            print()
        
        # Export collected dependencies to requirements.txt
        if collected_deps:
            req_path = "requirements.txt"
            with open(req_path, "w") as f:
                for dep in sorted(set(collected_deps)):
                    f.write(f"{dep}\n")
            print(f"Exported {len(set(collected_deps))} unique dependencies to {req_path}")
        
        print("-" * 50)
        if all_success:
            print("✓ All dependencies installed successfully")
        else:
            print("✗ Some dependencies failed to install", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
