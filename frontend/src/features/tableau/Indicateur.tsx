import { useTranslation } from "react-i18next";

import { enPourcentage, largeurJauge } from "../../shared/money/montant";
import { Montant } from "../../shared/ui/Montant";
import type { MontantsParDevise } from "./types";

const DECIMALES_PAR_DEFAUT = 2;

/** Un indicateur en montants : UNE ligne par devise, jamais une somme de devises différentes. */
export function IndicateurMontants({
  titre,
  montants,
  devises,
}: {
  titre: string;
  montants: MontantsParDevise;
  devises: Record<string, number>;
}) {
  const { t } = useTranslation();
  const lignes = Object.entries(montants).sort(([a], [b]) => a.localeCompare(b));
  return (
    <div className="indicateur">
      <h3 className="indicateur__titre">{titre}</h3>
      {lignes.length === 0 ? (
        <p className="indicateur__vide">
          <span aria-hidden="true">—</span>
          <span className="visuellement-cache">{t("tableau.aucun_montant")}</span>
        </p>
      ) : (
        <ul className="indicateur__lignes">
          {lignes.map(([devise, valeur]) => (
            <li key={devise}>
              <Montant valeur={valeur} decimales={devises[devise] ?? DECIMALES_PAR_DEFAUT} devise={devise} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Un taux (rapport décimal) par devise, avec une jauge : le chiffre est écrit, la jauge n'est qu'un repère. */
export function IndicateurTaux({
  titre,
  taux,
}: {
  titre: string;
  taux: Record<string, string | null>;
}) {
  const { t, i18n } = useTranslation();
  const langue = i18n.language === "pseudo" ? "fr" : i18n.language;
  const lignes = Object.entries(taux).sort(([a], [b]) => a.localeCompare(b));
  return (
    <div className="indicateur">
      <h3 className="indicateur__titre">{titre}</h3>
      {lignes.length === 0 ? (
        <p className="indicateur__vide">
          <span aria-hidden="true">—</span>
          <span className="visuellement-cache">{t("tableau.aucun_montant")}</span>
        </p>
      ) : (
        <ul className="indicateur__lignes">
          {lignes.map(([devise, rapport]) => (
            <li key={devise} className="taux">
              <span className="taux__texte chiffres" dir="ltr">
                {rapport === null ? "—" : enPourcentage(rapport, langue, 1)}
              </span>
              <span className="montant__devise">{devise}</span>
              {rapport !== null && (
                <span className="jauge" aria-hidden="true">
                  <span className="jauge__remplie" style={{ inlineSize: `${largeurJauge(rapport)}%` }} />
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
