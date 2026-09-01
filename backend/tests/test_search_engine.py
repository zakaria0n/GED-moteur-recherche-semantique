"""Tests unitaires pour les utilitaires du moteur de recherche."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.search.search_engine import (
    build_chunks,
    build_text_preview,
    category_of,
    chunk_text,
    is_supported_document,
)


# --- Tests chunk_text ---


class TestChunkText:
    def test_short_text_single_chunk(self):
        """Un texte court (<= CHUNK_SIZE) ne doit pas etre decoupe."""
        text = "Bonjour, ceci est un texte court."
        chunks = chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_empty_text(self):
        chunks = chunk_text("")
        assert chunks == []

    def test_whitespace_only(self):
        chunks = chunk_text("   \n  \t  ")
        assert chunks == []

    def test_longer_text_multiple_chunks(self):
        """Un texte long doit etre decoupe en plusieurs chunks."""
        text = "Phrase test. " * 200  # ~2600 chars
        chunks = chunk_text(text)
        assert len(chunks) > 1
        # Chaque chunk ne doit pas depasser trop CHUNK_SIZE + marge
        for chunk in chunks:
            assert len(chunk) <= 1200  # marge pour les coupures de ligne

    def test_chunks_cover_full_text(self):
        """L'union des chunks doit couvrir le texte original."""
        text = "Premiere partie. Deuxieme partie. Troisieme partie. " * 100
        chunks = chunk_text(text)
        joined = " ".join(chunks)
        # Tous les mots importants doivent etre presents
        assert "Premiere" in joined
        assert "Troisieme" in joined


# --- Tests build_chunks ---


class TestBuildChunks:
    def test_basic(self):
        documents = [
            {"text": "Premier document avec du contenu.", "file_name": "doc1.pdf"},
            {"text": "Second document avec du contenu.", "file_name": "doc2.pdf"},
        ]
        chunks = build_chunks(documents)
        assert len(chunks) >= 2
        # Chaque chunk doit etre lie a son document
        for chunk in chunks:
            assert "document" in chunk
            assert "text" in chunk

    def test_documents_preserved(self):
        doc = {"text": "Contenu unique.", "file_name": "test.pdf", "path": "/test.pdf"}
        chunks = build_chunks([doc])
        assert len(chunks) >= 1
        assert chunks[0]["document"] == doc


# --- Tests category_of ---


class TestCategoryOf:
    def test_subdirectory(self):
        assert category_of("Administratif/acte_naissance.pdf") == "Administratif"

    def test_deep_path(self):
        assert category_of("Banque/depots/rib.pdf") == "Banque"

    def test_root_file(self):
        assert category_of("loose_file.pdf") == "_root"

    def test_backslash_path(self):
        assert category_of("Contrats\\cdi.pdf") == "Contrats"


# --- Tests build_text_preview ---


class TestBuildTextPreview:
    def test_basic(self):
        text = "Le contrat de travail a duree indeterminee est conclu entre les parties."
        preview = build_text_preview(text, "contrat travail")
        assert "contrat" in preview.lower() or "travail" in preview.lower()

    def test_empty_text(self):
        assert build_text_preview("", "query") == ""

    def test_no_match_starts_from_beginning(self):
        text = "Document sans rapport avec la requete."
        preview = build_text_preview(text, "zebre girafe")
        assert len(preview) > 0

    def test_max_length_respected(self):
        text = "Mot. " * 500
        preview = build_text_preview(text, "mot", max_length=100)
        assert len(preview) <= 120  # marge pour "..." prefix/suffix

    def test_ellipsis_prefix(self):
        text = "Debut. " * 50 + "Mot cible important. " + "Fin. " * 50
        preview = build_text_preview(text, "cible", max_length=50)
        assert preview.startswith("…") or "Mot cible" in preview


# --- Tests is_supported_document ---


class TestIsSupportedDocument:
    def test_pdf(self):
        assert is_supported_document("doc.pdf")
        assert is_supported_document("DOC.PDF")

    def test_image(self):
        assert is_supported_document("photo.jpg")
        assert is_supported_document("scan.png")
        assert is_supported_document("doc.tiff")

    def test_word(self):
        assert is_supported_document("rapport.docx")

    def test_excel(self):
        assert is_supported_document("tableur.xlsx")

    def test_powerpoint(self):
        assert is_supported_document("presentation.pptx")

    def test_gif(self):
        assert is_supported_document("animation.gif")

    def test_unsupported(self):
        assert not is_supported_document("script.py")
        assert not is_supported_document("video.mp4")
        assert not is_supported_document("archive.zip")
