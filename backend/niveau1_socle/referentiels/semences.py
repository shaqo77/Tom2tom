"""Semence du référentiel des devises (ISO 4217). Voir L2-T01.

Utilisée par la migration 0002 et par la fixture de test `devises_referentiel` :
les tests en `transaction=True` vident toutes les tables, données de migration
comprises.
"""

# Codes ISO 4217 et nombre de décimales de l'unité monétaire (« minor unit »).
# Liste de départ, extensible par le propriétaire du schéma — jamais par
# l'application, qui n'a que la lecture.
DEVISES_INITIALES = [
    ("DJF", "Franc djiboutien", "Djiboutian franc", 0),
    ("USD", "Dollar des États-Unis", "United States dollar", 2),
    ("EUR", "Euro", "Euro", 2),
    ("GBP", "Livre sterling", "Pound sterling", 2),
    ("CHF", "Franc suisse", "Swiss franc", 2),
    ("JPY", "Yen", "Yen", 0),
    ("CNY", "Yuan renminbi", "Yuan renminbi", 2),
    ("XOF", "Franc CFA (BCEAO)", "CFA franc BCEAO", 0),
    ("XAF", "Franc CFA (BEAC)", "CFA franc BEAC", 0),
    ("KMF", "Franc comorien", "Comorian franc", 0),
    ("ETB", "Birr éthiopien", "Ethiopian birr", 2),
    ("ERN", "Nakfa érythréen", "Eritrean nakfa", 2),
    ("SOS", "Shilling somalien", "Somali shilling", 2),
    ("KES", "Shilling kényan", "Kenyan shilling", 2),
    ("UGX", "Shilling ougandais", "Ugandan shilling", 0),
    ("TZS", "Shilling tanzanien", "Tanzanian shilling", 2),
    ("RWF", "Franc rwandais", "Rwandan franc", 0),
    ("BIF", "Franc burundais", "Burundi franc", 0),
    ("MGA", "Ariary malgache", "Malagasy ariary", 2),
    ("HTG", "Gourde haïtienne", "Haitian gourde", 2),
    ("MAD", "Dirham marocain", "Moroccan dirham", 2),
    ("TND", "Dinar tunisien", "Tunisian dinar", 3),
    ("EGP", "Livre égyptienne", "Egyptian pound", 2),
    ("SAR", "Riyal saoudien", "Saudi riyal", 2),
    ("AED", "Dirham des Émirats arabes unis", "UAE dirham", 2),
    ("YER", "Rial yéménite", "Yemeni rial", 2),
    ("SDG", "Livre soudanaise", "Sudanese pound", 2),
]


def charger(modele_devise) -> None:
    """Insère les devises initiales. `modele_devise` : le modèle (ou son état historique)."""
    modele_devise.objects.bulk_create(
        [
            modele_devise(code=c, label={"fr": fr, "en": en}, decimales=d)
            for c, fr, en, d in DEVISES_INITIALES
        ]
    )
