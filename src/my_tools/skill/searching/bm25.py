from __future__ import annotations

import math
import pickle
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from numpy.typing import NDArray


class NgramTokenizer:
    """Overlapping n-gram generator with text normalization."""

    def __init__(self, n: int = 2) -> None:
        self.n = n

    @staticmethod
    def normalize(text: str) -> str:
        """Lower-case and apply Unicode NFKC normalization."""
        return unicodedata.normalize("NFKC", text.lower())

    @staticmethod
    def _is_cjk(char: str) -> bool:
        cp = ord(char)
        return (
            (0x4E00 <= cp <= 0x9FFF)          # CJK Unified Ideographs
            or (0x3400 <= cp <= 0x4DBF)       # Extension A
            or (0x20000 <= cp <= 0x2EBEF)     # Extensions B–F
            or (0xAC00 <= cp <= 0xD7AF)       # Hangul Syllables
            or (0x3040 <= cp <= 0x309F)       # Hiragana
            or (0x30A0 <= cp <= 0x30FF)       # Katakana
        )

    def _detect_n(self, text: str) -> int:
        """Auto-detect n-gram size: bigram for CJK, trigram for mixed/code."""
        if not text:
            return self.n
        cjk_count = sum(1 for c in text if self._is_cjk(c))
        if cjk_count > len(text) * 0.3:
            return 2
        return 3 if self.n < 3 else self.n

    def tokenize(self, text: str, n: int | None = None) -> list[str]:
        """Generate overlapping character n-grams from *text*."""
        text = self.normalize(text).strip()
        if not text:
            return []
        use_n = n if n is not None else self._detect_n(text)
        if len(text) < use_n:
            return [text]
        return [text[i : i + use_n] for i in range(len(text) - use_n + 1)]


class InvertedIndex:
    """Inverted index: build, persist, and load."""

    def __init__(self) -> None:
        self._term_to_id: dict[str, int] = {}
        self._temp_postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self._doc_lengths: list[int] = []
        self._N: int = 0
        self._avgdl: float = 0.0
        # Finalized compact arrays
        self._posting_docs: list[NDArray[np.int32]] = []
        self._posting_tfs: list[NDArray[np.uint16]] = []
        self._finalized: bool = False

    @property
    def N(self) -> int:
        return self._N

    @property
    def avgdl(self) -> float:
        return self._avgdl

    @property
    def doc_lengths(self) -> list[int]:
        return self._doc_lengths

    def add_document(self, doc_id: int, tokens: list[str]) -> None:
        """Add a document's tokens to the index."""
        if self._finalized:
            raise RuntimeError("Cannot add documents after finalize().")
        counter = Counter(tokens)
        self._doc_lengths.append(len(tokens))
        for token, freq in counter.items():
            if token not in self._term_to_id:
                self._term_to_id[token] = len(self._term_to_id)
            self._temp_postings[token].append((doc_id, freq))
        self._N = max(self._N, doc_id + 1)

    def _is_stop_ngram(self, token: str, df: int, threshold: float = 0.5) -> bool:
        """Drop n-grams appearing in >*threshold* fraction of docs or pure punctuation."""
        if not token:
            return True
        if df > self._N * threshold:
            return True
        if all(unicodedata.category(c).startswith("P") for c in token):
            return True
        return False

    def finalize(self, stop_threshold: float = 0.5, prune_df: int | None = None) -> None:
        """Convert temporary postings to compact numpy arrays."""
        if self._finalized:
            return

        self._posting_docs = []
        self._posting_tfs = []
        kept_terms: dict[str, int] = {}

        for token, postings in self._temp_postings.items():
            df = len(postings)
            if self._is_stop_ngram(token, df, stop_threshold):
                continue
            if prune_df is not None and df > prune_df:
                continue
            tid = len(kept_terms)
            kept_terms[token] = tid
            arr = np.array(postings, dtype=np.int32)
            sort_order = np.argsort(arr[:, 0])
            arr = arr[sort_order]
            self._posting_docs.append(arr[:, 0])
            self._posting_tfs.append(arr[:, 1].astype(np.uint16))

        self._term_to_id = kept_terms
        if self._doc_lengths:
            self._avgdl = sum(self._doc_lengths) / len(self._doc_lengths)
        self._finalized = True

    def get_postings(
        self, term: str
    ) -> tuple[NDArray[np.int32], NDArray[np.uint16]] | None:
        """Return (doc_ids, term_frequencies) for *term*, or ``None``."""
        if not self._finalized:
            self.finalize()
        tid = self._term_to_id.get(term)
        if tid is None:
            return None
        return self._posting_docs[tid], self._posting_tfs[tid]

    def doc_freq(self, term: str) -> int:
        """Document frequency of *term*."""
        postings = self.get_postings(term)
        if postings is None:
            return 0
        return len(postings[0])

    def has_term(self, term: str) -> bool:
        return term in self._term_to_id

    def terms(self) -> Iterable[str]:
        return self._term_to_id.keys()

    def save(self, path: str | Path) -> None:
        """Persist the index to disk."""
        if not self._finalized:
            self.finalize()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(
                {
                    "term_to_id": self._term_to_id,
                    "posting_docs": self._posting_docs,
                    "posting_tfs": self._posting_tfs,
                    "doc_lengths": self._doc_lengths,
                    "N": self._N,
                    "avgdl": self._avgdl,
                },
                f,
            )

    def load(self, path: str | Path) -> None:
        """Load a persisted index from disk."""
        with open(path, "rb") as f:
            data = pickle.load(f)
        self._term_to_id = data["term_to_id"]
        self._posting_docs = data["posting_docs"]
        self._posting_tfs = data["posting_tfs"]
        self._doc_lengths = data["doc_lengths"]
        self._N = data["N"]
        self._avgdl = data["avgdl"]
        self._finalized = True


