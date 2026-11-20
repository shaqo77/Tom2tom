"""Répartit les fichiers de test en N groupes équilibrés (CI en parallèle).

Usage (depuis backend/) : python ci/repartir_tests.py <groupe 1..N> <N>
Affiche les fichiers du groupe, un par ligne. La taille du fichier sert d'indicateur de durée ;
la répartition est déterministe, donc tous les groupes ensemble couvrent chaque fichier une fois.
"""

import sys
from pathlib import Path


def repartir(fichiers: list[Path], nombre: int) -> list[list[Path]]:
    groupes: list[list[Path]] = [[] for _ in range(nombre)]
    poids = [0] * nombre
    # Les plus gros d'abord, chacun dans le groupe le plus léger ; nom en second critère.
    for fichier in sorted(fichiers, key=lambda f: (-f.stat().st_size, f.name)):
        i = poids.index(min(poids))
        groupes[i].append(fichier)
        poids[i] += fichier.stat().st_size
    return groupes


if __name__ == "__main__":
    groupe, nombre = int(sys.argv[1]), int(sys.argv[2])
    if not 1 <= groupe <= nombre:
        sys.exit("groupe hors de 1..N")
    tests = sorted(Path("tests").glob("test_*.py"))
    for f in sorted(repartir(tests, nombre)[groupe - 1]):
        print(f.as_posix())
