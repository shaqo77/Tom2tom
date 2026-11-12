"""Refuse de servir avec un rôle qui contourne l'isolation. Voir §B.4.

Toute la garantie d'isolation repose sur un fait : le rôle qui sert les
requêtes subit les politiques de sécurité au niveau ligne. Or le même
fichier .env porte DATABASE_URL et DATABASE_OWNER_URL, et le propriétaire,
lui, possède BYPASSRLS — c'est ce qui lui permet de migrer. Les deux ne
sont séparés que par un « --settings » en ligne de commande.

Une erreur à cet endroit ne casse rien, n'allume aucun test et ne laisse
aucune trace : l'application fonctionne, simplement toutes les
organisations se voient entre elles. C'est précisément le genre de panne
qu'il faut rendre bruyante, et au démarrage plutôt qu'à l'audit.
"""

from django.conf import settings
from django.core.checks import Error, Warning
from django.db import DatabaseError, connection

ROLE_CONTOURNE = "sigf.E001"
ROLE_INATTENDU = "sigf.E002"
ROLE_INVERIFIABLE = "sigf.W001"

REQUETE = """
SELECT current_user,
       coalesce(r.rolbypassrls, false),
       coalesce(r.rolsuper, false)
  FROM pg_roles r
 WHERE r.rolname = current_user
"""


def juger(role, contourne, superutilisateur, attendu):
    """Décide à partir des seuls faits, sans toucher à la base.

    Séparé de la lecture pour rester testable : un rôle qui contourne
    l'isolation ne peut pas être fabriqué depuis l'application — et c'est
    exactement ce qu'on lui demande. Le jugement, lui, doit être vérifié.
    """
    if contourne or superutilisateur:
        motif = "BYPASSRLS" if contourne else "SUPERUSER"
        return [
            Error(
                f"Le rôle « {role} » possède {motif} : les politiques "
                f"d'isolation par organisation ne s'appliquent pas à lui.",
                hint=(
                    "DATABASE_URL pointe probablement sur le rôle "
                    "propriétaire. Celui-ci ne sert qu'aux migrations "
                    "(--settings=config.settings.migrate). L'application "
                    f"doit se connecter comme « {attendu} »."
                ),
                id=ROLE_CONTOURNE,
            )
        ]
    if role != attendu:
        # Le rôle subit bien l'isolation : ce n'est pas une faille, mais un
        # écart de configuration qui mérite d'être vu avant la mise en service.
        return [
            Error(
                f"L'application se connecte comme « {role} », et non « {attendu} ».",
                hint=(
                    "Alignez DATABASE_URL, ou déclarez le rôle attendu dans "
                    "ROLE_APPLICATIF si ce changement est voulu."
                ),
                id=ROLE_INATTENDU,
            )
        ]
    return []


def verifier_role_applicatif(app_configs, **kwargs):
    """Contrôle système : le rôle courant est-il soumis à l'isolation ?"""
    if not getattr(settings, "VERIFIER_ROLE_APPLICATIF", True):
        return []

    attendu = getattr(settings, "ROLE_APPLICATIF", "sigf_app")
    try:
        with connection.cursor() as cur:
            cur.execute(REQUETE)
            rangee = cur.fetchone()
    except DatabaseError as e:
        # Base injoignable : l'application ne servira rien de toute façon.
        # Un avertissement, pas une erreur — sinon « check » devient
        # impossible hors connexion.
        return [
            Warning(
                "Impossible de vérifier le rôle de connexion à la base.",
                hint=f"La base a répondu : {e}",
                id=ROLE_INVERIFIABLE,
            )
        ]

    if rangee is None:
        return [
            Warning(
                "Le rôle de connexion est introuvable dans pg_roles.",
                hint="Vérification de l'isolation impossible.",
                id=ROLE_INVERIFIABLE,
            )
        ]

    role, contourne, superutilisateur = rangee
    return juger(role, contourne, superutilisateur, attendu)
