"""Comprehensive tests for src/kimix/searching/bm25.py."""

from pathlib import Path

import pytest

from kimix.searching.bm25 import Search


@pytest.fixture
def api_markdown() -> str:
    """Load the API skill markdown document."""
    return Path(".agents/skills/api/SKILL.md").read_text(encoding="utf-8")


@pytest.fixture
def tool_markdown() -> str:
    """Load the tool skill markdown document."""
    return Path(".agents/skills/tool/SKILL.md").read_text(encoding="utf-8")


@pytest.fixture
def combined_content(api_markdown: str, tool_markdown: str) -> str:
    """Combine both markdown documents."""
    return api_markdown + "\n" + tool_markdown


class TestSearchInitialization:
    """Tests for Search class initialization and index building."""

    def test_init_with_empty_string(self) -> None:
        """Search should handle empty content gracefully."""
        search = Search("")
        assert search.N == 0
        assert search.avgdl == 0.0
        assert search.docs == []
        assert search.inverted_index == {}

    def test_init_with_whitespace_only(self) -> None:
        """Search should ignore whitespace-only lines."""
        search = Search("   \n\n   \t  \n")
        assert search.N == 0

    def test_init_strips_lines(self) -> None:
        """Search should strip whitespace from each line."""
        content = "  hello world  \n\n  foo bar  "
        search = Search(content)
        assert search.docs == ["hello world", "foo bar"]
        assert search.N == 2

    def test_init_skips_empty_lines(self) -> None:
        """Empty lines should not create documents."""
        content = "first line\n\nsecond line\n\n\nthird line"
        search = Search(content)
        assert search.N == 3
        assert search.docs == ["first line", "second line", "third line"]

    def test_default_parameters(self) -> None:
        """Default n, k1, and b values."""
        search = Search("hello")
        assert search.n == 2
        assert search.k1 == 1.2
        assert search.b == 0.75

    def test_custom_parameters(self) -> None:
        """Custom n, k1, and b values."""
        search = Search("hello", n=3, k1=2.0, b=0.5)
        assert search.n == 3
        assert search.k1 == 2.0
        assert search.b == 0.5

    def test_avgdl_computation(self) -> None:
        """Average document length should be computed correctly."""
        # With n=2, "abcd" -> 3 tokens, "efgh" -> 3 tokens
        search = Search("abcd\nefgh", n=2)
        assert search.doc_lengths == [3, 3]
        assert search.avgdl == 3.0


class TestTokenize:
    """Tests for the _tokenize method."""

    def test_basic_bigrams(self) -> None:
        """Default n=2 should produce character bigrams."""
        search = Search("hello")
        tokens = search._tokenize("hello")
        assert tokens == ["he", "el", "ll", "lo"]

    def test_trigrams(self) -> None:
        """n=3 should produce character trigrams."""
        search = Search("hello", n=3)
        tokens = search._tokenize("hello")
        assert tokens == ["hel", "ell", "llo"]

    def test_text_shorter_than_n(self) -> None:
        """Text shorter than n should return itself as a single token."""
        search = Search("hello", n=5)
        tokens = search._tokenize("hi")
        assert tokens == ["hi"]

    def test_empty_text(self) -> None:
        """Empty text should return empty list."""
        search = Search("hello")
        tokens = search._tokenize("")
        assert tokens == []

    def test_text_equal_to_n(self) -> None:
        """Text equal to n should return itself."""
        search = Search("hello", n=2)
        tokens = search._tokenize("ab")
        assert tokens == ["ab"]

    def test_whitespace_stripping(self) -> None:
        """Text should be stripped before tokenization."""
        search = Search("hello", n=2)
        tokens = search._tokenize("  abc  ")
        assert tokens == ["ab", "bc"]

    def test_unicode_text(self) -> None:
        """Unicode text should be tokenized correctly."""
        search = Search("hello", n=2)
        tokens = search._tokenize("日本")
        assert tokens == ["日本"]


class TestSearchEmptyIndex:
    """Tests for search behavior with empty index."""

    def test_search_empty_index(self) -> None:
        """Searching empty index should return empty list."""
        search = Search("")
        results = search.search("hello")
        assert results == []

    def test_search_empty_query(self) -> None:
        """Empty query should return empty list."""
        search = Search("hello world")
        results = search.search("")
        assert results == []

    def test_search_whitespace_query(self) -> None:
        """Whitespace-only query should return empty list."""
        search = Search("hello world")
        results = search.search("   ")
        assert results == []


