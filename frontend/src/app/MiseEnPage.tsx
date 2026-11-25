import { useQueryClient } from "@tanstack/react-query";
import { Link, Outlet, useMatch, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { libelleProjet } from "../features/projets/libelle";
import { LANGUES, NOMS_LANGUES, PSEUDO, appliquerLangue } from "../i18n";
import { ErreurApi } from "../shared/api/client";
import { enregistrerLangue, seDeconnecter } from "../shared/session/api";
import { useMoi } from "../shared/session/moi";
import { appliquerTheme, themeEnregistre } from "../shared/theme";
import type { Theme } from "../shared/theme";
import { Bouton } from "../shared/ui/Bouton";
import { Message } from "../shared/ui/Message";
import { Selecteur } from "../shared/ui/Selecteur";
import "./app.css";

const THEMES: Theme[] = ["systeme", "clair", "sombre"];

/** L'enveloppe de toutes les pages : lien d'évitement, en-tête (compte, projet, langue, thème). */
export function MiseEnPage() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { data: moi } = useMoi();
  const courant = useMatch({ from: "/protege/projets/$projetId", shouldThrow: false });
  const [theme, definirTheme] = useState<Theme>(themeEnregistre);
  const [echecSortie, definirEchecSortie] = useState<string | null>(null);
  const langues = import.meta.env.DEV ? [...LANGUES, PSEUDO] : [...LANGUES];

  async function changerLangue(code: string) {
    const appliquee = await appliquerLangue(code);
    if (moi && (appliquee === "fr" || appliquee === "en")) {
      // Mémorisée sur le compte ; si l'enregistrement échoue, la langue vaut pour cette page seulement.
      try {
        queryClient.setQueryData(["moi"], await enregistrerLangue(appliquee));
      } catch {
        /* pas bloquant */
      }
    }
  }

  async function sortir() {
    definirEchecSortie(null);
    try {
      await seDeconnecter();
    } catch (erreur) {
      const code = erreur instanceof ErreurApi ? erreur.code : "inconnue";
      definirEchecSortie(t(`erreur.${code}`, { defaultValue: t("erreur.inconnue") }));
      return; // la session serveur existe encore : on ne fait pas semblant d'être déconnecté
    }
    queryClient.clear(); // plus rien d'une session précédente ne reste en mémoire
    await navigate({ to: "/connexion" });
  }

  return (
    <>
      <a className="evitement" href="#contenu">
        {t("commun.aller_au_contenu")}
      </a>
      <header className="entete">
        <div className="entete__haut">
          <Link to="/" className="entete__marque">
            {t("accueil.titre")}
          </Link>
          {moi && (
            <nav aria-label={t("commun.navigation")} className="navigation">
              <Link to="/tableau-de-bord" className="navigation__lien" activeProps={{ className: "navigation__lien navigation__lien--actif" }}>
                {t("tableau.nav")}
              </Link>
              <Link to="/parametres-devises" className="navigation__lien" activeProps={{ className: "navigation__lien navigation__lien--actif" }}>
                {t("devises.nav")}
              </Link>
              <Link to="/taux-de-change" className="navigation__lien" activeProps={{ className: "navigation__lien navigation__lien--actif" }}>
                {t("taux.nav")}
              </Link>
            </nav>
          )}
          {moi && (
            <div className="compte">
              <span className="compte__nom">
                <span className="visuellement-cache">{t("session.compte")} : </span>
                {moi.nom_complet}
                {moi.organisation && <small className="technique"> · {moi.organisation.code}</small>}
              </span>
              <Link to="/mot-de-passe" className="navigation__lien" activeProps={{ className: "navigation__lien navigation__lien--actif" }}>
                {t("mdp.nav")}
              </Link>
              <Bouton variante="secondaire" onClick={() => void sortir()}>
                {t("session.deconnexion")}
              </Bouton>
            </div>
          )}
        </div>
        <div className="entete__contexte">
          {moi && moi.projets.length > 0 && (
            <Selecteur
              etiquette={t("projets.choisir")}
              valeur={courant?.params.projetId ?? ""}
              options={[
                { valeur: "", libelle: t("projets.tous") },
                ...moi.projets.map((p) => ({
                  valeur: p.id,
                  libelle: `${p.code} — ${libelleProjet(p, i18n.language)}`,
                })),
              ]}
              onChange={(id) =>
                void (id
                  ? navigate({ to: "/projets/$projetId", params: { projetId: id } })
                  : navigate({ to: "/" }))
              }
            />
          )}
          <div className="entete__reglages">
            <Selecteur
              etiquette={t("commun.langue")}
              valeur={i18n.language}
              options={langues.map((code) => ({ valeur: code, libelle: NOMS_LANGUES[code] ?? code }))}
              onChange={(code) => void changerLangue(code)}
            />
            <Selecteur
              etiquette={t("commun.theme")}
              valeur={theme}
              options={THEMES.map((valeur) => ({ valeur, libelle: t(`commun.theme_${valeur}`) }))}
              onChange={(choisi) => {
                definirTheme(choisi as Theme);
                appliquerTheme(choisi as Theme);
              }}
            />
          </div>
        </div>
      </header>
      <main id="contenu" className="contenu" tabIndex={-1}>
        {echecSortie && <Message variante="danger">{echecSortie}</Message>}
        <Outlet />
      </main>
    </>
  );
}
