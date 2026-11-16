# ruff: noqa: F811, E501
"""Import d'un relevé bancaire MT940 / CAMT.053. Voir L9-T05 (complément).

Contrôles : un relevé incohérent n'écrit rien ; rejouer le même fichier ne change rien ; le numéro
de compte n'apparaît dans aucun message ; une entité XML est refusée ; le relevé importé alimente
l'état de reconstitution du compte désigné.
"""

import datetime
from decimal import Decimal

import pytest
from django.db import connection
from rest_framework.exceptions import PermissionDenied

from core.erreurs import ErreurMetier
from niveau1_socle.financements.services import creer_compte_bancaire
from niveau1_socle.rapprochement.models import MouvementReleve
from niveau1_socle.tresorerie.models import SoldeReleve
from niveau1_socle.tresorerie.releves import importer_releve, lire_camt053, lire_mt940, lire_releves
from niveau1_socle.tresorerie.services import etat_reconstitution, justifier_ecart
from tests.test_cycle_ecriture_bd import decor  # noqa: F401
from tests.test_demandes_retrait_bd import drf  # noqa: F401
from tests.test_financements_bd import cadre  # noqa: F401
from tests.test_tresorerie_bd import banque  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)
J = datetime.date
D = Decimal
NUMERO = "DJ21 0001 0000 0099 8877"

MT940 = """{1:F01BCDJDJJDAXXX0000000000}{2:I940BCDJDJJDXXXXN}{4:
:20:REL-2026-02
:25:DJ21000100000099 8877
:28C:00001/001
:60F:C260131DJF1000,00
:61:2602100210C300,00NTRFNONREF//AV-1
:86:Avance de la Banque mondiale
:61:2602150215D120,00NCHGNONREF//FRAIS-1
:86:Frais de tenue
de compte
:61:2602200220RD20,00NTRFNONREF
:86:Annulation d'un frais
:62F:C260228DJF1200,00
-}"""

