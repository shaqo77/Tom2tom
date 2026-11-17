import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { Carte } from "../../shared/ui/Carte";

export function Accueil() {
  const { t } = useTranslation();
  return (
    <>
      <div className="page__entete">
        <h1>{t("accueil.titre")}</h1>
        <p className="page__sous-titre">{t("accueil.sous_titre")}</p>
      </div>
      <Carte>
        <Link to="/conception">{t("accueil.guide")}</Link>
      </Carte>
    </>
  );
}