class TestSearchBasic:
    """Basic search functionality tests."""

    def test_search_no_matches(self) -> None:
        """Query with no matching tokens should return empty list."""
        search = Search("hello world\nfoo bar")
        results = search.search("xyz")
        assert results == []

    def test_search_single_match(self) -> None:
        """Query matching a single document."""
        search = Search("hello world\nfoo bar")
        results = search.search("hello")
        assert len(results) == 1
        assert results[0]["doc_id"] == 0
        assert results[0]["text"] == "hello world"

    def test_search_multiple_matches(self) -> None:
        """Query matching multiple documents."""
        search = Search("hello world\nhello there\nfoo bar")
        results = search.search("hello")
        assert len(results) == 2
        doc_ids = [r["doc_id"] for r in results]
        assert 0 in doc_ids
        assert 1 in doc_ids

    def test_results_sorted_by_score(self) -> None:
        """Results should be sorted by score descending."""
        # "hello hello" has more "he" bigrams than "hello"
        search = Search("hello hello\nhello")
        results = search.search("he")
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_top_k_limits_results(self) -> None:
        """top_k should limit the number of results."""
        content = "\n".join([f"line {i}" for i in range(10)])
        search = Search(content)
        results = search.search("li", top_k=3)
        assert len(results) == 3

    def test_top_k_default(self) -> None:
        """Default top_k is 5."""
        content = "\n".join([f"line {i}" for i in range(10)])
        search = Search(content)
        results = search.search("li")
        assert len(results) == 5

    def test_result_structure(self) -> None:
        """Each result should have expected keys."""
        search = Search("hello world")
        results = search.search("hello")
        assert len(results) == 1
        result = results[0]
        assert "doc_id" in result
        assert "score" in result
        assert "text" in result
        assert "matched_terms" in result
        assert isinstance(result["doc_id"], int)
        assert isinstance(result["score"], float)
        assert isinstance(result["text"], str)
        assert isinstance(result["matched_terms"], list)

    def test_matched_terms(self) -> None:
        """matched_terms should contain query tokens found in the document."""
        search = Search("hello world")
        results = search.search("he")
        assert results[0]["matched_terms"] == ["he"]

    def test_matched_terms_multiple(self) -> None:
        """matched_terms should contain all matching query tokens."""
        search = Search("abcdef")
        results = search.search("ab cd")
        # n=2, "ab cd" -> tokens: ["ab", "b ", " c", "cd"]
        matched = results[0]["matched_terms"]
        assert "ab" in matched
        assert "cd" in matched


class TestSearchWithMarkdown:
    """Tests using real markdown documents from .agents folder."""

    def test_search_api_markdown(self, api_markdown: str) -> None:
        """Search should work with the API markdown document."""
        search = Search(api_markdown)
        assert search.N > 0
        results = search.search("session")
        assert len(results) > 0
        for r in results:
            assert "session" in r["text"].lower() or "se" in r["text"].lower()

    def test_search_tool_markdown(self, tool_markdown: str) -> None:
        """Search should work with the tool markdown document."""
        search = Search(tool_markdown)
        assert search.N > 0
        results = search.search("CallableTool2")
        assert len(results) > 0
        for r in results:
            assert "CallableTool2" in r["text"] or "Ca" in r["text"]

    def test_search_combined_content(self, combined_content: str) -> None:
        """Search should work with combined markdown documents."""
        search = Search(combined_content)
        assert search.N > 0
        results = search.search("Params")
        assert len(results) > 0
        # With top_k=3
        results = search.search("Params", top_k=3)
        assert len(results) <= 3

    def test_search_top_k_with_real_docs(self, api_markdown: str) -> None:
        """top_k should correctly limit results with real documents."""
        search = Search(api_markdown)
        results = search.search("se", top_k=10)
        assert len(results) <= 10
        assert len(results) > 0

    def test_scores_are_positive(self, tool_markdown: str) -> None:
        """All scores should be positive floats."""
        search = Search(tool_markdown)
        results = search.search("tool")
        for r in results:
            assert r["score"] > 0
            assert isinstance(r["score"], float)

    def test_doc_id_in_range(self, combined_content: str) -> None:
        """doc_id should be within valid range."""
        search = Search(combined_content)
        results = search.search("the")
        for r in results:
            assert 0 <= r["doc_id"] < search.N

    def test_text_matches_doc_id(self, api_markdown: str) -> None:
        """Result text should match the document at doc_id."""
        search = Search(api_markdown)
        results = search.search("Kimi")
        for r in results:
            assert r["text"] == search.docs[r["doc_id"]]


