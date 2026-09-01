"""Index vectoriel FAISS simple pour la recherche semantique.

Sharding : chaque categorie (dossier top-level) a son propre fichier d'index
et son fichier meta (chunk_relative_paths). Un manifeste shards.json decrit
l'ensemble des shards pour le rechargement au demarrage.
"""

import json
from pathlib import Path

import faiss
import numpy as np

from config import FAISS_INDEX_PATH, FAISS_INDEX_TYPE, HNSW_EF_SEARCH, HNSW_M, INDEX_DIR


def create_faiss_index(vectors):
    matrix = np.array(vectors, dtype="float32")

    if matrix.size == 0:
        raise ValueError("Aucun vecteur a indexer")

    faiss.normalize_L2(matrix)
    dimension = matrix.shape[1]
    num_vectors = matrix.shape[0]

    # "hnsw" : recherche approximative sous-lineaire, scale a 10000+ vecteurs.
    # Pour les petits shards (< 2 * HNSW_M), HNSW ne peut pas construire de
    # graphe fiable (pas assez de voisins), on bascule sur le Flat exact.
    if FAISS_INDEX_TYPE == "hnsw" and num_vectors > HNSW_M * 2:
        # METRIC_INNER_PRODUCT obligatoire : sur vecteurs normalises, le score
        # renvoye est alors le cosinus (<= 1). Le defaut du constructeur est
        # METRIC_L2, qui renvoie des DISTANCES euclidiennes (0-4) — incompatibles
        # avec le seuil de pertinence et le pourcentage affiche.
        index = faiss.IndexHNSWFlat(dimension, HNSW_M, faiss.METRIC_INNER_PRODUCT)
        index.hnsw.efSearch = HNSW_EF_SEARCH
    else:
        index = faiss.IndexFlatIP(dimension)

    index.add(matrix)

    return index


def search_in_index(index, query_vector, top_k=5):
    query = np.array([query_vector], dtype="float32")
    faiss.normalize_L2(query)

    scores, positions = index.search(query, top_k)

    return positions[0].tolist(), scores[0].tolist()


def _meta_path_for(index_path):
    path = Path(index_path)
    return path.parent / (path.name + ".meta.json")


def save_index(index, index_path, metadata=None):
    path = Path(index_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(path))

    # Metadonnees d'alignement (ordre des passages -> documents) : on ne
    # depend plus de l'ordre d'insertion en base pour reassocier un vecteur
    # a son document lors du rechargement.
    if metadata is not None:
        meta_path = _meta_path_for(path)
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump(metadata, handle)


def load_index(index_path, with_metadata=False):
    path = Path(index_path)

    if not path.is_file():
        raise FileNotFoundError("Index FAISS introuvable")

    index = faiss.read_index(str(path))

    if not with_metadata:
        return index

    meta_path = _meta_path_for(path)
    metadata = None

    if meta_path.is_file():
        with open(meta_path, encoding="utf-8") as handle:
            metadata = json.load(handle)

    return index, metadata


def _sanitize_category(category):
    """Nom de fichier sur le systeme (pas de / ou caractere special)."""

    return "".join(c if c.isalnum() or c in "-_" else "_" for c in category)


def shard_index_path(index_dir, category):
    """Chemin du fichier FAISS pour un shard (une categorie)."""

    safe = _sanitize_category(category)
    return Path(index_dir) / f"documents_{safe}.faiss"


def _shard_meta_path(index_dir, category):
    """Chemin du fichier meta (chunk_relative_paths) d'un shard."""

    return shard_index_path(index_dir, category).parent / (
        shard_index_path(index_dir, category).name + ".meta.json"
    )


def save_shard_index(index, index_dir, category, chunk_relative_paths, model_name):
    """Sauvegarde un shard : index FAISS + meta."""

    index_file = shard_index_path(index_dir, category)
    index_file.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_file))

    meta_path = _shard_meta_path(index_dir, category)
    with open(meta_path, "w", encoding="utf-8") as handle:
        json.dump({"chunk_relative_paths": chunk_relative_paths, "model_name": model_name}, handle)


def load_shard_index(index_dir, category):
    """Charge un shard : renvoie (index, meta). Leve FileNotFoundError si absent."""

    index_file = shard_index_path(index_dir, category)

    if not index_file.is_file():
        raise FileNotFoundError(f"Index FAISS du shard '{category}' introuvable: {index_file}")

    index = faiss.read_index(str(index_file))
    meta_path = _shard_meta_path(index_dir, category)
    metadata = None

    if meta_path.is_file():
        with open(meta_path, encoding="utf-8") as handle:
            metadata = json.load(handle)

    return index, metadata


def save_shards_manifest(index_dir, model_name, categories):
    """Sauvegarde la liste des shards actifs pour le rechargement."""

    manifest_path = Path(index_dir) / "shards.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump({"model_name": model_name, "categories": sorted(categories)}, handle)


def load_shards_manifest(index_dir):
    """Charge le manifeste des shards ; renvoie le dict ou None si absent."""

    manifest_path = Path(index_dir) / "shards.json"

    if not manifest_path.is_file():
        return None

    with open(manifest_path, encoding="utf-8") as handle:
        return json.load(handle)


def delete_shard_files(index_dir, category):
    """Supprime les fichiers index + meta d'un shard."""

    for path in [shard_index_path(index_dir, category), _shard_meta_path(index_dir, category)]:
        if path.is_file():
            path.unlink()
