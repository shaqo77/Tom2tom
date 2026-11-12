"""Garde-fous automatiques sur les conventions. Voir 03_GUIDE_DEMARRAGE.md partie B."""

import ast
import pathlib

RACINE = pathlib.Path(__file__).resolve().parent.parent
IGNORES = (".venv", "/tests/", "/migrations/")


def _fichiers_source():
    for f in RACINE.rglob("*.py"):
        if any(x in str(f) for x in IGNORES):
            continue
        yield f


def test_aucun_float_sur_un_montant():
    """Interdit FloatField dans tout le backend. Voir §B.1 et règle n°1."""
    fautes = []
    for f in _fichiers_source():
        for n in ast.walk(ast.parse(f.read_text())):
            if isinstance(n, ast.Attribute) and n.attr == "FloatField":
                fautes.append(f"{f.relative_to(RACINE)}:{n.lineno}")
    assert not fautes, f"FloatField interdit sur un montant : {fautes}"


def test_aucun_libelle_mono_langue():
    """Interdit label_fr / label_en. Les libellés sont du JSONB. Voir §B.2."""
    fautes = []
    for f in _fichiers_source():
        for i, ligne in enumerate(f.read_text().splitlines(), 1):
            for motif in ("label_fr", "label_en", "libelle_fr", "libelle_en"):
                if motif in ligne:
                    fautes.append(f"{f.relative_to(RACINE)}:{i} ({motif})")
    assert not fautes, f"Libellé mono-langue interdit : {fautes}"


def test_aucun_eval_ni_exec():
    """Interdit eval/exec. Voir règle n°5."""
    fautes = []
    for f in _fichiers_source():
        for n in ast.walk(ast.parse(f.read_text())):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                if n.func.id in {"eval", "exec"}:
                    fautes.append(f"{f.relative_to(RACINE)}:{n.lineno}")
    assert not fautes, f"eval/exec interdits : {fautes}"
