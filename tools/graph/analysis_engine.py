"""
Analysis Engine - Session management and code analysis using Kimi API.
"""

import sys
import json
from pathlib import Path
from typing import List, Dict, Callable, Optional
from dataclasses import dataclass, asdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from kimi_utils import create_session, prompt, close_session, get_default_session
from kaos.path import KaosPath
from agent_utils import print_success, print_error, print_info, print_debug, print_warning
from tools.summarize import summarize_session

from .project_analyzer import FileInfo, ProjectAnalyzer
from .prompts import (
    build_code_analysis_prompt, 
    build_batch_analysis_prompt,
    build_config_analysis_prompt,
    build_summary_prompt
)


@dataclass
class AnalysisResult:
    """Result of a code analysis."""
    file_path: str
    component: str
    analysis_text: str
    keywords: List[str]
    apis: List[Dict]
    timestamp: str = ""


class AnalysisEngine:
    """Engine for analyzing code files using Kimi API sessions."""
    
    def __init__(self, project_path: str, output_dir: str = None):
        self.project_path = Path(project_path).resolve()
        self.project_name = self.project_path.name
        
        # Set output directory to [project_path]/agent_doc by default
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = self.project_path / 'agent_doc'
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Storage for results
        self.all_results: List[AnalysisResult] = []
        self.all_keywords: set = set()
        self.all_apis: List[Dict] = []
        
        print_info(f"Analysis Engine initialized for: {self.project_path}")
        print_info(f"Output directory: {self.output_dir}")
    
    def _create_analysis_session(self, session_id: str = None) -> object:
        """Create a new independent session for analysis."""
        if session_id is None:
            import uuid
            session_id = f"analysis_{uuid.uuid4().hex[:8]}"
        
        print_debug(f"Creating session: {session_id}")
        session = create_session(
            session_id=session_id,
            work_dir=KaosPath(str(self.project_path)),
            thinking=True,  # Enable deep thinking for better analysis
            yolo=True       # Auto-approve for batch processing
        )
        return session
    
    def _read_file_content(self, file_path: str) -> str:
        """Read content of a file."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            print_error(f"Error reading {file_path}: {e}")
            return ""
    
    def _extract_keywords_from_analysis(self, analysis_text: str) -> List[str]:
        """Extract keywords from analysis text."""
        keywords = []
        
        # Look for keywords section
        lines = analysis_text.split('\n')
        in_keywords = False
        
        for line in lines:
            line = line.strip()
            if '### Keywords' in line or '## Keywords' in line:
                in_keywords = True
                continue
            
            if in_keywords:
                if line.startswith('## '):
                    break
                # Extract backtick-wrapped keywords
                import re
                found = re.findall(r'`([^`]+)`', line)
                keywords.extend(found)
                
                # Also extract comma-separated keywords
                if ',' in line and not line.startswith('```'):
                    parts = [p.strip().strip('`') for p in line.split(',')]
                    keywords.extend([p for p in parts if p and len(p) < 50])
        
        # Deduplicate and clean
        seen = set()
        clean_keywords = []
        for kw in keywords:
            kw = kw.strip()
            if kw and kw.lower() not in seen and len(kw) > 1:
                seen.add(kw.lower())
                clean_keywords.append(kw)
        
        return clean_keywords[:20]  # Limit to 20 keywords
    
    def _extract_apis_from_analysis(self, analysis_text: str) -> List[Dict]:
        """Extract API information from analysis text."""
        apis = []
        
        # Look for API reference section
        lines = analysis_text.split('\n')
        in_api_table = False
        
        for line in lines:
            line = line.strip()
            
            # Check for table separator indicating API table
            if '| Name | Type |' in line or '| API | File |' in line:
                in_api_table = True
                continue
            
            if in_api_table and line.startswith('|') and '---' not in line:
                parts = [p.strip() for p in line.split('|')[1:-1]]
                if len(parts) >= 2 and parts[0] and parts[0] not in ['Name', 'API']:
                    apis.append({
                        'name': parts[0],
                        'type': parts[1] if len(parts) > 1 else 'unknown',
                        'signature': parts[2] if len(parts) > 2 else '',
                        'description': parts[3] if len(parts) > 3 else ''
                    })
            
            if in_api_table and not line.startswith('|') and line:
                in_api_table = False
        
        return apis
    
    def analyze_file(self, file_info: FileInfo, session=None) -> Optional[AnalysisResult]:
        """
        Analyze a single code file.
        
        Args:
            file_info: FileInfo object for the file to analyze
            session: Optional existing session (creates new if None)
        
        Returns:
            AnalysisResult object or None if analysis failed
        """
        # Create new session if not provided
        created_session = False
        if session is None:
            session = self._create_analysis_session(f"file_{file_info.relative_path.replace('/', '_').replace('\\', '_')}")
            created_session = True
        
        try:
            # Read file content
            content = self._read_file_content(file_info.path)
            if not content:
                print_warning(f"Empty or unreadable file: {file_info.relative_path}")
                return None
            
            print_info(f"Analyzing: {file_info.relative_path}")
            
            # Build prompt
            prompt_text = build_code_analysis_prompt(
                file_path=file_info.relative_path,
                language=file_info.language,
                code_content=content,
                file_info={'size': file_info.size, 'lines': file_info.lines}
            )
            
            # Capture output
            analysis_output = []
            def capture_output(text):
                analysis_output.append(text)
            
            # Run analysis prompt
            prompt(prompt_text, session=session, output_function=capture_output)
            
            # Summarize session to compact context
            if created_session:
                summarize_session(session)
            
            # Combine output
            analysis_text = '\n'.join(analysis_output)
            
            # Extract structured data
            keywords = self._extract_keywords_from_analysis(analysis_text)
            apis = self._extract_apis_from_analysis(analysis_text)
            
            # Update global collections
            self.all_keywords.update(keywords)
            self.all_apis.extend(apis)
            
            result = AnalysisResult(
                file_path=file_info.relative_path,
                component=str(Path(file_info.relative_path).parent),
                analysis_text=analysis_text,
                keywords=keywords,
                apis=apis
            )
            
            self.all_results.append(result)
            print_success(f"Analysis complete: {file_info.relative_path}")
            
            return result
            
        except Exception as e:
            print_error(f"Error analyzing {file_info.relative_path}: {e}")
            return None
        finally:
            if created_session:
                close_session(session)
    
    def analyze_batch(self, files: List[FileInfo], component_name: str) -> Optional[AnalysisResult]:
        """
        Analyze a batch of related files together.
        
        Args:
            files: List of FileInfo objects to analyze together
            component_name: Name of the component/directory
        
        Returns:
            AnalysisResult object or None if analysis failed
        """
        if not files:
            return None
        
        # Create new session for this batch
        session_id = f"batch_{component_name.replace('/', '_').replace('\\', '_')}"
        session = self._create_analysis_session(session_id)
        
        try:
            print_info(f"Analyzing batch: {component_name} ({len(files)} files)")
            
            # Prepare file data
            file_data = []
            for f in files:
                content = self._read_file_content(f.path)
                if content:
                    file_data.append({
                        'path': f.relative_path,
                        'language': f.language,
                        'content': content
                    })
            
            if not file_data:
                print_warning(f"No readable content for batch: {component_name}")
                return None
            
            # Build batch prompt
            prompt_text = build_batch_analysis_prompt(component_name, file_data)
            
            # Capture output
            analysis_output = []
            def capture_output(text):
                analysis_output.append(text)
            
            # Run analysis
            prompt(prompt_text, session=session, output_function=capture_output)
            
            # Summarize session
            summarize_session(session)
            
            # Combine output
            analysis_text = '\n'.join(analysis_output)
            
            # Extract data
            keywords = self._extract_keywords_from_analysis(analysis_text)
            apis = self._extract_apis_from_analysis(analysis_text)
            
            self.all_keywords.update(keywords)
            self.all_apis.extend(apis)
            
            result = AnalysisResult(
                file_path=component_name,
                component=component_name,
                analysis_text=analysis_text,
                keywords=keywords,
                apis=apis
            )
            
            self.all_results.append(result)
            print_success(f"Batch analysis complete: {component_name}")
            
            return result
            
        except Exception as e:
            print_error(f"Error analyzing batch {component_name}: {e}")
            return None
        finally:
            close_session(session)
    
    def analyze_config_file(self, file_info: FileInfo) -> Optional[AnalysisResult]:
        """Analyze a configuration file."""
        session = self._create_analysis_session(f"config_{file_info.relative_path.replace('/', '_')}")
        
        try:
            content = self._read_file_content(file_info.path)
            if not content:
                return None
            
            print_info(f"Analyzing config: {file_info.relative_path}")
            
            prompt_text = build_config_analysis_prompt(
                file_path=file_info.relative_path,
                config_type=file_info.language,
                content=content
            )
            
            analysis_output = []
            def capture_output(text):
                analysis_output.append(text)
            
            prompt(prompt_text, session=session, output_function=capture_output)
            summarize_session(session)
            
            analysis_text = '\n'.join(analysis_output)
            keywords = self._extract_keywords_from_analysis(analysis_text)
            
            self.all_keywords.update(keywords)
            
            result = AnalysisResult(
                file_path=file_info.relative_path,
                component='config',
                analysis_text=analysis_text,
                keywords=keywords,
                apis=[]
            )
            
            self.all_results.append(result)
            print_success(f"Config analysis complete: {file_info.relative_path}")
            
            return result
            
        except Exception as e:
            print_error(f"Error analyzing config {file_info.relative_path}: {e}")
            return None
        finally:
            close_session(session)
    
    def generate_project_summary(self) -> str:
        """Generate project-wide summary using analyzed results."""
        print_info("Generating project summary...")
        
        session = self._create_analysis_session("project_summary")
        
        try:
            # Prepare component data
            components = []
            for result in self.all_results:
                components.append({
                    'name': result.component,
                    'description': result.analysis_text[:200] + '...' if len(result.analysis_text) > 200 else result.analysis_text
                })
            
            # Get analyses texts
            analyses = [r.analysis_text for r in self.all_results]
            
            # Build summary prompt
            prompt_text = build_summary_prompt(
                project_name=self.project_name,
                components=components,
                analyses=analyses
            )
            
            # Capture output
            summary_output = []
            def capture_output(text):
                summary_output.append(text)
            
            prompt(prompt_text, session=session, output_function=capture_output)
            summarize_session(session)
            
            summary_text = '\n'.join(summary_output)
            print_success("Project summary generated")
            
            return summary_text
            
        except Exception as e:
            print_error(f"Error generating summary: {e}")
            return f"# Project Summary: {self.project_name}\n\nError generating summary: {e}"
        finally:
            close_session(session)
    
    def save_results(self):
        """Save all analysis results to output directory."""
        print_info("Saving analysis results...")
        
        # Save individual analyses
        analyses_dir = self.output_dir / 'analyses'
        analyses_dir.mkdir(exist_ok=True)
        
        for result in self.all_results:
            # Create safe filename
            safe_name = result.file_path.replace('/', '_').replace('\\', '_').replace(':', '_')
            output_file = analyses_dir / f"{safe_name}.md"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(result.analysis_text)
        
        # Save keywords
        keywords_file = self.output_dir / 'keywords.json'
        with open(keywords_file, 'w', encoding='utf-8') as f:
            json.dump({
                'project': self.project_name,
                'keywords': sorted(list(self.all_keywords)),
                'count': len(self.all_keywords)
            }, f, indent=2)
        
        # Save API reference
        apis_file = self.output_dir / 'api_reference.json'
        with open(apis_file, 'w', encoding='utf-8') as f:
            json.dump({
                'project': self.project_name,
                'apis': self.all_apis
            }, f, indent=2)
        
        # Generate and save project summary
        summary = self.generate_project_summary()
        summary_file = self.output_dir / 'mindmap.md'
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        # Save master index
        index_file = self.output_dir / 'index.json'
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump({
                'project': self.project_name,
                'project_path': str(self.project_path),
                'output_dir': str(self.output_dir),
                'total_analyses': len(self.all_results),
                'total_keywords': len(self.all_keywords),
                'total_apis': len(self.all_apis),
                'analyses': [
                    {
                        'file': r.file_path,
                        'component': r.component,
                        'keywords': r.keywords
                    }
                    for r in self.all_results
                ]
            }, f, indent=2)
        
        print_success(f"Results saved to: {self.output_dir}")
        print_info(f"  - Individual analyses: {analyses_dir}")
        print_info(f"  - Mind map: {summary_file}")
        print_info(f"  - Keywords: {keywords_file}")
        print_info(f"  - API Reference: {apis_file}")
        print_info(f"  - Index: {index_file}")
