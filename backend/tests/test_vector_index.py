"""Tests unitaires pour l'index vectoriel FAISS."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.search.vector_index import (
    create_faiss_index,
    search_in_index,
)


class TestCreateFaissIndex:
    """Tests pour la creation d'index FAISS."""

    def test_basic_creation(self):
        vectors = np.random.randn(10, 384).astype("float32")
        index = create_faiss_index(vectors)
        assert index.ntotal == 10

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Aucun vecteur"):
            create_faiss_index(np.array([], dtype="float32").reshape(0, 0))

    def test_vectors_normalized_in_index(self):
        """Les vecteurs inseres doivent etre L2-normalises."""
        vectors = np.random.randn(5, 384).astype("float32")
        index = create_faiss_index(vectors)
        # Recuperer les vecteurs de l'index
        stored = np.array(index.reconstruct_n(0, index.ntotal))
        norms = np.linalg.norm(stored, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)

    def test_single_vector(self):
        vectors = np.random.randn(1, 384).astype("float32")
        index = create_faiss_index(vectors)
        assert index.ntotal == 1


class TestSearchInIndex:
    """Tests pour la recherche dans un index FAISS."""

    def test_basic_search(self):
        vectors = np.random.randn(10, 384).astype("float32")
        index = create_faiss_index(vectors)
        query = np.random.randn(384).astype("float32")
        positions, scores = search_in_index(index, query, top_k=3)
        assert len(positions) == 3
        assert len(scores) == 3
        # Les positions doivent etre valides
        assert all(0 <= p < 10 for p in positions)

    def test_scores_in_valid_range(self):
        """Les scores (cosinus via IP de vecteurs normalises) doivent etre dans [-1, 1]."""
        vectors = np.random.randn(20, 384).astype("float32")
        index = create_faiss_index(vectors)
        query = np.random.randn(384).astype("float32")
        _, scores = search_in_index(index, query, top_k=20)
        assert all(-1.0 <= s <= 1.0 + 1e-5 for s in scores), (
            f"Scores hors range [-1, 1]: {scores}"
        )

    def test_top_k_exceeds_index(self):
        """top_k plus grand que le nombre de vecteurs ne doit pas planter."""
        vectors = np.random.randn(3, 384).astype("float32")
        index = create_faiss_index(vectors)
        query = np.random.randn(384).astype("float32")
        positions, scores = search_in_index(index, query, top_k=10)
        assert len(positions) == 10
        # Les positionsmanquantes sont -1
        assert all(p == -1 or 0 <= p < 3 for p in positions)

    def test_exact_match_score_near_one(self):
        """Un vecteur identique a la requete devrait donner un cosinus ~1.0."""
        vector = np.random.randn(384).astype("float32")
        # Normaliser pour simuler le comportement du pipeline
        vector_norm = vector / np.linalg.norm(vector)
        vectors = vector_norm.reshape(1, 384)
        index = create_faiss_index(vectors)
        # Rechercher avec le meme vecteur
        positions, scores = search_in_index(index, vector, top_k=1)
        assert positions[0] == 0
        assert scores[0] > 0.99, f"Score attendu > 0.99, obtenu: {scores[0]}"

    def test_dissimilar_vectors_low_score(self):
        """Des vecteurs orthogonaux devraient avoir un cosinus proche de 0."""
        v1 = np.zeros(384, dtype="float32")
        v1[0] = 1.0
        v2 = np.zeros(384, dtype="float32")
        v2[1] = 1.0
        vectors = np.stack([v1, v2])
        index = create_faiss_index(vectors)
        _, scores = search_in_index(index, v1, top_k=2)
        # Le premier score devrait etre ~1.0 (meme vecteur)
        assert scores[0] > 0.99
        # Le deuxieme devrait etre ~0.0 (orthogonal)
        assert abs(scores[1]) < 0.01
