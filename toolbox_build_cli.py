#!/usr/bin/env python3
"""
Build script for kimi_cli project.
Pulls all git submodules defined in .gitmodules.
"""

import subprocess
import sys
from pathlib import Path
import configparser
from concurrent.futures import ThreadPoolExecutor, as_completed


def parse_gitmodules(gitmodules_path: Path) -> list[dict]:
    """
    Parse .gitmodules file and extract submodule information.
    
    Args:
        gitmodules_path: Path to .gitmodules file
        
    Returns:
        List of dictionaries containing submodule info (name, path, url, branch)
    """
    submodules = []
    if not gitmodules_path.exists():
        return submodules
    
    config = configparser.ConfigParser()
    config.read(gitmodules_path)
    
    for section in config.sections():
        if section.startswith('submodule '):
            name = section[10:].strip('"')
            submodule = {
                'name': name,
                'path': config.get(section, 'path', fallback=name),
                'url': config.get(section, 'url', fallback=''),
                'branch': config.get(section, 'branch', fallback='main')
            }
            submodules.append(submodule)
    
    return submodules


def _update_single_submodule(submodule: dict, current_dir: Path) -> tuple[str, bool]:
    """
    Worker function to update (clone or pull) a single submodule.
    
    Args:
        submodule: Dictionary containing submodule info
        current_dir: Base directory path
        
    Returns:
        Tuple of (submodule name, success status)
    """
    name = submodule['name']
    path = current_dir / submodule['path']
    url = submodule['url']
    branch = submodule['branch']
    
    if path.exists() and (path / '.git').exists():
        # Submodule already exists, pull latest
        print(f"[PULL] {name} -> {submodule['path']}")
        try:
            result = subprocess.run(
                ['git', 'pull', 'origin', branch],
                cwd=path,
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                print(f"  [OK] Pulled latest changes ({name})")
                return name, True
            else:
                print(f"  [WARN] Pull failed: {result.stderr.strip()} ({name})")
                return name, False
        except Exception as e:
            print(f"  [FAIL] Error pulling: {e} ({name})")
            return name, False
    else:
        # Submodule doesn't exist, clone it
        print(f"[CLONE] {name} -> {submodule['path']}")
        try:
            result = subprocess.run(
                ['git', 'clone', '--branch', branch, url, str(path)],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                print(f"  [OK] Cloned successfully ({name})")
                return name, True
            else:
                print(f"  [FAIL] Clone failed: {result.stderr.strip()} ({name})")
                return name, False
        except Exception as e:
            print(f"  [FAIL] Error cloning: {e} ({name})")
            return name, False


def update_submodules() -> bool:
    """
    Parse .gitmodules and clone or pull all submodules using multi-threading.
    
    Returns:
        True if all submodules are up to date, False otherwise
    """
    current_dir = Path.cwd()
    gitmodules_path = current_dir / '.gitmodules'
    
    if not gitmodules_path.exists():
        print("No .gitmodules file found, skipping submodule update.")
        return True
    
    submodules = parse_gitmodules(gitmodules_path)
    
    if not submodules:
        print("No submodules defined in .gitmodules.")
        return True
    
    print(f"Found {len(submodules)} submodule(s) in .gitmodules")
    print("-" * 50)
    
    all_success = True
    
    # Use ThreadPoolExecutor for concurrent submodule updates
    with ThreadPoolExecutor() as executor:
        # Submit all tasks
        future_to_submodule = {
            executor.submit(_update_single_submodule, submodule, current_dir): submodule
            for submodule in submodules
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_submodule):
            submodule = future_to_submodule[future]
            try:
                name, success = future.result()
                if not success:
                    all_success = False
            except Exception as e:
                print(f"  [FAIL] Unexpected error processing {submodule['name']}: {e}")
                all_success = False
    
    print("-" * 50)
    return all_success


def main():
    if not update_submodules():
        print('Pull failed.')


if __name__ == "__main__":
    main()
