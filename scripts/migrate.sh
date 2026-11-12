#!/bin/sh
# Applique les migrations avec le rôle PROPRIÉTAIRE (sigf_owner).
# L'application, elle, tourne avec sigf_app, sans droit de création.
set -e
cd "$(dirname "$0")/../backend"
exec ./.venv/bin/python manage.py migrate --settings=config.settings.migrate "$@"
