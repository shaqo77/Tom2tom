import { useTranslation } from "react-i18next";

import { formater, lire } from "../money/montant";

import "./ui.css";

/**
 * Un montant exact, aligné en colonne. Ses chiffres restent TOUJOURS de gauche à droite, même en
 * écriture droite-à-gauche ; un solde négatif porte son signe, pas seulement une couleur.
 */
export function Montant({ valeur, decimales, devise }: { valeur: string; decimales: number; devise?: string }) {
  const { i18n } = useTranslation();
  const langue = i18n.language === "pseudo" ? "fr" : i18n.language;
  const negatif = lire(valeur).isNegative() && !lire(valeur).isZero();
  return (
    <span className={`montant ${negatif ? "montant--negatif" : ""}`.trim()} dir="ltr">
      <span className="montant__valeur">{formater(valeur, langue, decimales)}</span>
      {devise && <span className="montant__devise">{devise}</span>}
    </span>
  );
}
