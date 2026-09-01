"""Generation simple des embeddings avec SBERT."""

import numpy as np
from numpy.typing import NDArray
from sentence_transformers import SentenceTransformer


DEFAULT_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Cache des modeles charges (par nom) : evite de recharger plusieurs centaines
# de Mo a chaque synchronisation ou rechargement de l'index.
_LOADED_MODELS: dict[str, SentenceTransformer] = {}


def load_embedding_model(model_name: str = DEFAULT_MODEL_NAME) -> SentenceTransformer:
    cached = _LOADED_MODELS.get(model_name)

    if cached is not None:
        return cached

    try:
        model = SentenceTransformer(model_name)
    except Exception as exc:
        raise ValueError("Impossible de charger le modele SBERT") from exc

    _LOADED_MODELS[model_name] = model

    return model


def embed_texts(texts: list[str], model: SentenceTransformer) -> NDArray[np.float32]:
    if not texts:
        raise ValueError("Aucun texte a encoder")

    try:
        return model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    except Exception as exc:
        raise ValueError("Impossible de generer les embeddings des documents") from exc


def embed_query(query: str, model: SentenceTransformer) -> NDArray[np.float32]:
    if not query or not query.strip():
        raise ValueError("La requete est vide")

    try:
        return model.encode([query], convert_to_numpy=True, normalize_embeddings=True)[0]
    except Exception as exc:
        raise ValueError("Impossible de generer l'embedding de la requete") from exc
