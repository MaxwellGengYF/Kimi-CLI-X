"""AST-Aware retriever parsing code AST for semantic code retrieval."""

import ast
import re
import hashlib
from typing import List, Dict, Any, Optional, Callable, Set, Tuple, Union
from dataclasses import dataclass, field
from collections import defaultdict

from python_rag.store.base import Document
from python_rag.store.chroma_store import ChromaDocumentStore
from python_rag.embeddings.base import BaseEmbeddingModel
from python_rag.embeddings.sentence_transformer import MiniLMEmbedding

from .base import BaseRetriever, RetrievedDocument


@dataclass
class ASTNode:
    """Represents a node in the code AST with semantic information."""
    
    id: str
    node_type: str  # 'FunctionDef', 'ClassDef', 'Import', 'Call', etc.
    name: str
    content: str  # Source code segment
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    semantic_signature: str = ""  # Normalized representation for comparison
    embedding: Optional[List[float]] = None
    
    def __repr__(self) -> str:
        return f"ASTNode({self.node_type}:{self.name})"


@dataclass  
class SemanticPattern:
    """Represents a semantic pattern extracted from code."""
    
    pattern_type: str  # 'control_flow', 'data_flow', 'api_usage', 'structure'
    description: str
    entities: List[str]  # Related entity names
    confidence: float = 1.0


