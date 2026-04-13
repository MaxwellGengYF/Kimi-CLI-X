#!/usr/bin/env python3
"""
Project Analysis & Mind-Map Generation System - Main Entry Point

Usage:
    python -m graph.main <project_path> [options]
    
Example:
    python -m graph.main D:/RoboCute --batch-size 5
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from graph.project_analyzer import ProjectAnalyzer, get_language_priority
from graph.analysis_engine import AnalysisEngine
from graph.output_manager import OutputManager

from agent_utils import print_success, print_error, print_info, print_warning, print_debug
from kimi_utils import create_session, prompt, close_session
from kaos.path import KaosPath


def verify_output(output_dir: Path, project_path: Path) -> bool:
    """
    Verify generated analysis output by cross-referencing with the codebase.
    
    Args:
        output_dir: Path to the output directory containing analysis results
        project_path: Path to the original project directory
    
    Returns:
        True if verification passed, False otherwise
    """
    from datetime import datetime
    import json
    
    print_info("")
    print_info("=" * 60)
    print_info("Step 6: Verifying analysis output...")
    print_info("=" * 60)
    
    # Create a new independent session for verification
    session_id = f"verify_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    session = create_session(
        session_id=session_id,
        work_dir=KaosPath(str(project_path)),
        thinking=True,
        yolo=True,
        agent_file=Path('agent_subagent.yaml'),
        plan_mode=True
    )
    
    try:
        # Read the generated files
        mindmap_file = output_dir / 'mindmap.md'
        keywords_file = output_dir / 'keywords.json'
        api_file = output_dir / 'api_reference.json'
        index_file = output_dir / 'index.json'
        
        verification_results = []
        
        # Check if files exist
        for f in [mindmap_file, keywords_file, api_file, index_file]:
            if f.exists():
                verification_results.append(f"✓ {f.name} exists")
            else:
                verification_results.append(f"✗ {f.name} missing")
        
        # Read keywords for validation
        keywords_data = {}
        if keywords_file.exists():
            try:
                with open(keywords_file, 'r', encoding='utf-8') as f:
                    keywords_data = json.load(f)
                verification_results.append(f"✓ Loaded {len(keywords_data.get('keywords', []))} keywords")
            except Exception as e:
                verification_results.append(f"✗ Error loading keywords: {e}")
        
        # Read APIs for validation
        api_data = {}
        if api_file.exists():
            try:
                with open(api_file, 'r', encoding='utf-8') as f:
                    api_data = json.load(f)
                verification_results.append(f"✓ Loaded {len(api_data.get('apis', []))} APIs")
            except Exception as e:
                verification_results.append(f"✗ Error loading APIs: {e}")
        
        # Build verification prompt
        verification_prompt = f'''Verify the following analysis output against the project codebase.

## Generated Files Location
{output_dir}

## Verification Tasks

1. **Validate Keywords**: Check if extracted keywords are relevant to the project
   - Use GrepAnalyzer to search for key terms in the codebase
   - Verify they appear in actual source files

2. **Validate APIs**: Cross-check extracted APIs
   - Use GrepAnalyzer to search for function/class definitions
   - Verify they exist in the codebase

3. **Validate File Paths**: Check if referenced files exist
   - Verify paths mentioned in the analysis exist in the project

## Keywords to Validate
{json.dumps(keywords_data.get('keywords', [])[:20], indent=2)}

## APIs to Validate
{json.dumps([api.get('name', '') for api in api_data.get('apis', [])[:20]], indent=2)}

## Instructions
- Use GrepAnalyzer tool to search for patterns and validate information
- Report any discrepancies found
- Provide confidence score for the analysis accuracy

## Output Format

```markdown
# Verification Report

## Summary
- Total keywords checked: X
- Total APIs checked: X
- Files validated: X

## Keyword Validation
| Keyword | Found in Codebase | Confidence |
|---------|-------------------|------------|
| keyword | Yes/No | High/Medium/Low |

## API Validation
| API | Found | Location | Confidence |
|-----|-------|----------|------------|
| api_name | Yes/No | file_path | High/Medium/Low |

## Issues Found
List any discrepancies or errors found.

## Overall Assessment
Overall confidence score and recommendations.
```
'''
        
        # Run verification
        verification_output = []
        def capture_output(text):
            verification_output.append(text)
        
        print_info("Running verification with GrepAnalyzer...")
        prompt(verification_prompt, session=session, output_function=capture_output)
        
        verification_text = '\n'.join(verification_output)
        
        # Save verification report
        report_file = output_dir / 'VERIFICATION_REPORT.md'
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("# Analysis Verification Report\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("## File Status\n\n")
            for result in verification_results:
                f.write(f"- {result}\n")
            f.write("\n## Detailed Verification\n\n")
            f.write(verification_text)
        
        print_success(f"Verification report saved: {report_file}")
        
        # Print summary
        print_info("")
        print_info("Verification Summary:")
        for result in verification_results:
            print_info(f"  {result}")
        
        return True
        
    except Exception as e:
        print_error(f"Verification failed: {e}")
        return False
    finally:
        close_session(session)


def analyze_project(project_path: str, output_dir: str = None, 
                   batch_size: int = 5, max_lines: int = 500,
                   analyze_mode: str = 'mixed', verify: bool = True) -> bool:
    """
    Analyze a project and generate mind-map documentation.
    
    Args:
        project_path: Path to the project directory
        output_dir: Output directory for results (default: [project]/agent_doc)
        batch_size: Maximum files per batch analysis
        max_lines: Maximum lines per batch
        analyze_mode: 'single', 'batch', or 'mixed'
    
    Returns:
        True if successful, False otherwise
    """
    project_path = Path(project_path).resolve()
    
    if not project_path.exists():
        print_error(f"Project path does not exist: {project_path}")
        return False
    
    if not project_path.is_dir():
        print_error(f"Project path is not a directory: {project_path}")
        return False
    
    print_success("=" * 60)
    print_success("Project Analysis & Mind-Map Generation System")
    print_success("=" * 60)
    print_info(f"Project: {project_path}")
    print_info(f"Mode: {analyze_mode}")
    print_info(f"Batch Size: {batch_size}")
    print_info("")
    
    # Initialize analyzer
    print_info("Step 1: Scanning project structure...")
    analyzer = ProjectAnalyzer(str(project_path))
    
    # Get project structure
    structure = analyzer.get_project_structure()
    print_success(f"Found {structure['total_files']} files")
    print_success(f"Total lines: {structure['total_lines']:,}")
    print_success(f"Languages: {', '.join(structure['languages'].keys())}")
    print_info("")
    
    # Initialize analysis engine
    print_info("Step 2: Initializing analysis engine...")
    engine = AnalysisEngine(str(project_path), output_dir)
    
    # Traverse files
    print_info("Step 3: Traversing project files...")
    files = analyzer.traverse()
    print_success(f"Found {len(files)} analyzable files")
    print_info("")
    
    # Filter out files that are too small or non-code
    files = [f for f in files if f.lines > 5]  # Skip very small files
    print_info(f"After filtering: {len(files)} files to analyze")
    print_info("")
    
    if len(files) == 0:
        print_warning("No files to analyze!")
        return False
    
    # Analyze files
    print_info("Step 4: Analyzing files...")
    print_info("-" * 40)
    
    # Handle config files separately
    config_files = [f for f in files if analyzer.is_config_file(f.path)]
    code_files = [f for f in files if not analyzer.is_config_file(f.path)]
    
    print_info(f"Config files: {len(config_files)}")
    print_info(f"Code files: {len(code_files)}")
    print_info("")
    
    # Analyze config files
    if config_files:
        print_info("Analyzing configuration files...")
        for f in config_files[:3]:  # Limit config files
            engine.analyze_config_file(f)
        print_info("")
    
    # Analyze code files based on mode
    if analyze_mode == 'single':
        # Analyze each file individually
        print_info("Analyzing code files individually...")
        for i, f in enumerate(code_files):
            print_info(f"[{i+1}/{len(code_files)}] ", end='')
            engine.analyze_file(f)
            
    elif analyze_mode == 'batch':
        # Create batches by directory
        print_info("Analyzing code files in batches...")
        batches = analyzer.create_batches(code_files, batch_size, max_lines)
        print_info(f"Created {len(batches)} batches")
        print_info("")
        
        max_batches = 3  # Limit for testing
        for i, batch in enumerate(batches[:max_batches]):
            component = batch[0].relative_path.split('/')[0] if batch and batch[0].relative_path else 'unknown'
            print_info(f"[{i+1}/{min(len(batches), max_batches)}] Analyzing batch: {component}")
            engine.analyze_batch(batch, component)
            
    elif analyze_mode == 'mixed':
        # Mix of single and batch based on file size
        print_info("Analyzing with mixed strategy...")
        
        # Small directories get batched, large files get individual analysis
        by_dir = analyzer.group_by_directory(code_files)
        
        for dir_path, dir_files in by_dir.items():
            if len(dir_files) <= 2:
                # Analyze individually
                for f in dir_files:
                    engine.analyze_file(f)
            else:
                # Batch analyze
                batches = analyzer.create_batches(dir_files, batch_size, max_lines)
                for batch in batches:
                    engine.analyze_batch(batch, dir_path)
    
    print_info("")
    print_info("-" * 40)
    
    # Save results
    print_info("Step 5: Saving results...")
    engine.save_results()
    
    # Generate additional outputs using OutputManager
    output_manager = OutputManager(engine.output_dir)
    
    # Save RAG-friendly keywords
    rag_file = output_manager.save_keywords_rag(engine.all_results)
    print_success(f"RAG keywords saved: {rag_file}")
    
    # Generate summary report
    report = output_manager.generate_summary_report(
        engine.project_name, 
        engine.all_results,
        analyzer
    )
    report_file = engine.output_dir / 'ANALYSIS_REPORT.md'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print_success(f"Summary report saved: {report_file}")
    
    print_info("")
    print_success("=" * 60)
    print_success("Analysis Complete!")
    print_success("=" * 60)
    print_info(f"Results saved to: {engine.output_dir}")
    print_info("")
    print_info("Generated files:")
    print_info("  - mindmap.md - Project mind-map and overview")
    print_info("  - keywords.json - Extracted keywords")
    print_info("  - api_reference.json - API documentation")
    print_info("  - index.json - Master index")
    print_info("  - analyses/ - Individual file analyses")
    print_info("  - keywords_rag.json - RAG-friendly keyword index")
    print_info("  - ANALYSIS_REPORT.md - Summary report")
    
    # Step 6: Verify output if requested
    if verify:
        verify_output(engine.output_dir, project_path)
    
    return True


def main(args = None):
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Analyze a code project and generate mind-map documentation.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m graph.main D:/RoboCute
  python -m graph.main /path/to/project --batch-size 3 --mode batch
  python -m graph.main ./my-project --output ./docs
        """
    )
    
    parser.add_argument(
        'project_path',
        help='Path to the project directory to analyze'
    )
    
    parser.add_argument(
        '--output', '-o',
        default=None,
        help='Output directory (default: [project]/agent_doc)'
    )
    
    parser.add_argument(
        '--batch-size', '-b',
        type=int,
        default=5,
        help='Maximum files per batch (default: 5)'
    )
    
    parser.add_argument(
        '--max-lines', '-l',
        type=int,
        default=500,
        help='Maximum lines per batch (default: 500)'
    )
    
    parser.add_argument(
        '--mode', '-m',
        choices=['single', 'batch', 'mixed'],
        default='mixed',
        help='Analysis mode: single, batch, or mixed (default: mixed)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    parser.add_argument(
        '--no-verify',
        action='store_true',
        help='Skip verification step after generation'
    )
    
    args = parser.parse_args(args)
    
    # Set verbose mode
    if args.verbose:
        import agent_utils
        agent_utils._quiet = False
    # Run analysis
    success = analyze_project(
        project_path=args.project_path,
        output_dir=args.output,
        batch_size=args.batch_size,
        max_lines=args.max_lines,
        analyze_mode=args.mode,
        verify=not args.no_verify
    )
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
