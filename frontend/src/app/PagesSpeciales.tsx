import type { ErrorComponentProps } from "@tanstack/react-router";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { Bouton } from "../shared/ui/Bouton";
import { Message } from "../shared/ui/Message";

/** Une page qui a planté : un message dans la langue de l'utilisateur, jamais la trace technique. */
export function PageErreur({ reset }: ErrorComponentProps) {
  const { t } = useTranslation();
  return (
    <>
      <div className="page__entete">
        <h1>{t("page.erreur_titre")}</h1>
      </div>
      <Message variante="danger">{t("page.erreur")}</Message>
      <div>
        <Bouton variante="secondaire" onClick={() => reset()}>
          {t("commun.reessayer")}
        </Bouton>
      </div>
      <Link to="/">{t("page.retour_accueil")}</Link>
    </>
  );
}

export function PageIntrouvable() {
  const { t } = useTranslation();
  return (
    <>
      <div className="page__entete">
        <h1>{t("page.introuvable_titre")}</h1>
        <p className="page__sous-titre">{t("page.introuvable")}</p>
      </div>
      <Link to="/">{t("page.retour_accueil")}</Link>
    </>
  );
}
