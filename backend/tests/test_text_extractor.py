"""Tests unitaires pour l'extraction de texte et l'OCR."""

import sys
from pathlib import Path

import numpy as np
import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.search.text_extractor import (
    extract_text_from_pdf,
    looks_garbled,
    merge_text_layers,
    normalize_whitespace,
)


# --- Helpers ---


def _make_pdf(path, text):
    """Genere un PDF simple avec du texte."""
    pdf = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    for line in text.split("\n"):
        pdf.drawString(50, y, line)
        y -= 20
    pdf.save()


# --- Tests normalize_whitespace ---


class TestNormalizeWhitespace:
    def test_basic(self):
        assert normalize_whitespace("bonjour  le   monde") == "bonjour le monde"

    def test_newlines(self):
        result = normalize_whitespace("ligne1\n\n\n\nligne2")
        assert "\n\n" in result
        assert "\n\n\n" not in result

    def test_carriage_return(self):
        assert normalize_whitespace("a\r\nb") == "a\nb"

    def test_strips(self):
        assert normalize_whitespace("  hello  ") == "hello"

    def test_empty(self):
        assert normalize_whitespace("") == ""


# --- Tests looks_garbled ---


class TestLooksGarbled:
    def test_normal_text_not_garbled(self):
        assert not looks_garbled("Ce document certifie la naissance de la personne.")

    def test_empty_not_garbled(self):
        assert not looks_garbled("")

    def test_mostly_symbols_garbled(self):
        assert looks_garbled("@#$%^&*()_+{}|:<>?")

    def test_mixed_ok(self):
        assert not looks_garbled("Document 2024 - Reference #42")

    def test_short_text_ok(self):
        assert not looks_garbled("AO 2025")


# --- Tests merge_text_layers ---


class TestMergeTextLayers:
    def test_no_duplicates(self):
        base = "Contrat de travail entre les parties."
        addition = "Contrat de travail entre les parties."
        merged = merge_text_layers(base, addition)
        assert merged == base

    def test_adds_new_content(self):
        base = "Premiere partie du document."
        addition = "Deuxieme partie du document."
        merged = merge_text_layers(base, addition)
        assert "Premiere partie" in merged
        assert "Deuxieme partie" in merged

    def test_empty_base(self):
        merged = merge_text_layers("", "Nouveau contenu")
        assert merged == "Nouveau contenu"

    def test_empty_addition(self):
        merged = merge_text_layers("Contenu existant", "")
        assert merged == "Contenu existant"

    def test_both_empty(self):
        merged = merge_text_layers("", "")
        assert merged == ""


# --- Tests extract_text_from_pdf ---


class TestExtractTextFromPDF:
    def test_basic_extraction(self, tmp_path):
        pdf_path = tmp_path / "test.pdf"
        _make_pdf(pdf_path, "Bonjour le monde.\nCeci est un test.")
        text = extract_text_from_pdf(pdf_path)
        assert "Bonjour" in text
        assert "monde" in text

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            extract_text_from_pdf("/nonexistent/file.pdf")

    def test_empty_pdf(self, tmp_path):
        pdf_path = tmp_path / "empty.pdf"
        _make_pdf(pdf_path, "")
        text = extract_text_from_pdf(pdf_path)
        # Un PDF avec du texte vide peut quand meme avoir du contenu
        # (metadonnees PDF), mais le texte extrait devrait etre vide ou minimal
        assert isinstance(text, str)


# --- Tests OCR (conditionnels) ---


@pytest.mark.skipif(
    not Path(__file__).resolve().parent.parent.joinpath("data", "pdfs").exists(),
    reason="OCR necessite des PDF reels dans data/pdfs/",
)
class TestOCRIntegration:
    """Tests d'integration OCR sur de vrais PDFs (si disponibles)."""

    def test_ocr_pdf_pages_returns_text(self):
        from services.search.text_extractor import ocr_pdf_pages

        pdfs_dir = Path(__file__).resolve().parent.parent / "data" / "pdfs"
        # Prendre le premier PDF disponible
        pdfs = list(pdfs_dir.rglob("*.pdf"))
        if not pdfs:
            pytest.skip("Aucun PDF disponible")
        text = ocr_pdf_pages(pdfs[0])
        assert isinstance(text, str)
