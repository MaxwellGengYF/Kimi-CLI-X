"""
Output Manager - Format and save analysis results.
"""

import json
from pathlib import Path
from typing import List, Dict
from datetime import datetime

from .analysis_engine import AnalysisResult


class OutputManager:
    """Manages formatting and saving of analysis results."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def format_mindmap(self, project_name: str, results: List[AnalysisResult], 
                       structure: Dict) -> str:
        """Format analysis results as a markdown mind-map."""
        lines = [
            f"# Project Mind-Map: {project_name}",
            "",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Table of Contents",
            "",
            "1. [Overview](#overview)",
            "2. [Architecture](#architecture)",
            "3. [Components](#components)",
            "4. [API Reference](#api-reference)",
            "5. [Keywords](#keywords)",
            "",
            "---",
            "",
            "## Overview",
            "",
        ]
        
        # Add overview from structure
        lines.append(f"**Project Path:** `{structure.get('project_path', 'N/A')}`")
        lines.append("")
        lines.append(f"**Total Files Analyzed:** {structure.get('total_files', 0)}")
        lines.append("")
        lines.append(f"**Total Lines of Code:** {structure.get('total_lines', 0):,}")
        lines.append("")
        
        # Language breakdown
        if 'languages' in structure and structure['languages']:
            lines.append("### Languages")
            lines.append("")
            for lang, count in sorted(structure['languages'].items(), key=lambda x: -x[1]):
                lines.append(f"- **{lang}**: {count} files")
            lines.append("")
        
        # Architecture section
        lines.extend([
            "## Architecture",
            "",
            "```",
        ])
        
        # Build tree structure
        if 'directories' in structure:
            tree = self._build_tree(structure['directories'])
            lines.extend(tree)
        
        lines.extend([
            "```",
            "",
        ])
        
        # Components section
        lines.extend([
            "## Components",
            "",
        ])
        
        # Group results by component
        by_component = {}
        for result in results:
            comp = result.component
            if comp not in by_component:
                by_component[comp] = []
            by_component[comp].append(result)
        
        for comp, comp_results in sorted(by_component.items()):
            lines.append(f"### {comp}")
            lines.append("")
            for r in comp_results:
                lines.append(f"- `{r.file_path}`")
            lines.append("")
        
        # API Reference section
        lines.extend([
            "## API Reference",
            "",
        ])
        
        all_apis = []
        for result in results:
            all_apis.extend(result.apis)
        
        if all_apis:
            lines.append("| Name | Type | Description |")
            lines.append("|------|------|-------------|")
            seen = set()
            for api in all_apis[:50]:  # Limit to top 50 APIs
                name = api.get('name', '')
                if name and name not in seen:
                    seen.add(name)
                    api_type = api.get('type', 'unknown')
                    desc = api.get('description', '')[:50]
                    lines.append(f"| `{name}` | {api_type} | {desc} |")
            lines.append("")
        else:
            lines.append("*No APIs extracted from analysis.*")
            lines.append("")
        
        # Keywords section
        lines.extend([
            "## Keywords",
            "",
        ])
        
        all_keywords = set()
        for result in results:
            all_keywords.update(result.keywords)
        
        if all_keywords:
            keywords_list = sorted(list(all_keywords))
            lines.append("### All Keywords")
            lines.append("")
            lines.append(", ".join([f"`{kw}`" for kw in keywords_list]))
            lines.append("")
        
        # Entry points
        if 'entry_points' in structure and structure['entry_points']:
            lines.extend([
                "## Entry Points",
                "",
            ])
            for ep in structure['entry_points']:
                lines.append(f"- `{ep}`")
            lines.append("")
        
        # Config files
        if 'config_files' in structure and structure['config_files']:
            lines.extend([
                "## Configuration Files",
                "",
            ])
            for cf in structure['config_files']:
                lines.append(f"- `{cf}`")
            lines.append("")
        
        return '\n'.join(lines)
    
    def _build_tree(self, directories: List[str]) -> List[str]:
        """Build an ASCII tree from directory list."""
        if not directories:
            return []
        
        # Sort and organize
        dirs = sorted([d for d in directories if d != 'root'])
        tree_lines = [self.project_name + '/']
        
        for i, d in enumerate(dirs):
            parts = d.split('/')
            is_last = (i == len(dirs) - 1)
            
            for depth, part in enumerate(parts):
                prefix = '    ' * depth
                if depth == len(parts) - 1:
                    connector = '└── ' if is_last else '├── '
                else:
                    connector = '├── '
                
                line = prefix + connector + part + '/'
                if line not in tree_lines:
                    tree_lines.append(line)
        
        return tree_lines
    
    def save_mindmap(self, content: str, filename: str = "mindmap.md"):
        """Save mindmap to file."""
        output_file = self.output_dir / filename
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)
        return output_file
    
    def save_json_index(self, data: Dict, filename: str = "index.json"):
        """Save JSON index file."""
        output_file = self.output_dir / filename
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return output_file
    
    def save_keywords_rag(self, results: List[AnalysisResult], filename: str = "keywords_rag.json"):
        """Save keywords in RAG-friendly format."""
        rag_data = {
            'metadata': {
                'type': 'keywords_index',
                'total_keywords': 0,
                'files_indexed': len(results)
            },
            'keywords': {}
        }
        
        # Build inverted index: keyword -> files
        keyword_files = {}
        for result in results:
            for kw in result.keywords:
                if kw not in keyword_files:
                    keyword_files[kw] = []
                keyword_files[kw].append(result.file_path)
        
        rag_data['keywords'] = keyword_files
        rag_data['metadata']['total_keywords'] = len(keyword_files)
        
        output_file = self.output_dir / filename
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(rag_data, f, indent=2)
        
        return output_file
    
    def generate_summary_report(self, project_name: str, results: List[AnalysisResult],
                                analyzer: 'ProjectAnalyzer') -> str:
        """Generate a summary report of the analysis."""
        structure = analyzer.get_project_structure()
        
        lines = [
            "# Analysis Report",
            "",
            f"**Project:** {project_name}",
            f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary",
            "",
            f"- **Files Analyzed:** {len(results)}",
            f"- **Components:** {len(set(r.component for r in results))}",
            f"- **Unique Keywords:** {len(set(kw for r in results for kw in r.keywords))}",
            f"- **APIs Extracted:** {len([api for r in results for api in r.apis])}",
            "",
            "## Language Distribution",
            "",
        ]
        
        if 'languages' in structure:
            for lang, count in sorted(structure['languages'].items(), key=lambda x: -x[1])[:10]:
                lines.append(f"- {lang}: {count} files")
        
        lines.extend([
            "",
            "## Output Files",
            "",
            f"All analysis results are saved in: `{self.output_dir}`",
            "",
            "### Files Generated:",
            "- `mindmap.md` - Hierarchical project mind-map",
            "- `keywords.json` - All extracted keywords",
            "- `api_reference.json` - API documentation",
            "- `index.json` - Master index of all analyses",
            "- `analyses/` - Individual file analyses",
            "",
        ])
        
        return '\n'.join(lines)
