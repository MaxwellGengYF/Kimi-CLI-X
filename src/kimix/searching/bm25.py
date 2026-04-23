from __future__ import annotations

import math
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np
from numpy.typing import NDArray


class Search:
    """BM25 + N-gram search over a single input string."""

    _CHUNK_SIZE = 1000

    def __init__(self, content: str, n: int = 2, k1: float = 1.2, b: float = 0.75) -> None:
        self.n: int = n
        self.k1: float = k1
        self.b: float = b
        self._docs: list[str] = []
        self._line_indices: list[int] = []
        self._doc_lengths_arr: NDArray[np.int32] = np.empty(0, dtype=np.int32)
        self._term_to_id: dict[str, int] = {}
        self._posting_docs: list[NDArray[np.int32]] = []
        self._posting_tfs: list[NDArray[np.uint16]] = []
        self._idf_arr: NDArray[np.float64] = np.empty(0, dtype=np.float64)
        self.avgdl: float = 0.0
        self.N: int = 0

        self._build_index(content)

    @property
    def docs(self) -> list[str]:
        return self._docs

    @property
    def doc_lengths(self) -> list[int]:
        return [int(x) for x in self._doc_lengths_arr]

    @property
    def inverted_index(self) -> dict[str, dict[int, int]]:
        if self.N == 0:
            return {}
        result: dict[str, dict[int, int]] = {}
        for term, tid in self._term_to_id.items():
            docs = self._posting_docs[tid]
            tfs = self._posting_tfs[tid]
            result[term] = {int(d): int(f) for d, f in zip(docs, tfs)}
        return result

    @property
    def idf(self) -> dict[str, float]:
        return {
            term: float(self._idf_arr[tid])
            for term, tid in self._term_to_id.items()
        }

    def _tokenize(self, text: str) -> list[str]:
        """Generate character N-grams from text."""
        text = text.strip()
        if not text:
            return []
        if len(text) < self.n:
            return [text]
        return [text[i : i + self.n] for i in range(len(text) - self.n + 1)]

    def _process_chunk(
        self, lines: list[str], start_idx: int = 0
    ) -> tuple[list[str], list[int], list[Counter[str]], list[int]]:
        """Process a chunk of lines: tokenize and count term frequencies."""
        docs: list[str] = []
        doc_lengths: list[int] = []
        counters: list[Counter[str]] = []
        line_indices: list[int] = []
        for offset, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            docs.append(stripped)
            tokens = self._tokenize(stripped)
            doc_lengths.append(len(tokens))
            counters.append(Counter(tokens))
            line_indices.append(start_idx + offset)
        return docs, doc_lengths, counters, line_indices

    def _build_index(self, content: str) -> None:
        """Build inverted index from content string."""
        lines = content.split("\n")
        total_lines = len(lines)

        if total_lines == 0:
            self.N = 0
            self.avgdl = 0.0
            return

        docs: list[str]
        doc_lengths: list[int]
        counters: list[Counter[str]]
        line_indices: list[int]
        if total_lines < self._CHUNK_SIZE:
            docs, doc_lengths, counters, line_indices = self._process_chunk(lines, 0)
        else:
            chunks = [
                lines[i : i + self._CHUNK_SIZE]
                for i in range(0, total_lines, self._CHUNK_SIZE)
            ]
            docs = []
            doc_lengths = []
            counters = []
            line_indices = []
            with ThreadPoolExecutor() as executor:
                futures = [
                    executor.submit(self._process_chunk, chunk, i)
                    for i, chunk in enumerate(chunks)
                ]
                for future in futures:
                    chunk_docs, chunk_dl, chunk_counters, chunk_li = future.result()
                    docs.extend(chunk_docs)
                    doc_lengths.extend(chunk_dl)
                    counters.extend(chunk_counters)
                    line_indices.extend(chunk_li)

        self._docs = docs
        self._line_indices = line_indices
        self._doc_lengths_arr = np.array(doc_lengths, dtype=np.int32)
        self.N = len(self._docs)

        if self.N == 0:
            self.avgdl = 0.0
            return

        self.avgdl = float(self._doc_lengths_arr.mean())

        # Build posting lists
        token_to_postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for doc_id, counter in enumerate(counters):
            for token, freq in counter.items():
                token_to_postings[token].append((doc_id, freq))

        # Convert to compact numpy arrays
        self._term_to_id = {}
        self._posting_docs = []
        self._posting_tfs = []
        idf_values: list[float] = []

        for idx, (token, postings) in enumerate(token_to_postings.items()):
            self._term_to_id[token] = idx
            postings_arr = np.array(postings, dtype=np.int32)
            sort_order = np.argsort(postings_arr[:, 0])
            postings_arr = postings_arr[sort_order]
            self._posting_docs.append(postings_arr[:, 0])
            self._posting_tfs.append(postings_arr[:, 1].astype(np.uint16))
            df = len(postings)
            idf_values.append(math.log((self.N - df + 0.5) / (df + 0.5) + 1.0))

        self._idf_arr = np.array(idf_values, dtype=np.float64)

    def search(self, keywords: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search documents using BM25 + N-gram algorithm."""
        if self.N == 0:
            return []

        query_tokens = self._tokenize(keywords)
        if not query_tokens:
            return []

        scores = np.zeros(self.N, dtype=np.float64)

        for token in query_tokens:
            tid = self._term_to_id.get(token)
            if tid is None:
                continue
            docs = self._posting_docs[tid]
            tfs = self._posting_tfs[tid]
            idf = self._idf_arr[tid]
            dl = self._doc_lengths_arr[docs]

            # BM25 scoring formula - vectorized
            tfs_f = tfs.astype(np.float64)
            numerator = tfs_f * (self.k1 + 1.0)
            denominator = tfs_f + self.k1 * (1.0 - self.b + self.b * dl / self.avgdl)
            scores[docs] += idf * numerator / denominator

        # Get non-zero scores
        nz_mask = scores > 0
        nz_count = int(nz_mask.sum())
        if nz_count == 0:
            return []

        if top_k <= 0:
            return []

        nz_indices = np.where(nz_mask)[0]
        nz_scores = scores[nz_indices]

        # Top-k selection
        if nz_count > top_k:
            top_idx = np.argpartition(nz_scores, -top_k)[-top_k:]
            top_idx = top_idx[np.argsort(-nz_scores[top_idx], kind="mergesort")]
        else:
            top_idx = np.argsort(-nz_scores, kind="mergesort")

        top_doc_ids = nz_indices[top_idx]
        top_scores = nz_scores[top_idx]

        # Build results
        results: list[dict[str, Any]] = []
        for doc_id, score in zip(top_doc_ids, top_scores):
            doc_id_int = int(doc_id)
            results.append({
                "doc_id": doc_id_int,
                "score": float(score),
                "line_index": self._line_indices[doc_id_int],
            })

        return results
