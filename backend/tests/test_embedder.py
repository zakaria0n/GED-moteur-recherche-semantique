"""Tests unitaires pour la generation d'embeddings SBERT."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.search.embedder import (
    DEFAULT_MODEL_NAME,
    embed_query,
    embed_texts,
    load_embedding_model,
)


@pytest.fixture(scope="module")
def model():
    """Charge le modele SBERT une seule fois pour tous les tests du module."""
    return load_embedding_model()


class TestLoadModel:
    """Tests pour le chargement du modele."""

    def test_default_model_loads(self, model):
        assert model is not None

    def test_model_name(self):
        assert "multilingual" in DEFAULT_MODEL_NAME.lower() or "miniLM" in DEFAULT_MODEL_NAME


class TestEmbedTexts:
    """Tests pour embed_texts."""

    def test_output_shape(self, model):
        texts = ["bonjour le monde", "contrat de travail"]
        vectors = embed_texts(texts, model)
        assert vectors.shape == (2, 384)

    def test_empty_raises(self, model):
        with pytest.raises(ValueError, match="Aucun texte"):
            embed_texts([], model)

    def test_single_text(self, model):
        vectors = embed_texts(["test"], model)
        assert vectors.shape == (1, 384)

    def test_normalized(self, model):
        """Les vecteurs doivent etre L2-normalises (norme ≈ 1.0)."""
        vectors = embed_texts(["bonjour", "monde"], model)
        norms = np.linalg.norm(vectors, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)

    def test_similar_texts_close(self, model):
        """Des textes similaires devraient avoir une cosine proche de 1."""
        v1 = embed_texts(["contrat de travail"], model)
        v2 = embed_texts(["contrat d'embauche"], model)
        cosine = float(np.dot(v1[0], v2[0]))
        assert cosine > 0.7, f"Cosine trop faible: {cosine}"

    def test_different_texts_distant(self, model):
        """Des textes differs devraient avoir une cosine plus faible."""
        v1 = embed_texts(["contrat de travail"], model)
        v2 = embed_texts(["Recette de cuisine au four"], model)
        cosine = float(np.dot(v1[0], v2[0]))
        assert cosine < 0.5, f"Cosine trop elevee: {cosine}"


class TestEmbedQuery:
    """Tests pour embed_query."""

    def test_output_shape(self, model):
        vector = embed_query("test query", model)
        assert vector.shape == (384,)

    def test_empty_raises(self, model):
        with pytest.raises(ValueError, match="La requete est vide"):
            embed_query("", model)

    def test_whitespace_only_raises(self, model):
        with pytest.raises(ValueError, match="La requete est vide"):
            embed_query("   ", model)

    def test_normalized(self, model):
        vector = embed_query("bonjour", model)
        norm = np.linalg.norm(vector)
        assert abs(norm - 1.0) < 1e-5, f"Norme non normalisee: {norm}"

    def test_consistency_with_embed_texts(self, model):
        """embed_query("x") devrait etre identique a embed_texts(["x"])[0]."""
        query = "contrat de travail"
        v_query = embed_query(query, model)
        v_texts = embed_texts([query], model)[0]
        np.testing.assert_allclose(v_query, v_texts, atol=1e-6)
