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
        <Link to="/" className="entete__marque">
          {t("accueil.titre")}
        </Link>
        {moi && moi.projets.length > 0 && (
          <label className="reglage">
            <span className="reglage__nom">{t("projets.choisir")}</span>
            <select
              value={courant?.params.projetId ?? ""}
              onChange={(e) =>
                void (e.target.value
                  ? navigate({ to: "/projets/$projetId", params: { projetId: e.target.value } })
                  : navigate({ to: "/" }))
              }
              className="reglage__choix"
            >
              <option value="">{t("projets.tous")}</option>
              {moi.projets.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.code} — {libelleProjet(p, i18n.language)}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="entete__reglages">
          <label className="reglage">
            <span className="reglage__nom">{t("commun.langue")}</span>
            <select
              value={i18n.language}
              onChange={(e) => void changerLangue(e.target.value)}
              className="reglage__choix"
            >
              {langues.map((code) => (
                <option key={code} value={code}>
                  {NOMS_LANGUES[code]}
                </option>
              ))}
            </select>
          </label>
          <label className="reglage">
            <span className="reglage__nom">{t("commun.theme")}</span>
            <select
              value={theme}
              onChange={(e) => {
                const choisi = e.target.value as Theme;
                definirTheme(choisi);
                appliquerTheme(choisi);
              }}
              className="reglage__choix"
            >
              {THEMES.map((valeur) => (
                <option key={valeur} value={valeur}>
                  {t(`commun.theme_${valeur}`)}
                </option>
              ))}
            </select>
          </label>
          {moi && (
            <div className="compte">
              <span className="compte__nom">
                <span className="visuellement-cache">{t("session.compte")} : </span>
                {moi.nom_complet}
                {moi.organisation && <small className="technique"> · {moi.organisation.code}</small>}
              </span>
              <Bouton variante="secondaire" onClick={() => void sortir()}>
                {t("session.deconnexion")}
              </Bouton>
            </div>
          )}
        </div>
      </header>
      <main id="contenu" className="contenu" tabIndex={-1}>
        {echecSortie && <Message variante="danger">{echecSortie}</Message>}
        <Outlet />
      </main>
    </>
  );
}
