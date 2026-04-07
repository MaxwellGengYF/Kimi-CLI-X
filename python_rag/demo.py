#!/usr/bin/env python3
r"""Demo of analyzing my_tools\common.py using RAGOrchestrator."""

import os
import ast
from pathlib import Path

from orchestrator import RAGOrchestrator, QueryType, RetrievalConfig
from retrievers.bm25 import BM25Retriever
from store.base import Document


def extract_code_elements(file_path: str) -> list[Document]:
    """Extract functions, classes, and key code elements from a Python file."""
    documents = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        source = f.read()
    
    # Add the full file as a document
    documents.append(Document(
        id="full_file",
        content=source,
        metadata={"type": "full_file", "path": file_path}
    ))
    
    try:
        tree = ast.parse(source)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Extract function
                func_source = ast.get_source_segment(source, node)
                doc = Document(
                    id=f"func_{node.name}",
                    content=func_source,
                    metadata={
                        "type": "function",
                        "name": node.name,
                        "line": node.lineno,
                        "path": file_path
                    }
                )
                documents.append(doc)
                
            elif isinstance(node, ast.ClassDef):
                # Extract class
                class_source = ast.get_source_segment(source, node)
                doc = Document(
                    id=f"class_{node.name}",
                    content=class_source,
                    metadata={
                        "type": "class",
                        "name": node.name,
                        "line": node.lineno,
                        "path": file_path
                    }
                )
                documents.append(doc)
                
            elif isinstance(node, ast.Assign):
                # Extract global variables/constants
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assign_source = ast.get_source_segment(source, node)
                        doc = Document(
                            id=f"var_{target.id}",
                            content=assign_source,
                            metadata={
                                "type": "variable",
                                "name": target.id,
                                "line": node.lineno,
                                "path": file_path
                            }
                        )
                        documents.append(doc)
                        
    except SyntaxError as e:
        print(f"  Warning: Could not parse file: {e}")
    
    return documents


def main():
    target_file = ''
    import sys
    if len(sys.argv) > 1:
        target_file = sys.argv[1]
    if not target_file:
        print('Input file')
        exit(1)
    print("=" * 70)
    print("RAG Orchestrator - Code Analysis Demo")
    print(f"Analyzing: {target_file}")
    print("=" * 70)
    
    # Check if file exists
    if not os.path.exists(target_file):
        print(f"\nError: File '{target_file}' not found!")
        return
    
    # Create orchestrator
    print("\n[1] Creating RAG Orchestrator...")
    orchestrator = RAGOrchestrator(
        default_query_type=QueryType.HYBRID,
        fusion_method="rrf",
        enable_query_classification=True,
        enable_cache=True
    )
    
    # Add BM25 retriever for keyword-based search
    print("\n[2] Adding retrievers...")
    bm25 = BM25Retriever(top_k=5)
    orchestrator.add_retriever(
        "bm25_code",
        bm25,
        query_types=[QueryType.KEYWORD, QueryType.HYBRID],
        weight=0.6,
        priority=5
    )
    print("  Added BM25 retriever for code search")
    
    # Add semantic retriever (mock)
    class MockSemanticRetriever:
        def __init__(self, name):
            self.name = name
            self.docs = []
        
        def add_documents(self, docs):
            self.docs.extend(docs)
        
        def retrieve(self, query):
            query_words = set(query.lower().split())
            results = []
            for doc in self.docs:
                doc_words = set(doc.content.lower().split())
                overlap = len(query_words & doc_words)
                if overlap > 0:
                    from .retrievers.base import RetrievedDocument
                    results.append(RetrievedDocument(
                        document=doc,
                        score=overlap / len(query_words) if query_words else 0,
                        rank=0
                    ))
            results.sort(key=lambda x: x.score, reverse=True)
            for i, r in enumerate(results, start=1):
                r.rank = i
            return results[:5]
        
        def is_available(self):
            return len(self.docs) > 0
    
    semantic = MockSemanticRetriever("semantic")
    orchestrator.add_retriever(
        "semantic_code",
        semantic,
        query_types=[QueryType.SEMANTIC, QueryType.HYBRID],
        weight=0.8,
        priority=10
    )
    print("  Added Semantic retriever")
    
    # Extract and index code elements
    print(f"\n[3] Extracting code elements from '{target_file}'...")
    documents = extract_code_elements(target_file)
    
    orchestrator.add_documents(documents)
    print(f"  Indexed {len(documents)} code elements")
    
    # Display what was indexed
    print("\n[4] Indexed Elements:")
    for doc in documents:
        doc_type = doc.metadata.get("type", "unknown")
        name = doc.metadata.get("name", "N/A")
        line = doc.metadata.get("line", "N/A")
        print(f"  - [{doc_type}] {name} (line {line})")
    
    # Test queries
    print("\n[5] Code Retrieval Tests:")
    
    test_queries = [
        "export to file function",
        "token estimation",
        "temporary file handling",
        "OUTPUT_TOKEN_LIMIT",
        "maybe_export_output",
    ]
    
    for query in test_queries:
        print(f"\n  Query: '{query}'")
        result = orchestrator.retrieve(query, top_k=3)
        
        print(f"    Detected Type: {result.query_type.value}")
        print(f"    Latency: {result.total_time_ms:.2f}ms")
        
        if result.documents:
            print(f"    Results:")
            for doc in result.documents[:2]:
                doc_type = doc.document.metadata.get("type", "unknown")
                name = doc.document.metadata.get("name", "N/A")
                content_preview = doc.document.content[:70].replace('\n', ' ')
                if len(doc.document.content) > 70:
                    content_preview += "..."
                print(f"      [{doc.score:.3f}] [{doc_type}] {name}")
                print(f"                {content_preview}")
        else:
            print("    No results found")
    
    # Test batch retrieval
    print("\n[6] Batch Retrieval Test:")
    batch_queries = [
        "export function",
        "estimate tokens",
        "temp folder path",
    ]
    results = orchestrator.batch_retrieve(batch_queries, top_k=2)
    
    for query, result in zip(batch_queries, results):
        doc_names = [d.document.metadata.get("name", "N/A") for d in result.documents[:2]]
        print(f"  '{query}': {', '.join(doc_names) if doc_names else 'No results'}")
    
    # Test cache
    print("\n[7] Cache Performance Test:")
    query = "export to temp file"
    
    # First retrieval (cache miss)
    result1 = orchestrator.retrieve(query, use_cache=True)
    print(f"  First query: {result1.total_time_ms:.2f}ms")
    
    # Second retrieval (cache hit)
    result2 = orchestrator.retrieve(query, use_cache=True)
    print(f"  Second query (cached): {result2.total_time_ms:.2f}ms")
    
    # Show final statistics
    print("\n[8] Final Statistics:")
    stats = orchestrator.get_stats()
    print(f"   Total queries: {stats['total_queries']}")
    print(f"   Cache hits: {stats['cache_hits']}")
    print(f"   Avg latency: {stats['avg_latency_ms']:.2f}ms")
    print(f"   Retriever usage: {dict(stats['retriever_usage'])}")
    
    # Specific function lookup
    print("\n[9] Specific Function Analysis:")
    query = "_maybe_export_output"
    result = orchestrator.retrieve(query, top_k=1, query_type=QueryType.KEYWORD)
    if result.documents:
        doc = result.documents[0].document
        print(f"  Function: {doc.metadata.get('name', 'N/A')}")
        print(f"  Line: {doc.metadata.get('line', 'N/A')}")
        print(f"  Content:")
        for line in doc.content.split('\n'):
            print(f"    {line}")
    
    print("\n" + "=" * 70)
    print("Demo complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
