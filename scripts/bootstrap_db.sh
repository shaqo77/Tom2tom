#!/bin/sh
# Amorce le cluster (schéma applicatif + rôles) AVANT la première migration.
set -e
cd "$(dirname "$0")/.."
exec backend/.venv/bin/python scripts/bootstrap_db.py "$@"
