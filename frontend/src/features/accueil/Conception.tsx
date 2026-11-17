import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Bouton } from "../../shared/ui/Bouton";
import { Carte } from "../../shared/ui/Carte";
import { Champ } from "../../shared/ui/Champ";
import { Message } from "../../shared/ui/Message";
import { Montant } from "../../shared/ui/Montant";
import { Pastille } from "../../shared/ui/Pastille";

const COULEURS = [
  "--fond", "--surface", "--surface-2", "--bordure", "--texte", "--texte-2",
  "--accent", "--accent-fond", "--succes", "--succes-fond", "--attention",
  "--attention-fond", "--danger", "--danger-fond", "--info", "--info-fond",
]; // fmt: skip

/** Le guide de style : chaque couleur et chaque brique, dans tous ses états. */
export function Conception() {
  const { t } = useTranslation();
  const [charge, definirCharge] = useState(false);
  return (
    <>
      <div className="page__entete">
        <h1>{t("conception.titre")}</h1>
        <p className="page__sous-titre">{t("conception.sous_titre")}</p>
      </div>

      <Carte titre={t("conception.couleurs")}>
        <div className="grille">
          {COULEURS.map((nom) => (
            <div className="echantillon" key={nom}>
              <div className="echantillon__pastille" style={{ background: `var(${nom})` }} />
              <code>{nom}</code>
            </div>
          ))}
        </div>
      </Carte>

      <Carte titre={t("conception.boutons")}>
        <div className="rangee">
          <Bouton>{t("commun.valider")}</Bouton>
          <Bouton variante="secondaire">{t("commun.annuler")}</Bouton>
          <Bouton variante="discret">{t("commun.fermer")}</Bouton>
          <Bouton variante="danger">{t("commun.annuler")}</Bouton>
          <Bouton disabled>{t("commun.enregistrer")}</Bouton>
          <Bouton chargement={charge} onClick={() => definirCharge(true)}>
            {t("commun.enregistrer")}
          </Bouton>
        </div>
      </Carte>

      <Carte titre={t("conception.champs")}>
        <div className="colonne">
          <Champ etiquette={t("conception.champ_exemple")} aide={t("conception.champ_aide")} />
          <Champ etiquette={t("conception.champ_exemple")} erreur={t("conception.champ_erreur")} />
        </div>
      </Carte>

      <Carte titre={t("conception.messages")}>
        <div className="colonne">
          <Message variante="info">{t("conception.message_info")}</Message>
          <Message variante="succes">{t("conception.message_succes")}</Message>
          <Message variante="attention">{t("conception.message_attention")}</Message>
          <Message variante="danger">{t("conception.message_danger")}</Message>
        </div>
        <div className="rangee" style={{ marginBlockStart: "var(--esp-4)" }}>
          <Pastille variante="succes">{t("conception.badge_actif")}</Pastille>
          <Pastille>{t("conception.badge_brouillon")}</Pastille>
          <Pastille variante="accent">{t("conception.badge_clos")}</Pastille>
          <Pastille variante="alerte">{t("conception.badge_alerte")}</Pastille>
        </div>
      </Carte>

      <Carte titre={t("conception.montants")}>
        <div className="colonne">
          <Montant valeur="1234567.8" decimales={2} devise="DJF" />
          <Montant valeur="-250000" decimales={0} devise="DJF" />
          <Montant valeur="12345678901234567890.1234" decimales={4} devise="USD" />
        </div>
      </Carte>
    </>
  );
}
