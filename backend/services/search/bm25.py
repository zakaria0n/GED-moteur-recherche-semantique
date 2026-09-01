"""BM25 lexical (Okapi) en Python pur, sans dependance externe.

Complète la recherche dense (SBERT) pour les termes exacts (numeros de
dossier, noms de formulaires) ou les requetes courtes ou le sens seul
suffit pas. Fusionne avec le score dense via RRF dans search_engine.
"""

import math
import re
from collections import defaultdict


_TOKEN_RE = re.compile(r"[a-zà-ÿ0-9]+")

# Mots-outils francais : pas de valeur discriminante pour le lexical (BM25),
# ils ne feraient que bruitier le classement. On les filtre a l'indexation et
# a la requete pour renforcer le signal des termes porteurs de sens.
_FRENCH_STOPWORDS = frozenset(
    """
    le la les un une des du de et est sont etre avec sans pour par sur dans en
    au aux ce cette ces cet il elle ils elles je tu nous vous son sa ses leur
    leurs qui que quoi dont ou si mais ne pas plus moins tres ont etait celui
    celle ceux cellees meme ainsi apres avant autre leurs des lors cas via
    """.split()
)


def tokenize(text):
    """Decoupe un texte en tokens minuscules (lettres accentuees + chiffres)."""

    if not text:
        return []

    return [
        token
        for token in _TOKEN_RE.findall(text.lower())
        if token not in _FRENCH_STOPWORDS
    ]


class BM25:
    """Index BM25 sur une liste de documents (passages) deja tokenises."""

    def __init__(self, corpus_tokens, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.docs = corpus_tokens
        self.doc_count = len(corpus_tokens)
        self.avgdl = sum(len(tokens) for tokens in corpus_tokens) / max(1, self.doc_count)

        self.df = defaultdict(int)
        self.tf = []

        for tokens in corpus_tokens:
            frequencies = defaultdict(int)

            for token in tokens:
                frequencies[token] += 1

            self.tf.append(frequencies)

            for token in frequencies:
                self.df[token] += 1

        self.idf = {
            token: math.log(1 + (self.doc_count - document_frequency + 0.5) / (document_frequency + 0.5))
            for token, document_frequency in self.df.items()
        }

    def get_scores(self, query_tokens):
        """Renvoie un score BM25 par document pour les tokens de la requete."""

        scores = [0.0] * self.doc_count

        for query_token in set(query_tokens):
            inverse_document_frequency = self.idf.get(query_token)

            if inverse_document_frequency is None:
                continue

            for document_index, frequencies in enumerate(self.tf):
                count = frequencies.get(query_token)

                if not count:
                    continue

                document_length = len(self.docs[document_index])
                denominator = count + self.k1 * (1 - self.b + self.b * document_length / self.avgdl)
                scores[document_index] += inverse_document_frequency * (count * (self.k1 + 1)) / denominator

        return scores
