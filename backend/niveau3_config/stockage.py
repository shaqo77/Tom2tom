"""Stockage des documents de référence. Voir L5-T01.

Le stockage est ADRESSÉ PAR LE CONTENU : la clé d'un fichier est son empreinte SHA-256, préfixée par
l'organisation (deux organisations qui téléversent les mêmes octets n'ont pas le même objet, donc
aucune ne peut deviner ce que l'autre détient). Conséquences voulues :
- téléverser deux fois le même fichier produit la même référence, sans doublon ;
- un fichier modifié d'un seul octet est un AUTRE objet ; l'ancien reste intact ;
- un objet ne s'écrase jamais, il ne se supprime pas par ce module.

Ici, un dossier local (développement et tests). En production, la même interface est tenue par le
stockage objet souverain (spécification §9.3) : seule la classe change, pas les appelants.
"""

import hashlib
import os
import tempfile
from pathlib import Path

from django.conf import settings

SCHEMA = "fs://"


class FichierIntrouvable(LookupError):
    """La référence ne désigne aucun objet stocké."""


def racine() -> Path:
    chemin = (
        getattr(settings, "STOCKAGE_DOCUMENTS_ROOT", None)
        or Path(settings.BASE_DIR) / "var" / "documents"
    )
    return Path(chemin)


def empreinte(contenu: bytes) -> bytes:
    return hashlib.sha256(contenu).digest()


def reference(org_id, digest: bytes) -> str:
    return f"{SCHEMA}{org_id}/{digest.hex()}"


def _chemin(ref: str) -> Path:
    if not ref.startswith(SCHEMA):
        raise FichierIntrouvable(f"Référence de stockage inconnue : {ref}")
    org_id, _, hexa = ref.removeprefix(SCHEMA).partition("/")
    if (
        len(hexa) != 64
        or any(c not in "0123456789abcdef" for c in hexa)
        or "/" in org_id
        or ".." in org_id
    ):
        raise FichierIntrouvable(f"Référence de stockage invalide : {ref}")
    return racine() / org_id / hexa[:2] / hexa


def deposer(org_id, contenu: bytes) -> str:
    """Dépose les octets et retourne leur référence. Idempotent : déjà là, rien n'est réécrit."""
    ref = reference(org_id, empreinte(contenu))
    chemin = _chemin(ref)
    if chemin.exists():
        return ref
    chemin.parent.mkdir(parents=True, exist_ok=True)
    # Écriture atomique : un lecteur ne voit jamais un fichier à moitié écrit.
    descripteur, temporaire = tempfile.mkstemp(dir=chemin.parent)
    try:
        with os.fdopen(descripteur, "wb") as fichier:
            fichier.write(contenu)
        os.replace(temporaire, chemin)
    except BaseException:
        Path(temporaire).unlink(missing_ok=True)
        raise
    return ref


def lire(ref: str) -> bytes:
    chemin = _chemin(ref)
    if not chemin.exists():
        raise FichierIntrouvable(f"Aucun objet stocké pour {ref}")
    return chemin.read_bytes()
