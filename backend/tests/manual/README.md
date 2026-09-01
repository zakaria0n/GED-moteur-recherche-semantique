# Tests manuels (bout en bout)

Scripts de test de l'API **en conditions reelles** : ils attaquent un backend
demarre (contrairement aux tests pytest unitaires du dossier parent, qui
tournent sans serveur).

## Preconditions

1. MySQL/MariaDB actif ;
2. backend demarre : `python -m uvicorn app:app --host 127.0.0.1 --port 8000` ;
3. dependance supplementaire : `pip install requests` (non incluse dans
   requirements.txt, reservee a ces scripts) ;
4. un compte utilisateur existant (ajuster les identifiants en tete de script).

## Scripts

| Script | Contenu |
|---|---|
| `manual_test_search.py` | 20 recherches de bases : categorie attendue par requete |
| `manual_test_search_v2.py` | Variante elargie des 20 cas |
| `manual_test_search_semantic.py` | Cas difficiles : requetes indirectes, synonymes, concepts (qualite semantique) |

## Lancement

```bash
python tests/manual/manual_test_search.py
```

Ces scripts ne sont PAS collectes par pytest (prefixe `manual_`) : ils
necessitent un serveur vivant et ne doivent pas casser la CI unitaire.