class ASTAnalyzer:
    """Analyzes Python AST to extract semantic information and patterns."""
    
    def __init__(self):
        self.nodes: Dict[str, ASTNode] = {}
        self.patterns: List[SemanticPattern] = []
        self.node_counter = 0
    
    def generate_id(self, prefix: str = "node") -> str:
        """Generate unique node ID."""
        self.node_counter += 1
        return f"{prefix}_{self.node_counter}_{hashlib.md5(str(self.node_counter).encode()).hexdigest()[:8]}"
    
    def analyze_code(self, code: str, file_path: str = "<unknown>") -> List[ASTNode]:
        """
        Analyze code and extract AST nodes with semantic information.
        
        Args:
            code: Source code to analyze
            file_path: Path to the file
            
        Returns:
            List of AST nodes
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []
        
        nodes = []
        file_node_id = self.generate_id("file")
        file_node = ASTNode(
            id=file_node_id,
            node_type="Module",
            name=file_path.split('/')[-1].split('\\')[-1],
            content=code[:1000],  # First 1000 chars as summary
            metadata={'file_path': file_path, 'language': 'python'}
        )
        self.nodes[file_node_id] = file_node
        nodes.append(file_node)
        
        # Walk the AST
        for node in ast.walk(tree):
            ast_node = self._process_node(node, file_node_id, code)
            if ast_node:
                self.nodes[ast_node.id] = ast_node
                nodes.append(ast_node)
                file_node.children_ids.append(ast_node.id)
        
        # Extract semantic patterns
        self._extract_patterns(tree, code)
        
        return nodes
    
    def _process_node(
        self,
        node: ast.AST,
        parent_id: str,
        source: str
    ) -> Optional[ASTNode]:
        """Process an AST node into an ASTNode."""
        
        if isinstance(node, ast.FunctionDef):
            return self._process_function(node, parent_id, source)
        elif isinstance(node, ast.ClassDef):
            return self._process_class(node, parent_id, source)
        elif isinstance(node, ast.AsyncFunctionDef):
            return self._process_async_function(node, parent_id, source)
        elif isinstance(node, ast.Import):
            return self._process_import(node, parent_id, source)
        elif isinstance(node, ast.ImportFrom):
            return self._process_import_from(node, parent_id, source)
        elif isinstance(node, ast.Call):
            return self._process_call(node, parent_id, source)
        
        return None
    
    def _process_function(
        self,
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        parent_id: str,
        source: str
    ) -> ASTNode:
        """Process function definition."""
        node_id = self.generate_id("func")
        
        # Extract function source
        func_source = ast.get_source_segment(source, node) or ""
        
        # Analyze parameters
        args_info = self._analyze_arguments(node.args)
        
        # Analyze return type
        return_annotation = ast.unparse(node.returns) if node.returns else None
        
        # Check for decorators
        decorators = [ast.unparse(d) for d in node.decorator_list]
        
        # Check docstring
        docstring = ast.get_docstring(node)
        
        # Build semantic signature
        signature_parts = [
            f"def {node.name}",
            f"args:{','.join(args_info['arg_names'])}",
        ]
        if return_annotation:
            signature_parts.append(f"->{return_annotation}")
        if decorators:
            signature_parts.append(f"decorators:{','.join(decorators)}")
        
        semantic_signature = "|".join(signature_parts)
        
        # Extract control flow patterns
        control_flow = self._extract_control_flow(node)
        
        # Extract API calls within function
        api_calls = self._extract_api_calls(node)
        
        metadata = {
            'args': args_info,
            'return_type': return_annotation,
            'decorators': decorators,
            'docstring': docstring,
            'control_flow': control_flow,
            'api_calls': api_calls,
            'line_start': node.lineno,
            'line_end': getattr(node, 'end_lineno', node.lineno),
        }
        
        return ASTNode(
            id=node_id,
            node_type="FunctionDef",
            name=node.name,
            content=func_source,
            parent_id=parent_id,
            metadata=metadata,
            semantic_signature=semantic_signature
        )
    
    def _process_async_function(
        self,
        node: ast.AsyncFunctionDef,
        parent_id: str,
        source: str
    ) -> ASTNode:
        """Process async function definition."""
        func_node = self._process_function(node, parent_id, source)
        func_node.node_type = "AsyncFunctionDef"
        func_node.semantic_signature = f"async|{func_node.semantic_signature}"
        func_node.metadata['is_async'] = True
        return func_node
    
    def _process_class(
        self,
        node: ast.ClassDef,
        parent_id: str,
        source: str
    ) -> ASTNode:
        """Process class definition."""
        node_id = self.generate_id("class")
        
        class_source = ast.get_source_segment(source, node) or ""
        
        # Analyze bases (inheritance)
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(f"{ast.unparse(base.value)}.{base.attr}")
            else:
                bases.append(ast.unparse(base))
        
        # Analyze methods
        methods = []
        class_vars = []
        
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(item.name)
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        class_vars.append(target.id)
        
        # Check docstring
        docstring = ast.get_docstring(node)
        
        # Build semantic signature
        semantic_signature = f"class {node.name}"
        if bases:
            semantic_signature += f"(bases:{','.join(bases)})"
        semantic_signature += f"|methods:{','.join(methods)}"
        
        metadata = {
            'bases': bases,
            'methods': methods,
            'class_vars': class_vars,
            'docstring': docstring,
            'line_start': node.lineno,
            'line_end': getattr(node, 'end_lineno', node.lineno),
        }
        
        return ASTNode(
            id=node_id,
            node_type="ClassDef",
            name=node.name,
            content=class_source,
            parent_id=parent_id,
            metadata=metadata,
            semantic_signature=semantic_signature
        )
    
    def _process_import(
        self,
        node: ast.Import,
        parent_id: str,
        source: str
    ) -> Optional[ASTNode]:
        """Process import statement."""
        if not node.names:
            return None
        
        node_id = self.generate_id("import")
        import_source = ast.get_source_segment(source, node) or ""
        
        modules = [alias.name for alias in node.names]
        
        return ASTNode(
            id=node_id,
            node_type="Import",
            name=modules[0],
            content=import_source,
            parent_id=parent_id,
            metadata={'modules': modules, 'is_import': True}
        )
    
    def _process_import_from(
        self,
        node: ast.ImportFrom,
        parent_id: str,
        source: str
    ) -> Optional[ASTNode]:
        """Process from-import statement."""
        if not node.names:
            return None
        
        node_id = self.generate_id("importfrom")
        import_source = ast.get_source_segment(source, node) or ""
        
        module = node.module or ""
        names = [alias.name for alias in node.names]
        
        return ASTNode(
            id=node_id,
            node_type="ImportFrom",
            name=module,
            content=import_source,
            parent_id=parent_id,
            metadata={
                'module': module,
                'names': names,
                'is_import': True
            }
        )
    
    def _process_call(
        self,
        node: ast.Call,
        parent_id: str,
        source: str
    ) -> Optional[ASTNode]:
        """Process function call."""
        node_id = self.generate_id("call")
        call_source = ast.get_source_segment(source, node) or ""
        
        # Get function name
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        else:
            func_name = ast.unparse(node.func)
        
        # Analyze arguments
        arg_types = []
        for arg in node.args:
            arg_types.append(type(arg).__name__)
        
        return ASTNode(
            id=node_id,
            node_type="Call",
            name=func_name,
            content=call_source,
            parent_id=parent_id,
            metadata={
                'func_name': func_name,
                'arg_types': arg_types,
                'arg_count': len(node.args) + len(node.keywords)
            }
        )
    
    def _analyze_arguments(self, args: ast.arguments) -> Dict[str, Any]:
        """Analyze function arguments."""
        arg_names = []
        arg_with_defaults = []
        has_varargs = args.vararg is not None
        has_kwargs = args.kwarg is not None
        
        # Regular args
        defaults_start = len(args.args) - len(args.defaults)
        for i, arg in enumerate(args.args):
            arg_names.append(arg.arg)
            has_default = i >= defaults_start
            arg_with_defaults.append({
                'name': arg.arg,
                'annotation': ast.unparse(arg.annotation) if arg.annotation else None,
                'has_default': has_default
            })
        
        # Keyword-only args
        kw_only_args = [arg.arg for arg in args.kwonlyargs]
        
        return {
            'arg_names': arg_names,
            'args_with_defaults': arg_with_defaults,
            'kw_only_args': kw_only_args,
            'has_varargs': has_varargs,
            'has_kwargs': has_kwargs,
        }
    
    def _extract_control_flow(self, node: ast.AST) -> List[Dict[str, Any]]:
        """Extract control flow patterns from a node."""
        patterns = []
        
        for child in ast.walk(node):
            if isinstance(child, ast.If):
                patterns.append({'type': 'if', 'has_else': len(child.orelse) > 0})
            elif isinstance(child, ast.For):
                patterns.append({'type': 'for', 'has_else': len(child.orelse) > 0})
            elif isinstance(child, ast.While):
                patterns.append({'type': 'while', 'has_else': len(child.orelse) > 0})
            elif isinstance(child, ast.Try):
                patterns.append({
                    'type': 'try',
                    'except_count': len(child.handlers),
                    'has_else': len(child.orelse) > 0,
                    'has_finally': len(child.finalbody) > 0
                })
            elif isinstance(child, ast.With):
                patterns.append({'type': 'with', 'item_count': len(child.items)})
            elif isinstance(child, (ast.Return, ast.Yield, ast.YieldFrom)):
                patterns.append({'type': type(child).__name__.lower()})
        
        return patterns
    
    def _extract_api_calls(self, node: ast.AST) -> List[str]:
        """Extract API calls (method calls on objects)."""
        calls = []
        
        for child in ast.walk(node):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                obj_name = ""
                if isinstance(child.func.value, ast.Name):
                    obj_name = child.func.value.id
                elif isinstance(child.func.value, ast.Attribute):
                    obj_name = ast.unparse(child.func.value)
                
                if obj_name:
                    calls.append(f"{obj_name}.{child.func.attr}")
        
        return calls
    
    def _extract_patterns(self, tree: ast.AST, source: str) -> None:
        """Extract high-level semantic patterns from the code."""
        
        # Pattern: Error Handling
        try_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.Try))
        if try_count > 0:
            self.patterns.append(SemanticPattern(
                pattern_type='control_flow',
                description=f'error_handling_with_{try_count}_try_blocks',
                entities=[],
                confidence=0.9
            ))
        
        # Pattern: Async/Await usage
        async_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef))
        if async_count > 0:
            self.patterns.append(SemanticPattern(
                pattern_type='control_flow',
                description=f'async_programming_with_{async_count}_async_functions',
                entities=[],
                confidence=0.95
            ))
        
        # Pattern: Decorator usage
        decorator_count = sum(
            len(node.decorator_list) 
            for node in ast.walk(tree) 
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        )
        if decorator_count > 0:
            self.patterns.append(SemanticPattern(
                pattern_type='structure',
                description=f'decorator_pattern_with_{decorator_count}_decorators',
                entities=[],
                confidence=0.85
            ))
    
    def find_similar_nodes(self, node_id: str) -> List[Tuple[ASTNode, float]]:
        """Find semantically similar nodes based on signature."""
        if node_id not in self.nodes:
            return []
        
        target = self.nodes[node_id]
        similar = []
        
        for node in self.nodes.values():
            if node.id == node_id:
                continue
            
            # Compare by node type
            if node.node_type != target.node_type:
                continue
            
            # Calculate similarity based on semantic signature
            similarity = self._calculate_signature_similarity(
                target.semantic_signature,
                node.semantic_signature
            )
            
            if similarity > 0.5:  # Threshold
                similar.append((node, similarity))
        
        similar.sort(key=lambda x: x[1], reverse=True)
        return similar
    
    def _calculate_signature_similarity(self, sig1: str, sig2: str) -> float:
        """Calculate similarity between two semantic signatures."""
        # Simple Jaccard similarity on signature parts
        parts1 = set(sig1.split('|'))
        parts2 = set(sig2.split('|'))
        
        if not parts1 or not parts2:
            return 0.0
        
        intersection = len(parts1 & parts2)
        union = len(parts1 | parts2)
        
        return intersection / union if union > 0 else 0.0


class ASTAwareRetriever(BaseRetriever):
    """
    AST-Aware retriever that parses code AST for semantic code retrieval.
    
    Uses AST analysis to:
    1. Extract structured code representations
    2. Understand semantic patterns (control flow, API usage, etc.)
    3. Create embeddings that capture code structure and semantics
    4. Enable precise code search by structure and functionality
    """
    
    def __init__(
        self,
        store: Optional[ChromaDocumentStore] = None,
        embedding_model: Optional[BaseEmbeddingModel] = None,
        top_k: int = 5,
        score_threshold: Optional[float] = None,
        filter_fn: Optional[Callable[[Document], bool]] = None,
        include_semantic_signature: bool = True,
        include_patterns: bool = True,
        structure_weight: float = 0.3,
        semantic_weight: float = 0.7
    ):
        """
        Initialize AST-aware retriever.
        
        Args:
            store: Optional ChromaDB store for persistence
            embedding_model: Model for embedding generation
            top_k: Maximum documents to retrieve
            score_threshold: Minimum score threshold
            filter_fn: Optional document filter
            include_semantic_signature: Include AST signatures in embeddings
            include_patterns: Include semantic patterns in search
            structure_weight: Weight for structural similarity
            semantic_weight: Weight for semantic similarity
        """
        super().__init__(top_k=top_k, score_threshold=score_threshold, filter_fn=filter_fn)
        
        self.store = store or ChromaDocumentStore(collection_name="ast_aware")
        self.embedding_model = embedding_model or MiniLMEmbedding()
        self.analyzer = ASTAnalyzer()
        
        self.include_semantic_signature = include_semantic_signature
        self.include_patterns = include_patterns
        self.structure_weight = structure_weight
        self.semantic_weight = semantic_weight
        
        # Track indexed nodes
        self._indexed_nodes: Dict[str, ASTNode] = {}
    
    def add_code(
        self,
        code: str,
        file_path: str = "<unknown>",
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """
        Add code to the retriever with AST analysis.
        
        Args:
            code: Source code
            file_path: Path to source file
            metadata: Additional metadata
            
        Returns:
            List of node IDs added
        """
        # Analyze code
        nodes = self.analyzer.analyze_code(code, file_path)
        
        if not nodes:
            return []
        
        # Create documents with enriched content
        documents = []
        for node in nodes:
            # Build enriched content for embedding
            enriched_content = self._enrich_node_content(node)
            
            # Create document
            doc_metadata = {
                'node_type': node.node_type,
                'name': node.name,
                'file_path': file_path,
                'semantic_signature': node.semantic_signature,
                **node.metadata
            }
            
            if metadata:
                doc_metadata.update(metadata)
            
            doc = Document(
                id=node.id,
                content=enriched_content,
                metadata=doc_metadata
            )
            documents.append(doc)
            self._indexed_nodes[node.id] = node
        
        # Generate embeddings
        self._embed_documents(documents)
        
        # Store in vector DB
        self.store.add(documents)
        
        return [doc.id for doc in documents]
    
    def add_code_documents(self, documents: List[Document]) -> None:
        """
        Add code documents with AST analysis.
        
        Args:
            documents: Documents containing code
        """
        for doc in documents:
            file_path = doc.metadata.get('file_path', doc.id)
            self.add_code(doc.content, file_path, doc.metadata)
    
    def _enrich_node_content(self, node: ASTNode) -> str:
        """
        Create enriched text representation for embedding.
        
        Args:
            node: AST node
            
        Returns:
            Enriched content string
        """
        parts = [f"Type: {node.node_type}", f"Name: {node.name}"]
        
        # Add semantic signature
        if self.include_semantic_signature and node.semantic_signature:
            parts.append(f"Signature: {node.semantic_signature}")
        
        # Add docstring if available
        if node.metadata.get('docstring'):
            parts.append(f"Documentation: {node.metadata['docstring'][:200]}")
        
        # Add control flow patterns
        if node.metadata.get('control_flow'):
            cf_patterns = [p['type'] for p in node.metadata['control_flow']]
            parts.append(f"ControlFlow: {','.join(set(cf_patterns))}")
        
        # Add API calls
        if node.metadata.get('api_calls'):
            api_calls = node.metadata['api_calls'][:5]  # Top 5
            parts.append(f"APIs: {','.join(api_calls)}")
        
        # Add actual code
        parts.append(f"Code: {node.content[:500]}")
        
        return "\n".join(parts)
    
    def _embed_documents(self, documents: List[Document]) -> None:
        """Generate embeddings for documents."""
        texts = [doc.content for doc in documents]
        embeddings = self.embedding_model.embed_documents(texts)
        
        for doc, emb in zip(documents, embeddings):
            doc.embedding = emb
    
    def retrieve(self, query: str) -> List[RetrievedDocument]:
        """
        Retrieve code by query, leveraging AST structure.
        
        Supports:
        - Natural language queries (semantic search)
        - Code structure queries (e.g., "function with try-except")
        - API usage queries (e.g., "uses requests.get")
        
        Args:
            query: Search query
            
        Returns:
            List of retrieved code nodes
        """
        # Parse query for structural hints
        structured_query = self._parse_query(query)
        
        # Get base results from vector search
        query_embedding = self.embedding_model.embed_query(structured_query)
        
        vector_results = self.store.search(
            query_embedding=query_embedding,
            top_k=self.top_k * 2
        )
        
        # Score and rank with structural awareness
        results = []
        for rank, doc in enumerate(vector_results, start=1):
            # Calculate structure score
            structure_score = self._calculate_structure_score(doc, query)
            
            # Calculate semantic score (from vector similarity)
            semantic_score = self._calculate_semantic_score(rank, len(vector_results))
            
            # Fuse scores
            fused_score = (
                self.structure_weight * structure_score +
                self.semantic_weight * semantic_score
            )
            
            retrieved = RetrievedDocument(
                document=doc,
                score=fused_score,
                rank=rank
            )
            results.append(retrieved)
        
        # Sort by fused score
        results.sort(key=lambda r: r.score, reverse=True)
        
        # Apply threshold and filter
        if self.score_threshold is not None:
            results = [r for r in results if r.score >= self.score_threshold]
        
        if self.filter_fn:
            results = [r for r in results if self.filter_fn(r.document)]
        
        # Re-rank
        for i, r in enumerate(results, start=1):
            r.rank = i
        
        return results[:self.top_k]
    
    def _parse_query(self, query: str) -> str:
        """
        Parse query to enhance with structural hints.
        
        Args:
            query: Raw query
            
        Returns:
            Enhanced query for embedding
        """
        query_lower = query.lower()
        enhancements = []
        
        # Detect node type hints
        if any(kw in query_lower for kw in ['function', 'def', 'method']):
            enhancements.append("Type: FunctionDef")
        elif any(kw in query_lower for kw in ['class', 'object']):
            enhancements.append("Type: ClassDef")
        elif any(kw in query_lower for kw in ['import', 'module']):
            enhancements.append("Type: Import")
        
        # Detect control flow hints
        if 'try' in query_lower or 'except' in query_lower or 'error' in query_lower:
            enhancements.append("ControlFlow: try")
        if 'async' in query_lower or 'await' in query_lower:
            enhancements.append("Type: AsyncFunctionDef")
        if 'decorator' in query_lower:
            enhancements.append("decorator_pattern")
        
        # Combine
        if enhancements:
            return f"{query}\nHints: {'; '.join(enhancements)}"
        
        return query
    
    def _calculate_structure_score(self, doc: Document, query: str) -> float:
        """
        Calculate structure-based relevance score.
        
        Args:
            doc: Document to score
            query: Original query
            
        Returns:
            Structure score (0-1)
        """
        score = 0.0
        query_lower = query.lower()
        
        metadata = doc.metadata
        
        # Node type matching
        node_type = metadata.get('node_type', '').lower()
        if 'function' in query_lower and node_type == 'functiondef':
            score += 0.3
        elif 'class' in query_lower and node_type == 'classdef':
            score += 0.3
        
        # Control flow matching
        control_flow = metadata.get('control_flow', [])
        cf_types = [p['type'] for p in control_flow]
        
        if 'try' in query_lower and 'try' in cf_types:
            score += 0.2
        if 'for' in query_lower and 'for' in cf_types:
            score += 0.1
        if 'async' in query_lower and metadata.get('is_async'):
            score += 0.2
        
        # API matching
        api_calls = metadata.get('api_calls', [])
        for api in api_calls:
            if any(part in query_lower for part in api.lower().split('.')):
                score += 0.15
                break
        
        # Decorator matching
        decorators = metadata.get('decorators', [])
        if 'decorator' in query_lower and decorators:
            score += 0.1
        
        return min(score, 1.0)
    
    def _calculate_semantic_score(self, rank: int, total: int) -> float:
        """
        Calculate semantic score from rank position.
        
        Args:
            rank: Position in results (1-based)
            total: Total number of results
            
        Returns:
            Semantic score (0-1)
        """
        import math
        # Exponential decay based on rank
        return math.exp(-0.1 * (rank - 1))
    
    def find_similar_functions(self, func_name: str) -> List[RetrievedDocument]:
        """
        Find functions with similar structure to the named function.
        
        Args:
            func_name: Name of the reference function
            
        Returns:
            List of similar functions
        """
        # Find the reference function
        reference_node = None
        for node in self._indexed_nodes.values():
            if node.name == func_name and node.node_type == 'FunctionDef':
                reference_node = node
                break
        
        if not reference_node:
            return []
        
        # Find similar nodes using analyzer
        similar = self.analyzer.find_similar_nodes(reference_node.id)
        
        results = []
        for i, (node, similarity) in enumerate(similar[:self.top_k], start=1):
            if node.id in self._indexed_nodes:
                doc = self.store.get(node.id)
                if doc:
                    retrieved = RetrievedDocument(
                        document=doc,
                        score=similarity,
                        rank=i
                    )
                    results.append(retrieved)
        
        return results
    
    def search_by_pattern(
        self,
        pattern_type: str,
        description: Optional[str] = None
    ) -> List[RetrievedDocument]:
        """
        Search for code matching specific semantic patterns.
        
        Args:
            pattern_type: Pattern type ('control_flow', 'api_usage', 'structure')
            description: Optional pattern description filter
            
        Returns:
            List of matching code nodes
        """
        results = []
        
        for pattern in self.analyzer.patterns:
            if pattern.pattern_type != pattern_type:
                continue
            
            if description and description not in pattern.description:
                continue
            
            # Find relevant nodes for this pattern
            for node in self._indexed_nodes.values():
                doc = self.store.get(node.id)
                if doc:
                    results.append(RetrievedDocument(
                        document=doc,
                        score=pattern.confidence,
                        rank=0  # Will be updated
                    ))
        
        # Sort by confidence and rank
        results.sort(key=lambda r: r.score, reverse=True)
        for i, r in enumerate(results[:self.top_k], start=1):
            r.rank = i
        
        return results[:self.top_k]
    
    def get_code_statistics(self) -> Dict[str, Any]:
        """Get statistics about the indexed code."""
        node_types = defaultdict(int)
        total_lines = 0
        
        for node in self._indexed_nodes.values():
            node_types[node.node_type] += 1
            if node.metadata.get('line_end') and node.metadata.get('line_start'):
                total_lines += node.metadata['line_end'] - node.metadata['line_start'] + 1
        
        return {
            'total_nodes': len(self._indexed_nodes),
            'node_types': dict(node_types),
            'estimated_total_lines': total_lines,
            'patterns': len(self.analyzer.patterns),
            'document_count': self.store.count()
        }
    
    def is_available(self) -> bool:
        """Check if retriever has indexed code."""
        return len(self._indexed_nodes) > 0 or self.store.count() > 0
