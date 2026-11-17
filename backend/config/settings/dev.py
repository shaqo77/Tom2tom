from .base import *  # noqa: F403

DEBUG = True

# Le serveur de développement du frontend (Vite) sert l'interface sur ce port et relaie /api ici :
# son origine doit être reconnue, sans quoi aucune requête qui modifie ne passe le contrôle CSRF.
# La production, elle, sert l'interface et l'API sous UNE origine (voir prod.py).
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]
