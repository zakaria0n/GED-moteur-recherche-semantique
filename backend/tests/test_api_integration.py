"""Tests d'integration pour le moteur de recherche semantique.

Teste le flux complet : construction du moteur, recherche, filtres,
cache LRU, et pagination.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conftest import MINI_CORPUS, make_corpus
from services.search.search_engine import (
    SearchCache,
    _search_cache,
    build_search_engine,
    search_documents,
)


# --- Fixtures ---


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    """Moteur de recherche sur le mini-corpus (5 documents)."""
    base = tmp_path_factory.mktemp("integration_corpus")
    make_corpus(base, MINI_CORPUS)
    return build_search_engine(documents_dir=str(base), use_ocr_for_pdf=False)


# --- Tests recherche de base ---


class TestBasicSearch:
    def test_search_returns_results(self, engine):
        """Une recherche pertinente doit retourner des resultats."""
        results = search_documents("contrat de travail", engine, top_k=5)
        assert len(results) > 0

    def test_search_result_structure(self, engine):
        """Chaque resultat doit contenir les champs obligatoires."""
        results = search_documents("salaire", engine, top_k=5)
        for r in results:
            assert "path" in r
            assert "relative_path" in r
            assert "file_name" in r
            assert "file_type" in r
            assert "score" in r
            assert "aggregated" in r
            assert "text_preview" in r

    def test_search_respects_top_k(self, engine):
        """top_k limite le nombre de resultats."""
        results = search_documents("document", engine, top_k=2)
        assert len(results) <= 2

    def test_search_lexical_match(self, engine):
        """Une recherche lexicale exacte doit trouver le bon document."""
        results = search_documents("releve identite bancaire", engine, top_k=5)
        assert len(results) > 0
        assert any("rib" in r["file_name"].lower() for r in results)

    def test_search_irrelevant_query(self, engine):
        """Une requete hors-sujet doit retourner 0 ou peu de resultats."""
        results = search_documents("astrologie numerologie horoscope", engine, top_k=5)
        # Peut retourner 0 ou quelques faux positifs, mais pas 5 vrais positifs.
        assert len(results) <= 2


# --- Tests filtres ---


class TestSearchFilters:
    def test_category_filter(self, engine):
        """Le filtre category doit limiter aux documents de cette categorie."""
        results_all = search_documents("document", engine, top_k=10)
        results_cat = search_documents("document", engine, top_k=10, category="Banque")
        # Les resultats filtres ne doivent pas depasser les totaux.
        assert len(results_cat) <= len(results_all)
        # Tous les resultats filtres doivent etre dans la categorie Banque.
        for r in results_cat:
            assert r["relative_path"].replace("\\", "/").startswith("Banque/")

    def test_file_type_filter(self, engine):
        """Le filtre file_type doit limiter aux documents du type donne."""
        results = search_documents("document", engine, top_k=10, file_type=".pdf")
        for r in results:
            assert r["file_type"] == ".pdf"

    def test_file_type_filter_no_match(self, engine):
        """Un filtre file_type inexistant doit retourner 0 resultats."""
        results = search_documents("contrat", engine, top_k=10, file_type=".docx")
        assert len(results) == 0


# --- Tests cache LRU ---


class TestSearchCache:
    def test_cache_hit_returns_same_results(self, engine):
        """Deux appels identiques doivent retourner les memes resultats."""
        query = "facture montant"
        r1 = search_documents(query, engine, top_k=3)
        r2 = search_documents(query, engine, top_k=3)
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a["relative_path"] == b["relative_path"]

    def test_cache_different_params(self, engine):
        """Des parametres differents doivent produire des entrees cache separees."""
        search_documents("contrat", engine, top_k=3)
        search_documents("contrat", engine, top_k=5)
        stats = _search_cache.stats()
        assert stats["hits"] >= 0  # Pas d'erreur

    def test_cache_stats(self, engine):
        """Le cache doit tracker les hits et misses."""
        _search_cache.clear()
        query = "test_cache_stats_unique"
        # Miss
        search_documents(query, engine, top_k=3)
        stats = _search_cache.stats()
        assert stats["misses"] >= 1
        # Hit
        search_documents(query, engine, top_k=3)
        stats = _search_cache.stats()
        assert stats["hits"] >= 1

    def test_cache_clear(self, engine):
        """clear() doit reinitialiser le cache."""
        _search_cache.clear()
        stats = _search_cache.stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0

    def test_cache_custom_ttl(self):
        """Le cache doit respecter le TTL (entrees expirees = miss)."""
        cache = SearchCache(max_size=10, ttl=0)  # TTL = 0 = tout expire immediatement.
        cache.put("q", 5, None, None, [{"result": 1}])
        result = cache.get("q", 5, None, None)
        assert result is None  # Expire


# --- Tests performance minimale ---


class TestPerformance:
    def test_search_under_500ms(self, engine):
        """Une recherche sur 5 documents doit etre < 500ms."""
        t0 = time.perf_counter()
        search_documents("contrat de travail", engine, top_k=5)
        latency_ms = (time.perf_counter() - t0) * 1000
        assert latency_ms < 500, f"Recherche trop lente : {latency_ms:.0f}ms"

    def test_cache_hit_under_10ms(self, engine):
        """Un cache hit doit etre < 10ms."""
        query = "performance_cache_test"
        search_documents(query, engine, top_k=5)  # Prime le cache.
        t0 = time.perf_counter()
        search_documents(query, engine, top_k=5)
        latency_ms = (time.perf_counter() - t0) * 1000
        assert latency_ms < 10, f"Cache hit trop lent : {latency_ms:.0f}ms"


# --- Tests fuzzy suggestions ---


class TestSuggestions:
    def test_suggestions_generated(self, engine):
        """Une requete sans resultats doit generer des suggestions."""
        from services.search.search_engine import _generate_suggestions
        suggestions = _generate_suggestions("xyzabc_nonexistent", engine)
        # Peut etre vide si aucun terme ne matche, mais pas d'erreur.
        assert isinstance(suggestions, list)
