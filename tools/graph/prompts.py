"""
Prompt templates for project analysis.
"""

from string import Template

# Main analysis prompt for code files
CODE_ANALYSIS_PROMPT = Template('''
You are analyzing the following code file(s) from a software project.

## File Information
$file_info

## Code Content
```$language
$code_content
```

## Analysis Instructions

Please analyze this code using **concise but comprehensive language**. Focus on extracting the following information:

### 1. API References
- Public functions, classes, methods, and their signatures
- Export/Import statements and module dependencies
- Interface definitions (for all supported languages)

### 2. Keywords for RAG System
Extract 10-20 relevant keywords that would help a RAG system match queries to this code:
- Technical terms
- Function names
- Class names
- Domain-specific vocabulary
- Framework/library names

### 3. Code Explanations
For each significant API or complex logic, provide:
- Brief explanation (1-2 sentences)
- Code block example showing usage
- Key comments explaining the "why" not just "what"

### 4. Features & Capabilities
- Main functionality provided
- Key features implemented
- Design patterns used

### 5. Usage Examples
Show practical usage examples in code blocks where applicable.

## Output Format

Return your analysis in this structured format:

```markdown
## File: $file_path

### Overview
Brief description of what this code does.

### API Reference
| Name | Type | Signature | Description |
|------|------|-----------|-------------|
| name | function/class/variable | signature | brief description |

### Keywords
`keyword1`, `keyword2`, `keyword3`, ...

### Code Explanations

#### `function_name()`
Brief explanation of what it does.

```$language
// Usage example
function_name(args);
```

### Features
- Feature 1: description
- Feature 2: description

### Dependencies
- dependency1: purpose
- dependency2: purpose
```

Be thorough but concise. Use bullet points and tables for readability.
''')

# Summary prompt for combining multiple analyses
SUMMARY_PROMPT = Template('''
You are creating a project-wide summary based on analyzed code files.

## Analyzed Components
$components

## Individual Analyses
$analyses

## Summary Instructions

Create a comprehensive project summary that includes:

### 1. Project Overview
- Project purpose and main functionality
- Architecture overview
- Technology stack

### 2. Module Hierarchy (Mind-Map Structure)
Create a hierarchical mind-map showing:
- Main modules/components
- Sub-modules and their relationships
- Entry points and core files

### 3. Key APIs (Consolidated)
List the most important APIs across all files with:
- File location
- Purpose
- Usage frequency/importance

### 4. Global Keywords
Consolidated list of keywords for RAG indexing (30-50 terms).

### 5. Entry Points & Usage
- How to start/use the project
- Main configuration files
- Important scripts/commands

## Output Format

```markdown
# Project Mind-Map: $project_name

## Overview
Brief project description.

## Architecture
```
Root/
├── Module A/
│   ├── Sub-module A1
│   └── Sub-module A2
├── Module B/
│   └── ...
```

## Key APIs
| API | File | Purpose | Importance |
|-----|------|---------|------------|

## Keywords
`keyword1`, `keyword2`, ...

## Entry Points
1. **Main Entry**: `file/path` - description
2. **Config**: `config/path` - description

## Dependencies
List of external dependencies.
```
''')

# File batch analysis prompt for multiple related files
BATCH_ANALYSIS_PROMPT = Template('''
Analyze the following batch of related code files from the same project component.

## Component: $component_name

## Files to Analyze
$file_list

## Code Contents
$code_contents

## Instructions

Analyze these files as a cohesive unit. Focus on:
1. **Inter-file relationships** - How these files interact
2. **Shared APIs** - Functions/classes used across files
3. **Module boundaries** - Clear separation of concerns
4. **Data flow** - How data moves between these files

Use **concise but comprehensive language**. Generate code-block explanations for key interactions.

Extract keywords for RAG matching covering:
- Cross-file function calls
- Shared data structures
- Component-level concepts

## Output Format

```markdown
## Component: $component_name

### Files Overview
| File | Purpose | Lines |
|------|---------|-------|

### Relationships
Description of how files interact.

### Shared APIs
| API | Defined In | Used By | Purpose |
|-----|------------|---------|---------|

### Data Flow
```
// Example showing data flow
```

### Keywords
`keyword1`, `keyword2`, ...

### Usage Patterns
Common usage patterns across these files.
```
''')

# Configuration file analysis prompt
CONFIG_ANALYSIS_PROMPT = Template('''
Analyze the following configuration file.

## File: $file_path
## Type: $config_type

## Content
```
$content
```

## Instructions

Extract:
1. **Configuration Options** - All available settings
2. **Default Values** - Default configurations
3. **Dependencies** - What this config affects
4. **Usage** - How to modify/use this config
5. **Keywords** - For RAG matching

## Output Format

```markdown
## Config: $file_name

### Purpose
Brief description.

### Options
| Option | Type | Default | Description |
|--------|------|---------|-------------|

### Usage Example
```$config_type
# Example configuration
```

### Keywords
`keyword1`, `keyword2`, ...
```
''')


def build_code_analysis_prompt(file_path: str, language: str, code_content: str, file_info: dict = None) -> str:
    """Build the code analysis prompt for a single file."""
    info_str = f"""
- File Path: `{file_path}`
- Language: {language}
- Size: {file_info.get('size', 'unknown')} bytes
- Lines: {file_info.get('lines', 'unknown')}
""" if file_info else f"""
- File Path: `{file_path}`
- Language: {language}
"""
    
    return CODE_ANALYSIS_PROMPT.substitute(
        file_info=info_str,
        language=language,
        code_content=code_content[:8000] if len(code_content) > 8000 else code_content,
        file_path=file_path
    )


def build_batch_analysis_prompt(component_name: str, files: list) -> str:
    """Build the batch analysis prompt for multiple related files."""
    file_list = "\n".join([f"- `{f['path']}` ({f.get('language', 'unknown')})" for f in files])
    
    code_contents = ""
    for f in files:
        content = f.get('content', '')
        if len(content) > 3000:
            content = content[:3000] + "\n... (truncated)"
        code_contents += f"\n### File: {f['path']}\n```{f.get('language', 'text')}\n{content}\n```\n"
    
    return BATCH_ANALYSIS_PROMPT.substitute(
        component_name=component_name,
        file_list=file_list,
        code_contents=code_contents
    )


def build_summary_prompt(project_name: str, components: list, analyses: list) -> str:
    """Build the summary prompt for project-wide analysis."""
    components_str = "\n".join([f"- {c['name']}: {c.get('description', 'N/A')}" for c in components])
    
    # Truncate analyses to avoid overwhelming the context
    analyses_str = ""
    for i, analysis in enumerate(analyses[:10]):  # Limit to first 10
        analyses_str += f"\n### Analysis {i+1}\n{analysis[:500]}...\n"
    
    if len(analyses) > 10:
        analyses_str += f"\n... and {len(analyses) - 10} more analyses\n"
    
    return SUMMARY_PROMPT.substitute(
        project_name=project_name,
        components=components_str,
        analyses=analyses_str
    )


def build_config_analysis_prompt(file_path: str, config_type: str, content: str) -> str:
    """Build the config file analysis prompt."""
    file_name = file_path.split('/')[-1] if '/' in file_path else file_path
    
    return CONFIG_ANALYSIS_PROMPT.substitute(
        file_path=file_path,
        file_name=file_name,
        config_type=config_type,
        content=content[:5000] if len(content) > 5000 else content
    )
