"""20 tests de pertinence : la recherche doit renvoyer le bon PDF en 1ere position.

On genere de vrais PDF (reportlab) dans un dossier temporaire, on construit le
moteur complet (extraction -> chunking -> BM25 + FAISS -> fusion RRF), puis on
verifie que chacune des 20 requetes cible le document attendu en rang 1.

Execution :
    pytest backend/tests/test_search_top1.py
    python backend/tests/test_search_top1.py   # mode autonome
"""

import sys
from pathlib import Path

# Permet d'executer le fichier directement (python tests/test_search_top1.py)
# en plus de pytest.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

import pytest

from services.search.search_engine import build_search_engine, search_documents


# --- Corpus realiste : documents administratifs francais bien distincts ---
CORPUS = [
    ("Administratif/acte_naissance.pdf",
     "Acte de naissance officiel. Ce document d'etat civil certifie la naissance "
     "de la personne a la mairie. Il mentionne le nom, la date et le lieu de naissance."),
    ("Administratif/attestation_domicile.pdf",
     "Attestation de domicile. Ce justificatif de residence prouve l'adresse actuelle "
     "du demandeur aupres des services administratifs."),
    ("Administratif/attestation_travail.pdf",
     "Attestation de travail. L'employeur certifie que le salarie occupe un poste "
     "et perceit un salaire au sein de l'entreprise."),
    ("Administratif/certificat_medical.pdf",
     "Certificat medical. Le medecin atteste un arret de travail pour raison de sante "
     "et prescrit un repos medicamenteux."),
    ("Administratif/demande_conge.pdf",
     "Demande de conge. Le salarie sollicite une autorisation d'absence pour les "
     "vacances et la direction doit valider cette demande."),
    ("Administratif/lettre_demission.pdf",
     "Lettre de demission. Le salarie notifie la rupture de son contrat et annonce "
     "son prevavis de depart a l'employeur."),
    ("Assurance/assurance_auto.pdf",
     "Assurance automobile. Ce contrat couvre le vehicule contre les risques de circulation "
     "et fixe le montant de la prime d'assurance auto."),
    ("Assurance/assurance_habitation.pdf",
     "Assurance habitation. Ce contrat protege le logement contre les risques et definit "
     "les garanties du locataire ou du proprietaire."),
    ("Assurance/attestation_assurance.pdf",
     "Attestation d'assurance. Ce justificatif de souscription prouve que le contrat "
     "d'assurance est en cours de validite."),
    ("Assurance/constat_amiable.pdf",
     "Constat amiable. Ce document descriptif d'accident permet de retracer les "
     "circonstances de la collision entre deux vehicules."),
    ("Assurance/declaration_sinistre.pdf",
     "Declaration de sinistre. Le souscripteur signale un dommage a l'assurance afin "
     "d'obtenir le remboursement prevu au contrat."),
    ("Banque/rib.pdf",
     "Releve d'identite bancaire. Ce document indique l'IBAN et la domiciliation du "
     "compte bancaire du titulaire."),
    ("Banque/ordre_virement.pdf",
     "Ordre de virement. Ce formulaire demande un transfert d'argent vers un "
     "beneficiaire pour un montant precise."),
    ("Banque/pret_immobilier.pdf",
     "Pret immobilier. Ce credit finance l'achat d'un bien et se rembourse par mensualite "
     "garantie par une hypotheque."),
    ("Banque/releve_particulier.pdf",
     "Releve bancaire particulier. Ce document liste les operations et le solde du "
     "compte d'un client prive."),
    ("Banque/releve_pro.pdf",
     "Releve bancaire professionnel. Ce document presente les operations et le solde du "
     "compte d'une entreprise ou d'un professionnel."),
    ("Contrats/cdi.pdf",
     "Contrat a duree indeterminee CDI. Ce contrat d'embauche ne fixe pas de fin et "
     "prevoit une periode d'essai."),
    ("Contrats/cdd.pdf",
     "Contrat a duree determinee CDD. Ce contrat de travail a une duree limitee et "
     "precise la date de fin."),
    ("Contrats/avenant.pdf",
     "Avenant au contrat. Cette piece modifie le contrat initial, par exemple le salaire "
     "ou les horaires de travail."),
    ("Contrats/stage.pdf",
     "Convention de stage. Ce document encadre le sejour d'un etudiant en entreprise "
     "pendant sa periode de stage."),
    ("Contrats/alternance.pdf",
     "Contrat d'alternance. Ce contrat d'apprentissage combine formation et travail en "
     "entreprise pour un jeune."),
    ("Entreprise/bon_commande.pdf",
     "Bon de commande. Ce document d'achat liste les articles, les quantites et le "
     "fournisseur choisi."),
    ("Entreprise/note_service.pdf",
     "Note de service. La direction diffuse une consigne ou une instruction au personnel "
     "de l'entreprise."),
    ("Entreprise/politique_rh.pdf",
     "Politique RH. Cette politique des ressources humaines definit le recrutement, "
     "les congres et la gestion du personnel."),
]


