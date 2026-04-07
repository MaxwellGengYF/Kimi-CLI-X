"""GraphRAG retriever building knowledge graph from code relationships."""

import re
import ast
from typing import List, Dict, Any, Optional, Callable, Set, Tuple, Iterator
from dataclasses import dataclass, field
from collections import defaultdict, deque

from python_rag.store.base import Document
from python_rag.embeddings.base import BaseEmbeddingModel
from python_rag.embeddings.sentence_transformer import MiniLMEmbedding

from .base import BaseRetriever, RetrievedDocument


@dataclass
class CodeEntity:
    """Represents a code entity (function, class, variable, etc.)."""
    
    id: str
    name: str
    type: str  # 'function', 'class', 'method', 'variable', 'module', etc.
    content: str
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    
    def __repr__(self) -> str:
        return f"CodeEntity({self.type}:{self.name})"


@dataclass
class Relationship:
    """Represents a relationship between two code entities."""
    
    source_id: str
    target_id: str
    relation_type: str  # 'calls', 'imports', 'inherits', 'contains', etc.
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __repr__(self) -> str:
        return f"Relationship({self.source_id} -{self.relation_type}-> {self.target_id})"


class CodeParser:
    """Parser for extracting code entities and relationships from Python code."""
    
    SUPPORTED_EXTENSIONS = {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.go', '.rs'}
    
    def __init__(self):
        self.entities: List[CodeEntity] = []
        self.relationships: List[Relationship] = []
    
    def parse_file(self, file_path: str, content: str, language: Optional[str] = None) -> None:
        """
        Parse a code file to extract entities and relationships.
        
        Args:
            file_path: Path to the file
            content: File content
            language: Language override (auto-detected from extension if not provided)
        """
        if language is None:
            language = self._detect_language(file_path)
        
        if language == 'python':
            self._parse_python(content, file_path)
        else:
            # Fallback: simple regex-based parsing for other languages
            self._parse_generic(content, file_path, language)
    
    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        ext = file_path.split('.')[-1].lower() if '.' in file_path else ''
        mapping = {
            'py': 'python',
            'js': 'javascript',
            'ts': 'typescript',
            'java': 'java',
            'cpp': 'cpp',
            'c': 'c',
            'h': 'c',
            'go': 'go',
            'rs': 'rust',
        }
        return mapping.get(ext, 'generic')
    
    def _parse_python(self, content: str, file_path: str) -> None:
        """Parse Python code using AST."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            # Fallback to generic parsing on syntax error
            self._parse_generic(content, file_path, 'python')
            return
        
        module_id = f"module:{file_path}"
        module_entity = CodeEntity(
            id=module_id,
            name=file_path.split('/')[-1].split('\\')[-1],
            type='module',
            content=content,
            file_path=file_path,
            metadata={'language': 'python'}
        )
        self.entities.append(module_entity)
        
        # Track imports for relationship building
        imports = {}
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.asname or alias.name] = alias.name
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                for alias in node.names:
                    name = alias.asname or alias.name
                    imports[name] = f"{module}.{alias.name}"
            
            # Extract classes
            elif isinstance(node, ast.ClassDef):
                class_id = f"class:{file_path}:{node.name}"
                class_content = ast.get_source_segment(content, node) or ''
                
                # Get base classes (inheritance)
                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        bases.append(f"{ast.unparse(base.value)}.{base.attr}")
                
                entity = CodeEntity(
                    id=class_id,
                    name=node.name,
                    type='class',
                    content=class_content,
                    file_path=file_path,
                    line_start=node.lineno,
                    line_end=node.end_lineno if hasattr(node, 'end_lineno') else node.lineno,
                    metadata={
                        'bases': bases,
                        'language': 'python'
                    }
                )
                self.entities.append(entity)
                
                # Module contains class
                self.relationships.append(Relationship(
                    source_id=module_id,
                    target_id=class_id,
                    relation_type='contains'
                ))
                
                # Inheritance relationships
                for base in bases:
                    self.relationships.append(Relationship(
                        source_id=class_id,
                        target_id=f"base:{base}",
                        relation_type='inherits',
                        metadata={'base_name': base}
                    ))
            
            # Extract functions and methods
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Determine if it's a method (inside a class)
                parent_class = self._get_parent_class(tree, node)
                
                if parent_class:
                    func_id = f"method:{file_path}:{parent_class}:{node.name}"
                    func_type = 'method'
                else:
                    func_id = f"function:{file_path}:{node.name}"
                    func_type = 'function'
                
                func_content = ast.get_source_segment(content, node) or ''
                
                # Extract parameters
                args = [arg.arg for arg in node.args.args]
                
                entity = CodeEntity(
                    id=func_id,
                    name=node.name,
                    type=func_type,
                    content=func_content,
                    file_path=file_path,
                    line_start=node.lineno,
                    line_end=node.end_lineno if hasattr(node, 'end_lineno') else node.lineno,
                    metadata={
                        'args': args,
                        'parent_class': parent_class,
                        'language': 'python'
                    }
                )
                self.entities.append(entity)
                
                # Parent contains function
                if parent_class:
                    parent_id = f"class:{file_path}:{parent_class}"
                else:
                    parent_id = module_id
                
                self.relationships.append(Relationship(
                    source_id=parent_id,
                    target_id=func_id,
                    relation_type='contains'
                ))
                
                # Find function calls within this function
                self._extract_calls(node, func_id, imports)
    
    def _get_parent_class(self, tree: ast.AST, node: ast.AST) -> Optional[str]:
        """Get the parent class name if the node is inside a class."""
        for parent in ast.walk(tree):
            if isinstance(parent, ast.ClassDef):
                for child in ast.walk(parent):
                    if child is node:
                        return parent.name
        return None
    
    def _extract_calls(self, node: ast.AST, func_id: str, imports: Dict[str, str]) -> None:
        """Extract function calls from a node."""
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    called_name = child.func.id
                    # Resolve import if possible
                    if called_name in imports:
                        called_name = imports[called_name]
                    
                    self.relationships.append(Relationship(
                        source_id=func_id,
                        target_id=f"call:{called_name}",
                        relation_type='calls',
                        metadata={'called_function': called_name}
                    ))
                elif isinstance(child.func, ast.Attribute):
                    called_name = child.func.attr
                    if isinstance(child.func.value, ast.Name):
                        obj_name = child.func.value.id
                        if obj_name in imports:
                            called_name = f"{imports[obj_name]}.{called_name}"
                    
                    self.relationships.append(Relationship(
                        source_id=func_id,
                        target_id=f"call:{called_name}",
                        relation_type='calls',
                        metadata={'called_function': called_name}
                    ))
    
    def _parse_generic(self, content: str, file_path: str, language: str) -> None:
        """Generic regex-based parsing for non-Python languages."""
        module_id = f"module:{file_path}"
        module_entity = CodeEntity(
            id=module_id,
            name=file_path.split('/')[-1].split('\\')[-1],
            type='module',
            content=content,
            file_path=file_path,
            metadata={'language': language}
        )
        self.entities.append(module_entity)
        
        # Function pattern (simplified)
        func_pattern = r'(?:function|def|fn|func)\s+(\w+)\s*\('
        for match in re.finditer(func_pattern, content, re.MULTILINE):
            func_name = match.group(1)
            func_id = f"function:{file_path}:{func_name}"
            
            # Extract surrounding context
            start = max(0, match.start() - 200)
            end = min(len(content), match.end() + 800)
            func_content = content[start:end]
            
            entity = CodeEntity(
                id=func_id,
                name=func_name,
                type='function',
                content=func_content,
                file_path=file_path,
                metadata={'language': language}
            )
            self.entities.append(entity)
            
            self.relationships.append(Relationship(
                source_id=module_id,
                target_id=func_id,
                relation_type='contains'
            ))
        
        # Class pattern (simplified)
        class_pattern = r'(?:class|struct|interface)\s+(\w+)'
        for match in re.finditer(class_pattern, content, re.MULTILINE):
            class_name = match.group(1)
            class_id = f"class:{file_path}:{class_name}"
            
            start = max(0, match.start() - 100)
            end = min(len(content), match.end() + 1000)
            class_content = content[start:end]
            
            entity = CodeEntity(
                id=class_id,
                name=class_name,
                type='class',
                content=class_content,
                file_path=file_path,
                metadata={'language': language}
            )
            self.entities.append(entity)
            
            self.relationships.append(Relationship(
                source_id=module_id,
                target_id=class_id,
                relation_type='contains'
            ))


class KnowledgeGraph:
    """Simple knowledge graph for code entities and relationships."""
    
    def __init__(self):
        self.entities: Dict[str, CodeEntity] = {}
        self.outgoing: Dict[str, List[Relationship]] = defaultdict(list)
        self.incoming: Dict[str, List[Relationship]] = defaultdict(list)
        self.entity_index: Dict[str, Set[str]] = defaultdict(set)  # type -> entity_ids
    
    def add_entity(self, entity: CodeEntity) -> None:
        """Add an entity to the graph."""
        self.entities[entity.id] = entity
        self.entity_index[entity.type].add(entity.id)
    
    def add_relationship(self, rel: Relationship) -> None:
        """Add a relationship to the graph."""
        self.outgoing[rel.source_id].append(rel)
        self.incoming[rel.target_id].append(rel)
    
    def get_neighbors(
        self,
        entity_id: str,
        relation_type: Optional[str] = None,
        direction: str = 'both'
    ) -> List[Tuple[CodeEntity, str]]:
        """
        Get neighboring entities.
        
        Args:
            entity_id: Starting entity ID
            relation_type: Filter by relationship type
            direction: 'outgoing', 'incoming', or 'both'
            
        Returns:
            List of (entity, relationship_type) tuples
        """
        neighbors = []
        
        if direction in ('outgoing', 'both'):
            for rel in self.outgoing.get(entity_id, []):
                if relation_type is None or rel.relation_type == relation_type:
                    if rel.target_id in self.entities:
                        neighbors.append((self.entities[rel.target_id], rel.relation_type))
        
        if direction in ('incoming', 'both'):
            for rel in self.incoming.get(entity_id, []):
                if relation_type is None or rel.relation_type == relation_type:
                    if rel.source_id in self.entities:
                        neighbors.append((self.entities[rel.source_id], f"{rel.relation_type}_reverse"))
        
        return neighbors
    
    def traverse(
        self,
        start_id: str,
        max_depth: int = 2,
        relation_types: Optional[List[str]] = None
    ) -> Dict[str, int]:
        """
        BFS traversal from a starting entity.
        
        Args:
            start_id: Starting entity ID
            max_depth: Maximum traversal depth
            relation_types: Allowed relationship types
            
        Returns:
            Dictionary mapping entity_id -> depth
        """
        visited = {start_id: 0}
        queue = deque([(start_id, 0)])
        
        while queue:
            current_id, depth = queue.popleft()
            
            if depth >= max_depth:
                continue
            
            # Get neighbors
            neighbors = self.get_neighbors(current_id, direction='both')
            
            for entity, rel_type in neighbors:
                if relation_types and rel_type not in relation_types:
                    continue
                
                if entity.id not in visited:
                    visited[entity.id] = depth + 1
                    queue.append((entity.id, depth + 1))
        
        return visited
    
    def search_by_name(self, name: str) -> List[CodeEntity]:
        """Search entities by name (exact or partial match)."""
        name_lower = name.lower()
        results = []
        for entity in self.entities.values():
            if name_lower in entity.name.lower():
                results.append(entity)
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        return {
            'entity_count': len(self.entities),
            'relationship_count': sum(len(rels) for rels in self.outgoing.values()),
            'entity_types': {t: len(ids) for t, ids in self.entity_index.items()}
        }


class GraphRAGRetriever(BaseRetriever):
    """
    GraphRAG retriever combining knowledge graph traversal with vector similarity.
    
    Builds a knowledge graph from code relationships and uses both:
    1. Graph traversal to find related code entities
    2. Vector similarity for semantic matching
    """
    
    def __init__(
        self,
        embedding_model: Optional[BaseEmbeddingModel] = None,
        top_k: int = 5,
        score_threshold: Optional[float] = None,
        filter_fn: Optional[Callable[[Document], bool]] = None,
        max_graph_depth: int = 2,
        vector_weight: float = 0.6,
        graph_weight: float = 0.4,
        relation_types: Optional[List[str]] = None
    ):
        """
        Initialize GraphRAG retriever.
        
        Args:
            embedding_model: Model for semantic search
            top_k: Maximum documents to retrieve
            score_threshold: Minimum fusion score
            filter_fn: Optional document filter
            max_graph_depth: Max depth for graph traversal
            vector_weight: Weight for vector similarity in fusion
            graph_weight: Weight for graph proximity in fusion
            relation_types: Relationship types to follow in graph
        """
        super().__init__(top_k=top_k, score_threshold=score_threshold, filter_fn=filter_fn)
        
        self.embedding_model = embedding_model or MiniLMEmbedding()
        self.max_graph_depth = max_graph_depth
        self.vector_weight = vector_weight
        self.graph_weight = graph_weight
        self.relation_types = relation_types
        
        # Components
        self.parser = CodeParser()
        self.graph = KnowledgeGraph()
        
        # Entity embeddings cache
        self._embeddings_computed = False
    
    def add_code_files(
        self,
        files: List[Tuple[str, str]],
        language: Optional[str] = None
    ) -> None:
        """
        Add code files to the knowledge graph.
        
        Args:
            files: List of (file_path, content) tuples
            language: Language override
        """
        for file_path, content in files:
            self.parser.parse_file(file_path, content, language)
        
        # Build graph
        for entity in self.parser.entities:
            self.graph.add_entity(entity)
        
        for rel in self.parser.relationships:
            self.graph.add_relationship(rel)
        
        self._embeddings_computed = False
    
    def add_code_documents(self, documents: List[Document]) -> None:
        """
        Add documents containing code to the knowledge graph.
        
        Args:
            documents: Documents with code content
        """
        files = []
        for doc in documents:
            file_path = doc.metadata.get('file_path', doc.id)
            files.append((file_path, doc.content))
        
        self.add_code_files(files)
    
    def _compute_embeddings(self) -> None:
        """Compute embeddings for all entities."""
        if self._embeddings_computed:
            return
        
        # Batch compute embeddings
        contents = []
        entities = []
        
        for entity in self.graph.entities.values():
            if entity.embedding is None:
                contents.append(f"{entity.type}: {entity.name}\n{entity.content[:500]}")
                entities.append(entity)
        
        if contents:
            embeddings = self.embedding_model.embed_documents(contents)
            for entity, emb in zip(entities, embeddings):
                entity.embedding = emb
        
        self._embeddings_computed = True
    
    def retrieve(self, query: str) -> List[RetrievedDocument]:
        """
        Retrieve relevant code entities using graph + vector search.
        
        Args:
            query: Search query (can be natural language or code)
            
        Returns:
            List of retrieved code entities
        """
        if not self.graph.entities:
            return []
        
        # Ensure embeddings are computed
        self._compute_embeddings()
        
        # Encode query
        query_embedding = self.embedding_model.embed_query(query)
        
        # Get initial candidates via vector search
        vector_candidates = self._vector_search(query_embedding, top_k=self.top_k * 2)
        
        # Expand candidates via graph traversal
        graph_candidates = self._graph_expansion(vector_candidates)
        
        # Fuse scores
        fused_results = self._fuse_scores(
            vector_candidates,
            graph_candidates,
            query_embedding
        )
        
        # Apply threshold and filter
        if self.score_threshold is not None:
            fused_results = [r for r in fused_results if r.score >= self.score_threshold]
        
        if self.filter_fn:
            fused_results = [r for r in fused_results if self.filter_fn(r.document)]
        
        return fused_results[:self.top_k]
    
    def _vector_search(
        self,
        query_embedding: List[float],
        top_k: int
    ) -> Dict[str, Tuple[CodeEntity, float]]:
        """
        Find entities by vector similarity.
        
        Args:
            query_embedding: Query vector
            top_k: Number of top results
            
        Returns:
            Dict mapping entity_id -> (entity, score)
        """
        import numpy as np
        
        scores = []
        entities_with_emb = []
        
        for entity in self.graph.entities.values():
            if entity.embedding:
                entities_with_emb.append(entity)
                # Cosine similarity
                sim = np.dot(query_embedding, entity.embedding)
                scores.append(sim)
        
        if not scores:
            return {}
        
        # Get top-k
        top_indices = np.argsort(scores)[-top_k:][::-1]
        
        results = {}
        for idx in top_indices:
            entity = entities_with_emb[idx]
            results[entity.id] = (entity, float(scores[idx]))
        
        return results
    
    def _graph_expansion(
        self,
        seed_candidates: Dict[str, Tuple[CodeEntity, float]]
    ) -> Dict[str, int]:
        """
        Expand candidates via graph traversal.
        
        Args:
            seed_candidates: Initial candidates from vector search
            
        Returns:
            Dict mapping entity_id -> graph distance
        """
        graph_scores = {}
        
        for entity_id in seed_candidates:
            # Traverse graph from this entity
            distances = self.graph.traverse(
                entity_id,
                max_depth=self.max_graph_depth,
                relation_types=self.relation_types
            )
            
            for neighbor_id, distance in distances.items():
                # Closer = higher score (inverse distance)
                score = self.max_graph_depth - distance + 1
                
                if neighbor_id in graph_scores:
                    graph_scores[neighbor_id] = max(graph_scores[neighbor_id], score)
                else:
                    graph_scores[neighbor_id] = score
        
        return graph_scores
    
    def _fuse_scores(
        self,
        vector_candidates: Dict[str, Tuple[CodeEntity, float]],
        graph_candidates: Dict[str, int],
        query_embedding: List[float]
    ) -> List[RetrievedDocument]:
        """
        Fuse vector and graph scores.
        
        Args:
            vector_candidates: Vector search results
            graph_candidates: Graph distance results
            query_embedding: Query embedding for computing missing scores
            
        Returns:
            Fused and ranked results
        """
        import numpy as np
        
        # Collect all unique entity IDs
        all_ids = set(vector_candidates.keys()) | set(graph_candidates.keys())
        
        # Normalize scores
        max_vector_score = max((s for _, s in vector_candidates.values()), default=1.0)
        max_graph_score = max(graph_candidates.values(), default=1.0)
        
        fused_scores = []
        
        for entity_id in all_ids:
            entity = self.graph.entities.get(entity_id)
            if not entity:
                continue
            
            # Vector score (normalized)
            if entity_id in vector_candidates:
                v_score = vector_candidates[entity_id][1] / max_vector_score
            else:
                # Compute on-the-fly for graph-only candidates
                if entity.embedding:
                    v_score = float(np.dot(query_embedding, entity.embedding))
                    v_score = max(0, v_score) / max_vector_score if max_vector_score > 0 else 0
                else:
                    v_score = 0.0
            
            # Graph score (normalized)
            if entity_id in graph_candidates:
                g_score = graph_candidates[entity_id] / max_graph_score
            else:
                g_score = 0.0
            
            # Weighted fusion
            fused = self.vector_weight * v_score + self.graph_weight * g_score
            
            fused_scores.append((entity, fused))
        
        # Sort by fused score
        fused_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Convert to RetrievedDocument
        results = []
        for rank, (entity, score) in enumerate(fused_scores, start=1):
            # Create a Document wrapper for the entity
            doc = Document(
                id=entity.id,
                content=entity.content,
                metadata={
                    'name': entity.name,
                    'type': entity.type,
                    'file_path': entity.file_path,
                    'line_start': entity.line_start,
                    'line_end': entity.line_end,
                    **entity.metadata
                }
            )
            
            retrieved = RetrievedDocument(
                document=doc,
                score=score,
                rank=rank
            )
            results.append(retrieved)
        
        return results
    
    def find_related(self, entity_name: str, max_depth: int = 2) -> List[RetrievedDocument]:
        """
        Find code entities related to a given entity name.
        
        Args:
            entity_name: Name of the entity to find
            max_depth: Maximum traversal depth
            
        Returns:
            List of related entities
        """
        # Search for entity by name
        matches = self.graph.search_by_name(entity_name)
        
        if not matches:
            return []
        
        results = []
        for start_entity in matches[:3]:  # Consider top 3 matches
            distances = self.graph.traverse(
                start_entity.id,
                max_depth=max_depth,
                relation_types=self.relation_types
            )
            
            for entity_id, distance in distances.items():
                if entity_id == start_entity.id:
                    continue
                
                entity = self.graph.entities[entity_id]
                doc = Document(
                    id=entity.id,
                    content=entity.content,
                    metadata={
                        'name': entity.name,
                        'type': entity.type,
                        'distance_from': start_entity.name,
                        'graph_distance': distance
                    }
                )
                
                retrieved = RetrievedDocument(
                    document=doc,
                    score=1.0 / (distance + 1),
                    rank=distance
                )
                results.append(retrieved)
        
        # Sort by score and deduplicate
        results.sort(key=lambda r: (-r.score, r.document.id))
        seen_ids = set()
        unique_results = []
        for r in results:
            if r.document.id not in seen_ids:
                seen_ids.add(r.document.id)
                unique_results.append(r)
        
        # Re-rank
        for i, r in enumerate(unique_results, start=1):
            r.rank = i
        
        return unique_results[:self.top_k]
    
    def get_graph_stats(self) -> Dict[str, Any]:
        """Get knowledge graph statistics."""
        return self.graph.get_stats()
    
    def is_available(self) -> bool:
        """Check if knowledge graph has entities."""
        return len(self.graph.entities) > 0
