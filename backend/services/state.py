"""Etat partage du moteur de recherche (accede par les routers et le sync)."""

import threading

# Protege le remplacement du moteur : on ne mute jamais le moteur en place, on
# construit un nouveau dict puis on le swap atomiquement sous ce verrou. Cela
# evite qu'une recherche concurrente lise un moteur a moitie mis a jour
# (index reconstruit mais chunks pas encore alignes -> IndexError / resultat faux).
search_state_lock = threading.Lock()

search_state = {
    "engine": None,
    "database_error": None,
    "sync_running": False,
    "last_sync_message": "Aucune synchronisation lancee",
}
