"""Query optimization and expansion for improved retrieval."""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class OptimizedQuery:
    """An optimized query with original and expanded forms."""
    original: str
    expanded: str
    hypothetical_doc: Optional[str] = None
    keywords: List[str] = None
    
    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []


class QueryExpander:
    """Expand queries with synonyms and related terms."""
    
    # Common technical term synonyms
    DEFAULT_SYNONYMS = {
        "config": ["configuration", "settings", "options"],
        "error": ["exception", "failure", "bug", "issue"],
        "function": ["method", "procedure", "routine"],
        "variable": ["var", "parameter", "argument"],
        "class": ["type", "object", "struct"],
        "import": ["include", "require", "load"],
        "async": ["asynchronous", "promise", "future"],
        "sync": ["synchronous", "blocking"],
        "api": ["interface", "endpoint"],
        "db": ["database", "storage", "repository"],
        "ui": ["interface", "frontend", "view"],
        "auth": ["authentication", "login", "security"],
        "test": ["testing", "unit test", "spec"],
        "deploy": ["deployment", "release", "publish"],
        "build": ["compile", "transpile", "bundle"],
        "debug": ["troubleshoot", "diagnose"],
        "install": ["setup", "configure", "add"],
        "update": ["upgrade", "refresh", "sync"],
        "delete": ["remove", "drop", "clear"],
        "create": ["make", "generate", "init"],
    }
    
    def __init__(self, synonyms: Optional[Dict[str, List[str]]] = None, cache_size: int = 1000):
        """Initialize query expander.
        
        Args:
            synonyms: Custom synonym dictionary (merges with defaults)
            cache_size: Maximum number of cached expansions
        """
        self.synonyms = dict(self.DEFAULT_SYNONYMS)
        if synonyms:
            self.synonyms.update(synonyms)
        
        # LRU cache for query expansions
        self._cache: Dict[str, str] = {}
        self._cache_order: List[str] = []
        self._cache_size = cache_size
        
    def _get_cache_key(self, query: str) -> str:
        """Generate cache key for query."""
        return query.lower().strip()
    
    def _get_cached(self, query: str) -> Optional[str]:
        """Get cached expansion if available."""
        key = self._get_cache_key(query)
        if key in self._cache:
            # Move to end (most recently used)
            self._cache_order.remove(key)
            self._cache_order.append(key)
            return self._cache[key]
        return None
    
    def _set_cached(self, query: str, expanded: str) -> None:
        """Cache expansion result."""
        key = self._get_cache_key(query)
        
        if key in self._cache:
            # Update existing
            self._cache_order.remove(key)
        elif len(self._cache) >= self._cache_size:
            # Evict oldest
            oldest = self._cache_order.pop(0)
            del self._cache[oldest]
        
        self._cache[key] = expanded
        self._cache_order.append(key)
    
    def expand(self, query: str, use_cache: bool = True) -> str:
        """Expand query with synonyms.
        
        Args:
            query: Original query
            use_cache: Whether to use caching
            
        Returns:
            Expanded query string
        """
        # Check cache first
        if use_cache:
            cached = self._get_cached(query)
            if cached is not None:
                return cached
        
        query_lower = query.lower()
        expanded_terms = [query]
        added_terms = set()
        
        for term, alts in self.synonyms.items():
            if term in query_lower:
                # Add alternative terms
                for alt in alts:
                    alt_lower = alt.lower()
                    if alt_lower not in query_lower and alt_lower not in added_terms:
                        expanded_terms.append(alt)
                        added_terms.add(alt_lower)
        
        result = " ".join(expanded_terms)
        
        # Cache result
        if use_cache:
            self._set_cached(query, result)
        
        return result
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dict with cache stats
        """
        return {
            "size": len(self._cache),
            "max_size": self._cache_size,
            "hit_rate": None,  # Would need hit/miss counters
            "enabled": self._cache_size > 0
        }
    
    def extract_keywords(self, query: str) -> List[str]:
        """Extract keywords from query.
        
        Args:
            query: Query string
            
        Returns:
            List of keywords
        """
        # Remove common stop words
        stop_words = {
            'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'must', 'shall',
            'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
            'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
            'through', 'during', 'before', 'after', 'above', 'below',
            'between', 'under', 'and', 'but', 'or', 'yet', 'so',
            'if', 'because', 'although', 'though', 'while', 'where',
            'when', 'that', 'which', 'who', 'whom', 'whose', 'what',
            'this', 'these', 'those', 'i', 'me', 'my', 'myself', 'we',
            'our', 'ours', 'ourselves', 'you', 'your', 'yours', 'yourself',
            'yourselves', 'he', 'him', 'his', 'himself', 'she', 'her',
            'hers', 'herself', 'it', 'its', 'itself', 'they', 'them',
            'their', 'theirs', 'themselves', 'how', 'all', 'any', 'both',
            'each', 'few', 'more', 'most', 'other', 'some', 'such',
            'no', 'nor', 'not', 'only', 'own', 'same', 'than', 'too',
            'very', 'just', 'now'
        }
        
        # Tokenize and filter
        words = re.findall(r'\b[a-zA-Z]+\b', query.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        
        return keywords
    
    def get_expansion_info(self, query: str) -> Dict[str, Any]:
        """Get detailed expansion information.
        
        Args:
            query: Original query
            
        Returns:
            Dict with original, expanded, keywords, and matched_synonyms
        """
        original = query.strip()
        expanded = self.expand(original)
        keywords = self.extract_keywords(original)
        
        # Find which synonyms were matched
        query_lower = original.lower()
        matched_synonyms = {}
        for term, alts in self.synonyms.items():
            if term in query_lower:
                matched_synonyms[term] = alts
        
        return {
            "original": original,
            "expanded": expanded,
            "keywords": keywords,
            "matched_synonyms": matched_synonyms,
            "expansion_count": len(expanded.split()) - len(original.split())
        }


class HyDEGenerator:
    """Hypothetical Document Embedding (HyDE) generator.
    
    Generates a hypothetical answer/document based on the query,
    which can be used for better semantic search.
    """
    
    def __init__(self):
        """Initialize HyDE generator."""
        self._llm_available = False
        self._check_llm()
    
    def _check_llm(self):
        """Check if LLM is available for generating hypothetical documents."""
        try:
            # Try to import common LLM libraries
            import openai
            self._llm_available = True
            self._llm_type = "openai"
        except ImportError:
            try:
                import transformers
                self._llm_available = True
                self._llm_type = "transformers"
            except ImportError:
                self._llm_available = False
    
    def generate(
        self,
        query: str,
        context: Optional[str] = None
    ) -> Optional[str]:
        """Generate hypothetical document for query.
        
        Without an LLM, this returns a template-based hypothetical document.
        
        Args:
            query: Search query
            context: Optional context about the domain
            
        Returns:
            Hypothetical document text or None
        """
        if self._llm_available:
            # Would use actual LLM here
            # For now, fall through to template-based approach
            pass
        
        # Template-based generation
        return self._generate_template(query, context)
    
    def _generate_template(self, query: str, context: Optional[str] = None) -> str:
        """Generate template-based hypothetical document.
        
        Args:
            query: Search query
            context: Optional domain context
            
        Returns:
            Hypothetical document
        """
        keywords = QueryExpander().extract_keywords(query)
        
        # Build a structured hypothetical answer
        sections = [
            f"Question: {query}",
            "",
            "Answer:",
        ]
        
        if keywords:
            sections.append(f"This involves {', '.join(keywords)}.")
        
        sections.extend([
            "Here is the detailed explanation and implementation:",
            "",
            "Key concepts: " + ", ".join(keywords[:5]) if keywords else "Key information",
            "",
            "Steps to implement:",
            "1. Understand the requirements",
            "2. Apply the appropriate solution",
            "3. Verify the results",
        ])
        
        if context:
            sections.extend([
                "",
                f"Context: {context}",
            ])
        
        return "\n".join(sections)


class QueryOptimizer:
    """Main query optimizer combining multiple techniques."""
    
    def __init__(
        self,
        use_expansion: bool = True,
        use_hyde: bool = False,
        synonyms: Optional[Dict[str, List[str]]] = None
    ):
        """Initialize query optimizer.
        
        Args:
            use_expansion: Whether to use query expansion
            use_hyde: Whether to use HyDE
            synonyms: Custom synonym dictionary
        """
        self.use_expansion = use_expansion
        self.use_hyde = use_hyde
        
        self.expander = QueryExpander(synonyms) if use_expansion else None
        self.hyde = HyDEGenerator() if use_hyde else None
    
    def optimize(self, query: str) -> OptimizedQuery:
        """Optimize a query.
        
        Args:
            query: Original query
            
        Returns:
            OptimizedQuery with expanded forms
        """
        original = query.strip()
        
        # Extract keywords
        keywords = self.expander.extract_keywords(original) if self.expander else []
        
        # Expand query
        expanded = original
        if self.expander:
            expanded = self.expander.expand(original)
        
        # Generate hypothetical document
        hypothetical_doc = None
        if self.hyde:
            hypothetical_doc = self.hyde.generate(original)
        
        return OptimizedQuery(
            original=original,
            expanded=expanded,
            hypothetical_doc=hypothetical_doc,
            keywords=keywords
        )
    
    def optimize_for_vector_search(self, query: str) -> str:
        """Get optimized query text for vector search.
        
        If HyDE is enabled and available, returns the hypothetical document.
        Otherwise, returns the expanded query.
        
        Args:
            query: Original query
            
        Returns:
            Optimized query for embedding
        """
        optimized = self.optimize(query)
        
        if self.use_hyde and optimized.hypothetical_doc:
            return optimized.hypothetical_doc
        
        return optimized.expanded
    
    def optimize_for_keyword_search(self, query: str) -> str:
        """Get optimized query text for keyword/BM25 search.
        
        Args:
            query: Original query
            
        Returns:
            Optimized query for keyword search
        """
        optimized = self.optimize(query)
        
        # For keyword search, use original + keywords
        if optimized.keywords:
            return f"{optimized.original} {' '.join(optimized.keywords)}"
        
        return optimized.expanded
    
    def get_expansion_info(self, query: str) -> Dict[str, Any]:
        """Get detailed expansion information.
        
        Args:
            query: Original query
            
        Returns:
            Dict with expansion details
        """
        return self.expander.get_expansion_info(query)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics from the expander.
        
        Returns:
            Dict with cache stats
        """
        return self.expander.get_cache_stats()


def create_optimizer(
    mode: str = "expansion",
    synonyms: Optional[Dict[str, List[str]]] = None
) -> QueryOptimizer:
    """Factory function to create a query optimizer.
    
    Args:
        mode: Optimization mode - "none", "expansion", "hyde", or "full"
        synonyms: Custom synonym dictionary
        
    Returns:
        QueryOptimizer instance
    """
    modes = {
        "none": (False, False),
        "expansion": (True, False),
        "hyde": (False, True),
        "full": (True, True),
    }
    
    use_expansion, use_hyde = modes.get(mode, (True, False))
    
    return QueryOptimizer(
        use_expansion=use_expansion,
        use_hyde=use_hyde,
        synonyms=synonyms
    )
