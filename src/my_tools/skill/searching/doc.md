# Search Implementation Plan

## 1. Architecture

Dual strategy: **BM25 + N-gram** for CJK and code, **Levenshtein Automaton** for Latin text.

| Component | Role |
|-----------|------|
| N-gram tokenizer | Character-level fuzzy matching unit |
| BM25 scorer | Relevance ranking via IDF + term frequency |
| Levenshtein automaton | Query-time fuzzy expansion for Latin tokens |
| Inverted index | N-gram → doc list + frequency |

---

## 2. Index Pipeline

```
Raw doc → Normalize (lower, unicode NFKC) → Tokenize → Filter stop n-grams → Build inverted index
```

1. **N-gram generation**
   - CJK: `n=2` (bigram), fallback `n=3` for mixed content
   - Latin: optional word-level tokenization + character n-gram fallback
   - Output: overlapping substrings with position + frequency

2. **Stop n-gram filter**
   - Build frequency histogram across corpus
   - Drop n-grams appearing in >50% of docs
   - Drop pure punctuation n-grams

3. **Index storage**
   - Term dictionary: n-gram → (doc_freq, posting_ptr)
   - Postings: doc_id → [term_freq, positions...] per n-gram
   - Store avg document length (in n-gram count)

---

## 3. Query Pipeline

```
Query → Normalize → Tokenize → Fetch postings → Score BM25 → Rank → Return top-k
```

1. Tokenize query identically to indexing
2. For each query n-gram:
   - Load postings from inverted index
   - Skip if n-gram not in dictionary
3. Accumulate BM25 score per candidate doc:
   ```
   score = Σ IDF(q) * tf(q,d) * (k1+1) / (tf(q,d) + k1 * (1 - b + b * |d|/avgdl))
   ```
   - `k1 = 1.2`, `b = 0.75` (default)
   - `IDF = ln((N - n(q) + 0.5) / (n(q) + 0.5))`
4. Return top-k by score

---

## 4. Latin Text: Fuzzy Expansion

For Latin/English tokens, apply Levenshtein automaton before BM25:

1. Build Damerau-Levenshtein automaton for token with `fuzziness ≤ 2`
   - `AUTO` mode: 0-2 chars → 0, 3-5 → 1, >5 → 2
2. Walk term dictionary with automaton, collect up to `max_expansions = 50`
3. Set `prefix_length = 1` to prune branch factor
4. Expand query token to matched terms, execute standard BM25 over expanded set

---

## 5. Performance Optimizations

| Technique | Implementation |
|-----------|---------------|
| Minimum match | Require `m` of `n` query n-grams to hit before scoring (e.g. `m = n/2`) |
| WAND / Block-Max WAND | Skip low-scoring postings during accumulation |
| Index pruning | Drop n-grams with df > threshold at build time |
| In-memory hot index | Cache frequently accessed n-gram postings |
| Batch scoring | Process multiple docs per posting list to improve cache locality |

---

## 6. Parameter Table

| Parameter | Value | Notes |
|-----------|-------|-------|
| `n` | 2 (CJK), 3 (mixed) | Bigram for Chinese; trigram for code/English fallback |
| `k1` | 1.2 | Term frequency saturation |
| `b` | 0.75 | Length normalization |
| `fuzziness` | AUTO | Per-token edit distance limit |
| `max_expansions` | 50 | Cap on fuzzy-expanded terms |
| `prefix_length` | 1 | Exact prefix before fuzzy matching |
| `min_should_match` | 50% | Fraction of query n-grams required |

---

## 7. Deliverables

1. `NgramTokenizer` — overlapping n-gram generator
2. `InvertedIndex` — build + persist + load
3. `BM25Scorer` — score(query_ngrams, candidate_docs)
4. `LevenshteinAutomaton` — fuzzy term expansion for Latin
5. `Searcher` — query pipeline orchestrator (normalize → tokenize → score → rank)
6. CLI / API entrypoint for index build and search
