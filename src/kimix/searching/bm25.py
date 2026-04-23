from __future__ import annotations

import math
from typing import Any


class Search:
    """BM25 + N-gram search over a single input string."""

    def __init__(self, content: str, n: int = 2, k1: float = 1.2, b: float = 0.75) -> None:
        self.n: int = n
        self.k1: float = k1
        self.b: float = b
        self.docs: list[str] = []
        self.doc_lengths: list[int] = []
        self.inverted_index: dict[str, dict[int, int]] = {}
        self.idf: dict[str, float] = {}
        self.avgdl: float = 0.0
        self.N: int = 0

        self._build_index(content)

    def _tokenize(self, text: str) -> list[str]:
        """Generate character N-grams from text."""
        tokens: list[str] = []
        text = text.strip()
        if len(text) < self.n:
            if text:
                tokens.append(text)
            return tokens
        for i in range(len(text) - self.n + 1):
            tokens.append(text[i:i + self.n])
        return tokens

    def _build_index(self, content: str) -> None:
        """Build inverted index from content string."""
        lines = content.split("\n")

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            self.docs.append(stripped)
            tokens = self._tokenize(stripped)
            self.doc_lengths.append(len(tokens))
            doc_id = len(self.docs) - 1

            # Count term frequencies
            tf_dict: dict[str, int] = {}
            for token in tokens:
                tf_dict[token] = tf_dict.get(token, 0) + 1

            # Add to inverted index
            for token, freq in tf_dict.items():
                if token not in self.inverted_index:
                    self.inverted_index[token] = {}
                self.inverted_index[token][doc_id] = freq

        self.N = len(self.docs)
        if self.N == 0:
            self.avgdl = 0.0
            return

        total_length = sum(self.doc_lengths)
        self.avgdl = total_length / self.N

        # Compute IDF for each term
        for token, postings in self.inverted_index.items():
            df = len(postings)
            # BM25 IDF formula
            self.idf[token] = math.log((self.N - df + 0.5) / (df + 0.5) + 1.0)

    def search(self, keywords: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search documents using BM25 + N-gram algorithm."""
        if self.N == 0:
            return []

        query_tokens = self._tokenize(keywords)
        if not query_tokens:
            return []

        # Collect candidate documents
        candidates: set[int] = set()
        for token in query_tokens:
            if token in self.inverted_index:
                candidates.update(self.inverted_index[token].keys())

        # Score candidates
        scores: dict[int, float] = {}
        for doc_id in candidates:
            dl = self.doc_lengths[doc_id]
            score = 0.0

            for token in query_tokens:
                if token not in self.inverted_index:
                    continue
                if doc_id not in self.inverted_index[token]:
                    continue

                tf = self.inverted_index[token][doc_id]
                idf = self.idf[token]

                # BM25 scoring formula
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * dl / self.avgdl)
                score += idf * numerator / denominator

            scores[doc_id] = score

        # Sort by score descending
        sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        results: list[dict[str, Any]] = []
        for doc_id, score in sorted_docs[:top_k]:
            matched_terms = [
                token for token in query_tokens
                if token in self.inverted_index and doc_id in self.inverted_index[token]
            ]
            results.append({
                "doc_id": doc_id,
                "score": score,
                "text": self.docs[doc_id],
                "matched_terms": matched_terms,
            })

        return results
