import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { useMoi } from "../../shared/session/moi";
import { Carte } from "../../shared/ui/Carte";
import { Message } from "../../shared/ui/Message";
import { Pastille } from "../../shared/ui/Pastille";
import { libelleProjet } from "../projets/libelle";

/** L'accueil d'une personne connectée : ses projets, ou la raison claire pour laquelle il n'y en a pas. */
export function Accueil() {
  const { t, i18n } = useTranslation();
  const { data: moi } = useMoi();
  if (!moi) return null;

  return (
    <>
      <div className="page__entete">
        <h1>{t("accueil.bonjour", { nom: moi.nom_complet })}</h1>
        {moi.organisation && <p className="page__sous-titre">{moi.organisation.raison_sociale}</p>}
      </div>
      {!moi.organisation ? (
        <Message variante="attention">{t("projets.sans_organisation")}</Message>
      ) : moi.projets.length === 0 ? (
        <Message variante="info">{t("projets.aucun")}</Message>
      ) : (
        <section aria-labelledby="titre-projets">
          <h2 id="titre-projets" className="titre-section">
            {t("projets.titre")}
          </h2>
          <ul className="grille-projets">
            {moi.projets.map((projet) => (
              <li key={projet.id}>
                <Carte>
                  <h3>
                    <Link
                      to="/projets/$projetId"
                      params={{ projetId: projet.id }}
                      aria-label={t("projets.ouvrir", { code: projet.code })}
                      className="carte-projet__lien"
                    >
                      <span className="technique">{projet.code}</span>
                    </Link>
                  </h3>
                  <p>{libelleProjet(projet, i18n.language)}</p>
                  <Pastille variante={projet.statut === "active" ? "succes" : "neutre"}>
                    {t(`projet.statut.${projet.statut}`, { defaultValue: projet.statut })}
                  </Pastille>
                </Carte>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
