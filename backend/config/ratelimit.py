"""Rate limiting partage (login / forgot-password) : defini ici pour etre
utilise a la fois par app.py (etat) et par le controller auth (decorateurs)."""

from slowapi import Limiter
from slowapi.util import get_remote_address


limiter = Limiter(key_func=get_remote_address)