CAMT = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <Stmt>
      <Id>REL-2026-02</Id>
      <Acct><Id><IBAN>DJ21000100000099 8877</IBAN></Id></Acct>
      <Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp><Amt Ccy="DJF">1000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-01-31</Dt></Dt></Bal>
      <Bal><Tp><CdOrPrtry><Cd>CLBD</Cd></CdOrPrtry></Tp><Amt Ccy="DJF">1200.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-02-28</Dt></Dt></Bal>
      <Ntry><Amt Ccy="DJF">300.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><BookgDt><Dt>2026-02-10</Dt></BookgDt><AcctSvcrRef>AV-1</AcctSvcrRef><AddtlNtryInf>Avance de la Banque mondiale</AddtlNtryInf></Ntry>
      <Ntry><Amt Ccy="DJF">120.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><BookgDt><Dt>2026-02-15</Dt></BookgDt><AcctSvcrRef>FRAIS-1</AcctSvcrRef></Ntry>
      <Ntry><Amt Ccy="DJF">20.00</Amt><CdtDbtInd>DBIT</CdtDbtInd><RvslInd>true</RvslInd><BookgDt><Dt>2026-02-20</Dt></BookgDt></Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>"""


def _compte(banque):
    return banque[3]


def test_un_mt940_se_lit_avec_ses_soldes_ses_signes_et_des_references_stables():
    [r] = lire_mt940(MT940)
    assert (r.reference, r.devise) == ("REL-2026-02", "DJF")
    assert (r.date_ouverture, r.solde_ouverture) == (J(2026, 1, 31), D("1000.00"))
    assert (r.date_cloture, r.solde_cloture) == (J(2026, 2, 28), D("1200.00"))
    assert [(m.reference, m.date, m.montant) for m in r.mouvements] == [
        ("AV-1", J(2026, 2, 10), D("300.00")),
        ("FRAIS-1", J(2026, 2, 15), D("-120.00")),
        (
            "REL-2026-02:0003",
            J(2026, 2, 20),
            D("20.00"),
        ),  # annulation de débit : +20 ; pas de réf. banque
    ]
    assert r.mouvements[1].libelle == "Frais de tenue de compte"


def test_un_camt053_donne_le_meme_releve_que_le_mt940():
    [a] = lire_mt940(MT940)
    [b] = lire_camt053(CAMT.encode())
    assert [(m.reference, m.date, m.montant) for m in a.mouvements] == [
        (m.reference, m.date, m.montant) for m in b.mouvements
    ]
    assert (a.solde_ouverture, a.solde_cloture, a.devise) == (
        b.solde_ouverture,
        b.solde_cloture,
        b.devise,
    )
    assert (
        lire_releves(CAMT)[0].reference == "REL-2026-02"
        and lire_releves(MT940)[0].reference == "REL-2026-02"
    )


@pytest.mark.parametrize("fichier", [MT940, CAMT])
def test_importer_un_releve_pose_les_mouvements_et_les_deux_soldes(banque, fichier):
    _, _, profils, designe, _ = banque
    bilan = importer_releve(utilisateur=profils["claire"], compte=designe, contenu=fichier)
    assert bilan == {"mouvements_importes": 3, "mouvements_ignores": 0, "soldes_poses": 2}
    assert MouvementReleve.objects.filter(compte=designe).count() == 3
    soldes = {s.date_solde: s.solde for s in SoldeReleve.objects.filter(compte=designe)}
    assert soldes == {J(2026, 1, 31): D("1000.00"), J(2026, 2, 28): D("1200.00")}


def test_rejouer_le_meme_fichier_ne_change_rien(banque):
    _, _, profils, designe, _ = banque
    importer_releve(utilisateur=profils["claire"], compte=designe, contenu=MT940)
    bilan = importer_releve(utilisateur=profils["claire"], compte=designe, contenu=MT940)
    assert bilan == {"mouvements_importes": 0, "mouvements_ignores": 3, "soldes_poses": 0}
    importer_releve(
        utilisateur=profils["claire"], compte=designe, contenu=CAMT
    )  # l'autre format, mêmes références
    assert MouvementReleve.objects.filter(compte=designe).count() == 3


def test_un_releve_incoherent_n_ecrit_rien(banque):
    _, _, profils, designe, _ = banque
    faux = MT940.replace("C260228DJF1200,00", "C260228DJF1200,01")
    with pytest.raises(ErreurMetier) as e:
        importer_releve(utilisateur=profils["claire"], compte=designe, contenu=faux)
    assert "incohérent" in str(e.value) and "1200.01" in str(e.value)
    assert not MouvementReleve.objects.exists() and not SoldeReleve.objects.exists()


def test_un_solde_deja_pose_avec_une_autre_valeur_est_un_conflit_et_annule_tout(banque):
    from niveau1_socle.tresorerie.services import enregistrer_solde_releve

    _, _, profils, designe, _ = banque
    enregistrer_solde_releve(
        utilisateur=profils["amina"], compte=designe, date_solde=J(2026, 2, 28), solde="999"
    )
    with pytest.raises(ErreurMetier):
        importer_releve(utilisateur=profils["claire"], compte=designe, contenu=MT940)
    assert not MouvementReleve.objects.exists()  # le conflit défait aussi l'import des mouvements


def test_le_releve_d_un_autre_compte_ou_d_une_autre_devise_est_refuse_sans_reveler_le_numero(
    banque,
):
    _, projet, profils, designe, _ = banque
    autre = creer_compte_bancaire(
        utilisateur=profils["dora"], project_id=projet.id, code="CD-2", type="designe", devise="DJF",
        banque="BCD", numero="DJ21 0001 0000 0011 2233",
    )  # fmt: skip
    with pytest.raises(ErreurMetier) as e:
        importer_releve(utilisateur=profils["claire"], compte=autre, contenu=MT940)
    assert "CD-2" in str(e.value) and "0099" not in str(e.value) and "8877" not in str(e.value)
    usd = MT940.replace("DJF", "USD")
    with pytest.raises(ErreurMetier) as e:
        importer_releve(utilisateur=profils["claire"], compte=designe, contenu=usd)
    assert "USD" in str(e.value)


def test_un_compte_en_devise_etrangere_exige_un_taux_explicite(banque):
    _, projet, profils, _, _ = banque
    usd = creer_compte_bancaire(
        utilisateur=profils["dora"], project_id=projet.id, code="CD-USD", type="designe", devise="USD",
        banque="BCD", numero="US 99",
    )  # fmt: skip
    fichier = MT940.replace("DJ21000100000099 8877", "US99").replace("DJF", "USD")
    with pytest.raises(ErreurMetier) as e:
        importer_releve(utilisateur=profils["claire"], compte=usd, contenu=fichier)
    assert "taux" in str(e.value)
    bilan = importer_releve(
        utilisateur=profils["claire"], compte=usd, contenu=fichier, taux="177.5"
    )
    assert bilan["mouvements_importes"] == 3
    assert MouvementReleve.objects.get(compte=usd, reference="AV-1").montant_base == D(
        "53250"
    )  # 300 × 177,5


def test_un_xml_avec_dtd_ou_entite_est_refuse(banque):
    _, _, profils, designe, _ = banque
    piege = CAMT.replace("<Document", '<!DOCTYPE d [<!ENTITY x "boom">]><Document', 1)
    with pytest.raises(ErreurMetier) as e:
        importer_releve(utilisateur=profils["claire"], compte=designe, contenu=piege)
    assert "DTD" in str(e.value)
    with pytest.raises(ErreurMetier):
        importer_releve(utilisateur=profils["claire"], compte=designe, contenu="<Document><oups>")


@pytest.mark.parametrize("contenu", ["", "n'importe quoi", ":20:X\n:25:Y\n", b"\x00" * 10])
def test_un_fichier_vide_illisible_ou_incomplet_est_refuse(banque, contenu):
    _, _, profils, designe, _ = banque
    with pytest.raises(ErreurMetier):
        importer_releve(utilisateur=profils["claire"], compte=designe, contenu=contenu)
    assert not MouvementReleve.objects.exists()


def test_un_format_inconnu_et_un_fichier_trop_gros_sont_refuses(banque):
    _, _, profils, designe, _ = banque
    with pytest.raises(ErreurMetier):
        importer_releve(utilisateur=profils["claire"], compte=designe, contenu=MT940, format="ofx")
    with pytest.raises(ErreurMetier):
        lire_releves(b"x" * (10 * 1024 * 1024 + 1))


def test_l_import_exige_l_habilitation_de_comptabiliser(banque):
    _, _, profils, designe, _ = banque
    with pytest.raises(PermissionDenied):  # amina saisit mais ne comptabilise pas
        importer_releve(utilisateur=profils["amina"], compte=designe, contenu=MT940)
    assert not MouvementReleve.objects.exists()


def test_le_releve_importe_alimente_l_etat_de_reconstitution(banque):
    """Ouverture au 31/01, clôture au 28/02 : l'état se rapproche du relevé sans autre saisie."""
    _, _, profils, designe, _ = banque
    importer_releve(utilisateur=profils["claire"], compte=designe, contenu=MT940)
    etat = etat_reconstitution(
        utilisateur=profils["amina"],
        compte=designe,
        date_debut=J(2026, 2, 1),
        date_fin=J(2026, 2, 28),
    )
    assert etat.complet and etat.ouverture == D("1000.00") and etat.cloture_releve == D("1200.00")
    assert etat.autres_encaissements == D("320.00") and etat.decaissements == D("120.00")
    assert etat.cloture_calculee == D("1200.00") and etat.ecart_releve == 0
    # Le grand livre n'a pas été écrit : l'écart comptable existe et se justifie explicitement.
    assert etat.ecart_comptable != 0 and not etat.justifie
    justifier_ecart(
        utilisateur=profils["bruno"], compte=designe, date_debut=J(2026, 2, 1), date_fin=J(2026, 2, 28),
        cible="comptable", montant=etat.ecart_comptable, explication="Écritures de la période non encore passées",
    )  # fmt: skip
    assert etat_reconstitution(
        utilisateur=profils["amina"],
        compte=designe,
        date_debut=J(2026, 2, 1),
        date_fin=J(2026, 2, 28),
    ).justifie
    assert connection.vendor == "postgresql"


