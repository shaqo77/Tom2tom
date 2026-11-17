import { Link, useParams } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { OPERATIONS, projetParId } from "../../shared/session/droits";
import { useMoi } from "../../shared/session/moi";
import { Carte } from "../../shared/ui/Carte";
import { Message } from "../../shared/ui/Message";
import { Pastille } from "../../shared/ui/Pastille";
import { libelleProjet } from "./libelle";

/** La page d'un projet : son identité et, en clair, ce que l'utilisateur y peut faire. */
export function ProjetPage() {
  const { t, i18n } = useTranslation();
  const { projetId } = useParams({ from: "/protege/projets/$projetId" });
  const { data: moi } = useMoi();
  const projet = projetParId(moi, projetId);

  if (!projet) {
    return (
      <>
        <Message variante="attention">{t("projets.introuvable")}</Message>
        <Link to="/">{t("projets.retour")}</Link>
      </>
    );
  }
  const accordees = OPERATIONS.filter((o) => projet.operations.includes(o));
  const sites = Object.entries(projet.operations_par_site);
  return (
    <>
      <div className="page__entete">
        <h1>
          <span className="technique">{projet.code}</span> · {libelleProjet(projet, i18n.language)}
        </h1>
        <p>
          <Pastille variante={projet.statut === "active" ? "succes" : "neutre"}>
            {t(`projet.statut.${projet.statut}`, { defaultValue: projet.statut })}
          </Pastille>
        </p>
      </div>
      <Carte titre={t("droits.titre")}>
        {accordees.length === 0 ? (
          <p>{t("droits.aucun")}</p>
        ) : (
          <ul className="liste-pastilles" aria-label={t("droits.titre")}>
            {accordees.map((o) => (
              <li key={o}>
                <Pastille variante="accent">{t(`droits.${o}`)}</Pastille>
              </li>
            ))}
          </ul>
        )}
        {sites.map(([site, operations]) => (
          <div key={site} className="droits-site">
            <h3>{t("droits.par_site", { site })}</h3>
            <ul className="liste-pastilles">
              {OPERATIONS.filter((o) => operations.includes(o)).map((o) => (
                <li key={o}>
                  <Pastille>{t(`droits.${o}`)}</Pastille>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </Carte>
      <Link to="/">{t("projets.retour")}</Link>
    </>
  );
}
