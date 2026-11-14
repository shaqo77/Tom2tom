from .base import *  # noqa: F403
from .base import SECRET_KEY, env

DEBUG = False
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# Un an de HSTS, sous-domaines compris ; derrière un proxy qui termine TLS.
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Une clé trop courte ou d'exemple signe des sessions falsifiables : on refuse de démarrer.
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("changez-moi"):
    raise RuntimeError("SECRET_KEY de production trop courte (50 caractères) ou d'exemple")