def test_un_solde_d_ouverture_debiteur_est_negatif():
    fichier = MT940.replace(":60F:C260131DJF1000,00", ":60F:D260131DJF100,00").replace(
        ":62F:C260228DJF1200,00", ":62F:C260228DJF100,00"
    )
    [r] = lire_mt940(fichier)
    assert r.solde_ouverture == D("-100.00") and r.solde_cloture == D("100.00")
    assert sum(m.montant for m in r.mouvements) == D("200.00")  # −100 + 200 = +100 : cohérent


def test_deux_mouvements_de_meme_reference_bancaire_gardent_des_references_distinctes():
    fichier = MT940.replace("//FRAIS-1", "//AV-1")  # la même référence que le premier
    refs = [m.reference for m in lire_mt940(fichier)[0].mouvements]
    assert len(set(refs)) == 3 and refs[:2] == ["REL-2026-02:0001", "REL-2026-02:0002"]


def test_les_devises_d_ouverture_et_de_cloture_doivent_etre_les_memes():
    fichier = MT940.replace(":62F:C260228DJF1200,00", ":62F:C260228USD1200,00")
    with pytest.raises(ErreurMetier) as e:
        lire_mt940(fichier)
    assert "devise" in str(e.value)


def test_un_fichier_trop_gros_est_refuse_pour_sa_taille():
    with pytest.raises(ErreurMetier) as e:
        lire_releves(b"x" * (10 * 1024 * 1024 + 1))
    assert "volumineux" in str(e.value)


def test_sans_habilitation_on_n_apprend_rien_du_fichier(banque):
    _, _, profils, designe, _ = banque
    with pytest.raises(PermissionDenied):  # même un fichier illisible : d'abord l'habilitation
        importer_releve(utilisateur=profils["amina"], compte=designe, contenu="n'importe quoi")