class BM25Scorer:
    """BM25 relevance scorer over an :class:`InvertedIndex`."""

    def __init__(
        self,
        index: InvertedIndex,
        k1: float = 1.2,
        b: float = 0.75,
    ) -> None:
        self.index = index
        self.k1 = k1
        self.b = b

    @staticmethod
    def _idf(df: int, N: int) -> float:
        """IDF = ln((N - df + 0.5) / (df + 0.5))."""
        return math.log((N - df + 0.5) / (df + 0.5))

    def score(
        self,
        query_tokens: list[str],
        candidate_docs: set[int] | None = None,
    ) -> dict[int, float]:
        """Accumulate BM25 score per candidate document.

        ``candidate_docs`` restricts scoring to a subset of docs; ``None``
        scores every document that has at least one query token.
        """
        scores: dict[int, float] = defaultdict(float)
        N = self.index.N
        avgdl = self.index.avgdl
        if N == 0 or avgdl == 0:
            return {}

        for token in query_tokens:
            postings = self.index.get_postings(token)
            if postings is None:
                continue
            docs, tfs = postings
            df = len(docs)
            idf = self._idf(df, N)
            for doc_id, tf in zip(docs, tfs):
                doc_id_int = int(doc_id)
                if candidate_docs is not None and doc_id_int not in candidate_docs:
                    continue
                dl = self.index.doc_lengths[doc_id_int]
                denom = float(tf) + self.k1 * (1.0 - self.b + self.b * dl / avgdl)
                if denom == 0:
                    continue
                scores[doc_id_int] += idf * float(tf) * (self.k1 + 1.0) / denom

        return dict(scores)


