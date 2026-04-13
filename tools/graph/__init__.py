"""
Project Analysis & Mind-Map Generation System

A system to analyze code projects and generate comprehensive documentation/mind-maps.
"""
__version__ = "1.0.0"
__author__ = "Code Agent"

from .project_analyzer import ProjectAnalyzer
from .analysis_engine import AnalysisEngine
from .output_manager import OutputManager

__all__ = ['ProjectAnalyzer', 'AnalysisEngine', 'OutputManager']

    
if __name__ == '__main__':
    if not args:
        args: str = ''
    args = args.split(' ')
    from .main import main as _main
    _main(args)
