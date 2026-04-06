# Build Documentation

This document describes the build system and tools for the Kimi Agent CLI project.

## Build Script (`toolbox_build_cli.py`)

A build utility for the kimi_cli project that handles dependency installation and package copying.

### Commands

#### `build` - Install Dependencies

Recursively finds all `pyproject.toml` files under a project directory and installs their dependencies.

```bash
python toolbox_build_cli.py build <project_dir> [options]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--with-optional` | Also install optional dependencies (extras) |
| `--optional-groups <groups>` | Specific optional dependency groups to install (e.g., `dev`, `test`) |

**Examples:**

```bash
# Install dependencies for the current project
python toolbox_build_cli.py build

# Install with all optional dependencies
python toolbox_build_cli.py build --with-optional

# Install with specific optional groups
python toolbox_build_cli.py build --optional-groups dev test
```

#### `copy` - Copy Packages

Copies package source files from development repositories to the site-packages directory. This is useful for testing local changes without reinstalling packages.

```bash
python toolbox_build_cli.py copy
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `sdk_repo_path` | Path to the kimi-agent-sdk repository |
| `cli_repo_path` | Path to the kimi-cli repository |
| `packages_path` | Path to the target site-packages directory |

**Example:**

```bash
python toolbox_build_cli.py copy D:/kimi-agent-sdk D:/kimi-cli D:/venv/Lib/site-packages
```

**What gets copied:**
- `kimi_agent_sdk` from `<sdk_repo_path>/python/src/kimi_agent_sdk`
- `kimi_cli` from `<cli_repo_path>/src/kimi_cli`
- `kaos` from `<cli_repo_path>/packages/kaos/src/kaos`
- `kosong` from `<cli_repo_path>/packages/kosong/src/kosong`

#### `package` - Create Distribution Package

Packages the current project directory into a zip file, excluding build scripts and cache directories.

```bash
python toolbox_build_cli.py package [--output-name NAME]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `target_dir` | Path to the target directory where the zip file will be created |
| `--output-name` | (Optional) Name of the output zip file without extension (default: `package`) |

**Excluded Items:**
- `toolbox_build_cli.py` - The build script itself
- `agent.py` - Agent script
- `__pycache__` folders - Python cache directories (anywhere in the tree)

**Examples:**

```bash
# Create package.zip in the dist directory
python toolbox_build_cli.py package

# Create a named package
python toolbox_build_cli.py package ./dist --output-name myproject-v1.0
```