class LevenshteinAutomaton:
    """Damerau-Levenshtein automaton for fuzzy term expansion."""

    def __init__(
        self,
        pattern: str,
        max_edits: int,
        prefix_length: int = 1,
    ) -> None:
        self.pattern = pattern
        self.max_edits = max_edits
        self.prefix_length = prefix_length

    @staticmethod
    def auto_fuzziness(term: str) -> int:
        """AUTO mode: 0–2 chars → 0, 3–5 → 1, >5 → 2."""
        length = len(term)
        if length <= 2:
            return 0
        if length <= 5:
            return 1
        return 2

    def _damerau_levenshtein(self, s: str, t: str) -> int:
        """Compute Damerau-Levenshtein distance between *s* and *t*."""
        m, n = len(s), len(t)
        if m < n:
            return self._damerau_levenshtein(t, s)
        if n == 0:
            return m

        prev_prev = list(range(n + 1))
        prev = list(range(n + 1))
        curr = [0] * (n + 1)
        for i in range(1, m + 1):
            curr[0] = i
            for j in range(1, n + 1):
                cost = 0 if s[i - 1] == t[j - 1] else 1
                curr[j] = min(
                    curr[j - 1] + 1,      # insertion
                    prev[j] + 1,          # deletion
                    prev[j - 1] + cost,   # substitution
                )
                if (
                    i > 1
                    and j > 1
                    and s[i - 1] == t[j - 2]
                    and s[i - 2] == t[j - 1]
                ):
                    curr[j] = min(curr[j], prev_prev[j - 2] + 1)  # transposition
            prev_prev, prev, curr = prev, curr, prev_prev
        return prev[n]

    def match(self, dictionary: Iterable[str], max_expansions: int = 50) -> list[str]:
        """Walk *dictionary* and collect up to *max_expansions* matches."""
        results: list[str] = []
        for term in dictionary:
            if len(results) >= max_expansions:
                break
            if self.prefix_length > 0:
                if (
                    len(term) >= self.prefix_length
                    and len(self.pattern) >= self.prefix_length
                    and term[: self.prefix_length] != self.pattern[: self.prefix_length]
                ):
                    continue
            if self._damerau_levenshtein(self.pattern, term) <= self.max_edits:
                results.append(term)
        return results


class Searcher:
    """Query pipeline orchestrator: normalize → tokenize → score → rank."""

    def __init__(
        self,
        index: InvertedIndex,
        tokenizer: NgramTokenizer | None = None,
        scorer: BM25Scorer | None = None,
        k1: float = 1.2,
        b: float = 0.75,
        min_should_match: float = 0.5,
        fuzziness: str | int = "AUTO",
        max_expansions: int = 50,
        prefix_length: int = 1,
    ) -> None:
        self.index = index
        self.tokenizer = tokenizer or NgramTokenizer()
        self.scorer = scorer or BM25Scorer(index, k1=k1, b=b)
        self.k1 = k1
        self.b = b
        self.min_should_match = min_should_match
        self.fuzziness = fuzziness
        self.max_expansions = max_expansions
        self.prefix_length = prefix_length

    @staticmethod
    def _is_latin_token(token: str) -> bool:
        """Heuristic: token is primarily Latin/ASCII."""
        return bool(token) and all(ord(c) < 128 for c in token)

    def _expand_token(self, token: str) -> list[str]:
        """Fuzzy-expand a Latin token; CJK tokens are returned verbatim if present."""
        if not self._is_latin_token(token):
            return [token] if self.index.has_term(token) else []

        max_edits = (
            LevenshteinAutomaton.auto_fuzziness(token)
            if self.fuzziness == "AUTO"
            else int(self.fuzziness)
        )
        if max_edits == 0:
            return [token] if self.index.has_term(token) else []

        automaton = LevenshteinAutomaton(
            token, max_edits=max_edits, prefix_length=self.prefix_length
        )
        matches = automaton.match(
            self.index.terms(), max_expansions=self.max_expansions
        )
        return matches if matches else ([token] if self.index.has_term(token) else [])

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """Run the full query pipeline and return top-k *(doc_id, score)* pairs."""
        if self.index.N == 0:
            return []

        query_tokens = self.tokenizer.tokenize(query)
        if not query_tokens:
            return []

        # Expand tokens and enforce minimum-match
        expanded_tokens: list[str] = []
        unique_query = list(dict.fromkeys(query_tokens))
        hits = 0
        for token in unique_query:
            expanded = self._expand_token(token)
            if expanded:
                hits += 1
            expanded_tokens.extend(expanded)

        min_match = max(1, int(len(unique_query) * self.min_should_match))
        if hits < min_match:
            return []

        if not expanded_tokens:
            return []

        scores = self.scorer.score(expanded_tokens)
        if not scores:
            return []

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_k]


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
