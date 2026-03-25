#!/usr/bin/env python3
"""
Project Analysis Script

This script:
1. Analyzes the whole project structure
2. Makes a todolist
3. Starts multiple agent tasks to analyze each folder and output documents
4. Makes a summary of all documents to readme

Usage: Run this script with kimi_cli to execute the analysis workflow.
"""

from kimi_utils import *
import os
import json

# =============================================================================
# Configuration
# =============================================================================
PROJECT_ROOT = "."  # Current directory
OUTPUT_DIR = "./analysis_output"
README_PATH = "./README.md"

# =============================================================================
# Step 1: Analyze Project Structure
# =============================================================================
print("=" * 60)
print("Step 1: Analyzing Project Structure")
print("=" * 60)

structure_prompt = '''
Please analyze the project structure in the current directory.

Tasks:
1. List all directories and subdirectories recursively
2. Identify the main programming languages used
3. Find key configuration files (e.g., package.json, CMakeLists.txt, pyproject.toml, etc.)
4. Identify the project type (web app, library, CLI tool, etc.)
5. List all source code directories

Output a structured summary in JSON format with these fields:
- project_type: string
- languages: list of strings
- root_files: list of important files in root
- directories: list of objects with {name, type, description, files_count}
- config_files: list of configuration files found
'''

project_structure = prompt(structure_prompt)

# =============================================================================
# Step 2: Create Todo List
# =============================================================================
print("=" * 60)
print("Step 2: Creating Todo List")
print("=" * 60)

todo_prompt = f'''
Based on the following project structure:
{project_structure}

Please create a detailed todo list (use SetTodoList tool) for analyzing this project.

Requirements:
1. Create a todo item for each major directory that needs analysis
2. Create a todo item for summary/compilation
3. Each todo should be specific and actionable

Output format: JSON array with objects containing:
- id: unique identifier (string)
- title: brief description of the task
- target: directory or file to analyze
- status: "pending"
- output_file: where to save the analysis result
'''

# Create todo list using make_todo and get_todo from kimi_utils
valid = make_todo(todo_prompt)
if not valid:
    raise Exception('make todo failed.')
todo_result = get_todo()

# Parse todo list from the result
try:
    if todo_result and hasattr(todo_result, 'todos'):
        todos = []
        for i, item in enumerate(todo_result.todos):
            # Convert Todo object to dict format expected by the rest of the code
            if hasattr(item, 'title'):
                todo_dict = {
                    'id': str(i),
                    'title': item.title,
                    'target': item.title,  # Use title as target since Todo model doesn't have target field
                    'status': item.status if hasattr(item, 'status') else 'pending',
                    'output_file': f"{OUTPUT_DIR}/todo_{i}.md"
                }
            else:
                todo_dict = item if isinstance(item, dict) else {}
            todos.append(todo_dict)
    else:
        print("Warning: Could not get todo list")
        todos = []
except Exception as e:
    print(f"Warning: Could not parse todo list: {e}")
    todos = []

# =============================================================================
# Step 3: Start Multiple Agent Tasks for Each Folder
# =============================================================================
print("=" * 60)
print("Step 3: Starting Agent Tasks for Folder Analysis")
print("=" * 60)

def analyze_folder(folder_path, output_file):
    """Create an agent task to analyze a specific folder."""
    agent_prompt = f'''
Please analyze the folder: {folder_path}

Tasks:
1. Read all source files in this folder and subfolders
2. Understand the code structure and architecture
3. Identify key classes, functions, and modules
4. Document the purpose and functionality
5. Identify dependencies and relationships with other parts of the project
6. Look for any tests, documentation, or examples

Output Requirements:
- Save your analysis to: {output_file}
- Include a summary section at the top
- Use markdown format
- Include code examples where helpful
- Document any important patterns or conventions

Structure your output as:
# Analysis of {folder_path}

## Overview
[Brief description of what this folder contains]

## Files and Components
[List and describe each significant file/component]

## Architecture
[Describe the structure and design patterns used]

## Dependencies
[List internal and external dependencies]

## Key Functions/Classes
[Document important APIs]

## Notes
[Any additional observations]
'''
    return agent_prompt

# Create output directory
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Start analysis tasks for each directory
analysis_tasks = []
if todos:
    for todo in todos:
        if isinstance(todo, dict):
            target = todo.get('target', '')
            output_file = todo.get('output_file', f"{OUTPUT_DIR}/{todo.get('id', 'unknown')}.md")
            
            if os.path.isdir(target):
                print(f"Starting analysis task for: {target}")
                task_prompt = analyze_folder(target, output_file)
                # This would typically spawn a new agent
                # For now, we document what should happen
                analysis_tasks.append({
                    'target': target,
                    'output': output_file,
                    'prompt': task_prompt
                })

print(f"Created {len(analysis_tasks)} analysis tasks")

# =============================================================================
# Step 4: Compile Summary and Generate README
# =============================================================================
print("=" * 60)
print("Step 4: Compiling Summary and Generating README")
print("=" * 60)

readme_prompt = f'''
Please compile a comprehensive README.md based on all the analysis documents.

Project Structure:
{project_structure}

Analysis Documents Location: {OUTPUT_DIR}

Tasks:
1. Read all analysis documents from {OUTPUT_DIR}
2. Synthesize the information into a coherent project overview
3. Generate a professional README.md with the following sections:

README Structure:
# [Project Name]

## Overview
[High-level description of the project based on all analyses]

## Features
[Key features and capabilities]

## Project Structure
[Overview of directory organization]

## Installation
[Setup instructions if available]

## Usage
[How to use the project]

## Architecture
[Technical architecture summary]

## Modules/Components
[Brief description of each major component with links to detailed analysis]

## Development
[Development guidelines, conventions found in the codebase]

## Contributing
[If applicable]

## License
[If found in the project]

## Additional Notes
[Any important observations about the project]

Output:
- Save the final README to: {README_PATH}
- Ensure all sections are well-organized
- Include badges or shields if appropriate
- Add table of contents for longer READMEs
'''

print("README generation prompt prepared")

# =============================================================================
# Main Execution Flow (when run as script)
# =============================================================================
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Project Analysis Script")
    print("=" * 60)
    print("\nThis script will:")
    print("1. Analyze project structure")
    print("2. Create a todo list for analysis")
    print("3. Generate agent prompts for each folder")
    print("4. Compile everything into a README")
    print("\n" + "=" * 60)
    
    # The actual execution would use kimi_utils functions
    # This script serves as a workflow definition
    
    print("\nWorkflow defined. To execute:")
    print("  kimi_cli run prompt.py")
