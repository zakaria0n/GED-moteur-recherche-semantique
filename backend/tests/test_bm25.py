"""Tests unitaires pour le scoring BM25 et la tokenisation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.search.bm25 import BM25, tokenize


class TestTokenize:
    """Tests pour la fonction de tokenisation."""

    def test_lowercase(self):
        assert tokenize("HELLO World") == ["hello", "world"]

    def test_accents_preserved(self):
        tokens = tokenize("café résumé")
        assert "café" in tokens
        assert "résumé" in tokens

    def test_short_words_filtered(self):
        tokens = tokenize("je suis un test")
        # "je", "un" font < 2 caracteres et sont filtres
        assert "je" not in tokens
        assert "un" not in tokens
        assert "suis" in tokens
        assert "test" in tokens

    def test_punctuation_removed(self):
        tokens = tokenize("bonjour, monde! (test)")
        assert tokens == ["bonjour", "monde", "test"]

    def test_empty_string(self):
        assert tokenize("") == []

    def test_numbers_kept(self):
        tokens = tokenize("article 42 ref-123")
        assert "42" in tokens
        assert "ref" in tokens
        assert "123" in tokens


class TestBM25:
    """Tests pour le scoring BM25."""

    def test_exact_match_top_ranked(self):
        corpus = [
            tokenize("contrat de travail salarie employeur"),
            tokenize("facture client montant total"),
            tokenize("bulletin de paie salaire mensuel"),
        ]
        bm25 = BM25(corpus)
        scores = bm25.get_scores(tokenize("contrat"))
        # Le document 0 contient "contrat" -> score > 0
        assert scores[0] > 0
        assert scores[1] == 0  # "facture" ne contient pas "contrat"
        assert scores[2] == 0  # "bulletin" ne contient pas "contrat"

    def test_no_match_zero_score(self):
        corpus = [
            tokenize("bonjour monde"),
            tokenize("hello world"),
        ]
        bm25 = BM25(corpus)
        scores = bm25.get_scores(tokenize("zebre girafe"))
        assert all(s == 0 for s in scores)

    def test_single_document(self):
        corpus = [tokenize("test unique document")]
        bm25 = BM25(corpus)
        scores = bm25.get_scores(tokenize("test"))
        assert len(scores) == 1
        assert scores[0] > 0

    def test_ranking_order(self):
        corpus = [
            tokenize("chat felin animal domestique"),
            tokenize("chien canide animal compagnie"),
            tokenize("voiture automobile transport route"),
        ]
        bm25 = BM25(corpus)
        scores = bm25.get_scores(tokenize("chat felin"))
        # Document 0 devrait etre premier (contient les deux termes)
        assert scores[0] > scores[1]
        assert scores[0] > scores[2]