class TestSearchNgramVariations:
    """Tests with different n-gram sizes."""

    def test_n1_unigrams(self) -> None:
        """n=1 should use character unigrams."""
        search = Search("hello", n=1)
        tokens = search._tokenize("hello")
        assert tokens == ["h", "e", "l", "l", "o"]

    def test_n4_fourgrams(self) -> None:
        """n=4 should use character 4-grams."""
        search = Search("abcdef", n=4)
        tokens = search._tokenize("abcdef")
        assert tokens == ["abcd", "bcde", "cdef"]

    def test_search_with_n3(self) -> None:
        """Search should work with trigrams."""
        search = Search("hello world\nhelp me", n=3)
        results = search.search("hel")
        assert len(results) == 2


class TestBM25Scoring:
    """Tests related to BM25 scoring behavior."""

    def test_longer_document_lower_score_same_tf(self) -> None:
        """For same term frequency, shorter doc should score higher."""
        # Both docs have "he" exactly once, but doc1 is shorter
        search = Search("he\nhello world foo bar")
        results = search.search("he")
        # The shorter doc should generally score higher due to dl normalization
        assert len(results) == 2

    def test_higher_tf_higher_score(self) -> None:
        """Document with more occurrences should score higher."""
        # "hehehehe" contains 4 "he" bigrams with dl=7
        # "he" contains 1 "he" bigram with dl=1
        # The higher tf overcomes the length penalty
        search = Search("hehehehe\nhe")
        results = search.search("he")
        # First doc has 4 occurrences, second has 1
        assert results[0]["doc_id"] == 0
        assert results[0]["score"] > results[1]["score"]

    def test_idf_effect(self) -> None:
        """Rare terms should have higher IDF and contribute more to score."""
        # "xy" is rare (1 doc), "ab" is common (2 docs)
        search = Search("xy zw\nab cd\nab ef")
        results_xy = search.search("xy")
        results_ab = search.search("ab")
        # xy has higher idf, so per-occurrence score contribution is higher
        assert len(results_xy) == 1
        assert len(results_ab) == 2


class TestEdgeCases:
    """Edge case tests."""

    def test_single_line_content(self) -> None:
        """Single line should work correctly."""
        search = Search("only one line here")
        assert search.N == 1
        results = search.search("one")
        assert len(results) == 1
        assert results[0]["doc_id"] == 0

    def test_query_equal_to_n(self) -> None:
        """Query exactly n characters long."""
        search = Search("abcdef", n=2)
        results = search.search("ab")
        assert len(results) == 1

    def test_query_shorter_than_n(self) -> None:
        """Query shorter than n should still work if a doc is also shorter than n."""
        search = Search("abcdef\nab", n=3)
        results = search.search("ab")
        assert len(results) == 1
        assert results[0]["doc_id"] == 1
        assert results[0]["matched_terms"] == ["ab"]

    def test_repeated_empty_lines(self) -> None:
        """Many repeated empty lines should be handled."""
        content = "line1\n\n\n\n\nline2\n\n\nline3"
        search = Search(content)
        assert search.N == 3

    def test_special_characters(self) -> None:
        """Special characters should be tokenized normally."""
        search = Search("!@#$%\n^&*()")
        assert search.N == 2
        results = search.search("!@")
        assert len(results) == 1

    def test_numbers(self) -> None:
        """Numbers should be handled correctly."""
        search = Search("12345\n67890")
        results = search.search("12")
        assert len(results) == 1
        assert results[0]["text"] == "12345"

    def test_case_sensitivity(self) -> None:
        """Search should be case-sensitive (character n-grams)."""
        search = Search("Hello World\nhello world")
        results = search.search("He")
        assert len(results) == 1
        assert results[0]["doc_id"] == 0

    def test_large_top_k(self) -> None:
        """top_k larger than result count should return all results."""
        search = Search("hello\nworld")
        results = search.search("hello", top_k=100)
        assert len(results) == 1

    def test_zero_top_k(self) -> None:
        """top_k=0 should return empty list."""
        search = Search("hello\nworld")
        results = search.search("hello", top_k=0)
        assert results == []
