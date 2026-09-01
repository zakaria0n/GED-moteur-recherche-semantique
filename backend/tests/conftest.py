"""Fixtures partagees pour les tests du moteur de recherche.

Fournit un corpus temporaire de PDFs generes via reportlab, un moteur
pre-construit, et des helpers pour creer des fichiers de test.
"""

import sys
from pathlib import Path

# Permet d'executer les tests depuis le repertoire backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from services.search.search_engine import (
    build_chunks,
    build_search_engine,
    chunk_text,
    search_documents,
)


# --- Helpers ---


def make_pdf(path, text):
    """Genere un PDF contenant le texte donne (pour les tests)."""
    pdf = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    for line in text.split("\n"):
        pdf.drawString(50, y, line)
        y -= 20
    pdf.save()


def make_corpus(base_dir, documents):
    """Cree un corpus de PDFs a partir d'une liste (relative_path, text)."""
    for relative_path, text in documents:
        document_path = base_dir / relative_path
        document_path.parent.mkdir(parents=True, exist_ok=True)
        make_pdf(document_path, text)


# --- Mini-corpus pour les tests unitaires ---


MINI_CORPUS = [
    ("Administratif/acte_naissance.pdf",
     "Acte de naissance officiel. Ce document d'etat civil certifie la naissance "
     "de la personne a la mairie. Il mentionne le nom, la date et le lieu de naissance."),
    ("Administratif/attestation_travail.pdf",
     "Attestation de travail. L'employeur certifie que le salarie occupe un poste "
     "et perceit un salaire au sein de l'entreprise."),
    ("Banque/rib.pdf",
     "Releve d'identite bancaire. Ce document indique l'IBAN et la domiciliation du "
     "compte bancaire du titulaire."),
    ("Contrats/cdi.pdf",
     "Contrat a duree indeterminee CDI. Ce contrat d'embauche ne fixe pas de fin et "
     "prevoit une periode d'essai."),
    ("Factures/facture_client.pdf",
     "Facture client. Ce document commercial detaille les services factures et le montant "
     "total a regler par le client."),
]


# --- Fixtures pytest ---


@pytest.fixture(scope="module")
def mini_engine(tmp_path_factory):
    """Moteur de recherche pre-construit sur le mini-corpus (5 documents)."""
    base = tmp_path_factory.mktemp("mini_corpus")
    make_corpus(base, MINI_CORPUS)
    return build_search_engine(documents_dir=str(base), use_ocr_for_pdf=False)


@pytest.fixture(scope="module")
def mini_chunks():
    """Chunks du mini-corpus (sans moteur, juste le text chunking)."""
    all_chunks = []
    for _, text in MINI_CORPUS:
        all_chunks.extend(chunk_text(text))
    return all_chunks