# --- 20 requetes -> document attendu en rang 1 ---
QUERIES = [
    ("acte de naissance", "Administratif/acte_naissance.pdf"),
    ("attestation de domicile", "Administratif/attestation_domicile.pdf"),
    ("attestation de travail employeur", "Administratif/attestation_travail.pdf"),
    ("certificat medical arret maladie", "Administratif/certificat_medical.pdf"),
    ("demande de conge vacances", "Administratif/demande_conge.pdf"),
    ("lettre de demission prevavis", "Administratif/lettre_demission.pdf"),
    ("assurance auto vehicule", "Assurance/assurance_auto.pdf"),
    ("assurance habitation logement", "Assurance/assurance_habitation.pdf"),
    ("attestation d assurance", "Assurance/attestation_assurance.pdf"),
    ("constat amiable accident", "Assurance/constat_amiable.pdf"),
    ("declaration de sinistre remboursement", "Assurance/declaration_sinistre.pdf"),
    ("RIB IBAN compte bancaire", "Banque/rib.pdf"),
    ("ordre de virement beneficiaire", "Banque/ordre_virement.pdf"),
    ("pret immobilier credit", "Banque/pret_immobilier.pdf"),
    ("releve bancaire particulier", "Banque/releve_particulier.pdf"),
    ("releve bancaire professionnel entreprise", "Banque/releve_pro.pdf"),
    ("contrat CDI embauche", "Contrats/cdi.pdf"),
    ("contrat CDD duree determinee", "Contrats/cdd.pdf"),
    ("avenant modification contrat", "Contrats/avenant.pdf"),
    ("convention de stage etudiant", "Contrats/stage.pdf"),
]


def _make_pdf(path, text):
    pdf = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    for line in text.split("\n"):
        pdf.drawString(50, y, line)
        y -= 20
    pdf.save()


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    base = tmp_path_factory.mktemp("corpus")

    for relative_path, text in CORPUS:
        document_path = base / relative_path
        document_path.parent.mkdir(parents=True, exist_ok=True)
        _make_pdf(document_path, text)

    return build_search_engine(documents_dir=str(base))


@pytest.mark.parametrize("query,expected", QUERIES, ids=[q for q, _ in QUERIES])
def test_top1_is_expected_document(query, expected, engine):
    results = search_documents(query, engine, top_k=5)

    assert results, f"Aucun resultat pour la requete {query!r}"

    top = results[0]["relative_path"].replace("\\", "/")
    assert top == expected, (
        f"Requete {query!r} : rang 1 = {top} (attendu {expected})"
    )


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    base = Path(tempfile.mkdtemp(prefix="corpus_"))
    for relative_path, text in CORPUS:
        document_path = base / relative_path
        document_path.parent.mkdir(parents=True, exist_ok=True)
        _make_pdf(document_path, text)

    engine = build_search_engine(documents_dir=str(base))

    passed = 0
    for query, expected in QUERIES:
        results = search_documents(query, engine, top_k=5)
        top = results[0]["relative_path"].replace("\\", "/") if results else None
        ok = top == expected
        passed += ok
        status = "OK " if ok else "ECHEC"
        print(f"[{status}] {query!r:45} -> {top}  (attendu {expected})")

    print(f"\n{passed}/{len(QUERIES)} requetes ciblent le bon document en rang 1.")
    sys.exit(0 if passed == len(QUERIES) else 1)
