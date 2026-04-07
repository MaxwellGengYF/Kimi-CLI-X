#!/usr/bin/env python3
"""Example usage of the RAG system with skill files."""

from pathlib import Path
from rag.pipeline import RAGPipeline


def main():
    """Run a demo query against the skill files."""
    skills_dir = Path(".agents/skills")
    
    if not skills_dir.exists():
        print("Skill files directory not found. Make sure you're running from the project root.")
        return
    
    print("Initializing RAG pipeline...")
    pipeline = RAGPipeline(
        collection_name="skills_demo",
        persist_directory="./chroma_skills_db"
    )
    
    print(f"Indexing documents from {skills_dir}...")
    count = pipeline.index_directory(skills_dir)
    print(f"Indexed {count} document chunks")
    
    stats = pipeline.get_stats()
    print(f"\nCollection stats: {stats}")
    
    # Demo queries
    queries = [
        "How do I build with CMake?",
        "What is XMake used for?",
        "How do I write a GPU kernel?",
        "Explain the LC_DSL syntax",
    ]
    
    print("\n" + "=" * 60)
    for query in queries:
        print(f"\nQuery: {query}")
        results = pipeline.query(query, top_k=2)
        
        for i, result in enumerate(results, 1):
            print(f"  Result {i} (distance: {result.distance:.3f}):")
            content_preview = result.content[:200].replace('\n', ' ')
            print(f"    {content_preview}...")
        print("-" * 60)


if __name__ == "__main__":
    main()
