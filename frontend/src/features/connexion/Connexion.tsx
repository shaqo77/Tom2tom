import { useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import type { FormEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { appliquerLangue } from "../../i18n";
import { ErreurApi } from "../../shared/api/client";
import { seConnecter } from "../../shared/session/api";
import { retourSur } from "../../shared/session/retour";
import { Bouton } from "../../shared/ui/Bouton";
import { Carte } from "../../shared/ui/Carte";
import { Champ } from "../../shared/ui/Champ";
import { Message } from "../../shared/ui/Message";
import "./connexion.css";

export function Connexion() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { retour, expiree } = useSearch({ from: "/connexion" });
  const [identifiant, definirIdentifiant] = useState("");
  const [motDePasse, definirMotDePasse] = useState("");
  const [visible, definirVisible] = useState(false);
  const [envoi, definirEnvoi] = useState(false);
  const [erreurs, definirErreurs] = useState<{ identifiant?: string; motDePasse?: string }>({});
  const [echec, definirEchec] = useState<string | null>(null);
  const refIdentifiant = useRef<HTMLInputElement>(null);
  const refMotDePasse = useRef<HTMLInputElement>(null);

  useEffect(() => refIdentifiant.current?.focus(), []);

  async function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    definirEchec(null);
    const manques = {
      ...(identifiant.trim() ? {} : { identifiant: t("connexion.identifiant_requis") }),
      ...(motDePasse ? {} : { motDePasse: t("connexion.mot_de_passe_requis") }),
    };
    definirErreurs(manques);
    if (manques.identifiant) return refIdentifiant.current?.focus();
    if (manques.motDePasse) return refMotDePasse.current?.focus();

    definirEnvoi(true);
    try {
      const moi = await seConnecter(identifiant.trim(), motDePasse);
      queryClient.setQueryData(["moi"], moi);
      await appliquerLangue(moi.langue);
      await navigate({ to: retourSur(retour) });
    } catch (erreur) {
      const code = erreur instanceof ErreurApi ? erreur.code : "inconnue";
      definirEchec(t(`erreur.${code}`, { defaultValue: t("erreur.inconnue") }));
      definirMotDePasse(""); // on ne garde jamais un mot de passe refusé à l'écran
      refMotDePasse.current?.focus();
    } finally {
      definirEnvoi(false);
    }
  }

  return (
    <div className="connexion">
      <Carte>
        <form onSubmit={(e) => void soumettre(e)} noValidate aria-labelledby="titre-connexion" className="connexion__formulaire">
          <div className="page__entete">
            <h1 id="titre-connexion">{t("connexion.titre")}</h1>
            <p className="page__sous-titre">{t("connexion.sous_titre")}</p>
          </div>
          {expiree && <Message variante="info">{t("connexion.session_expiree")}</Message>}
          {echec && <Message variante="danger">{echec}</Message>}
          <Champ
            ref={refIdentifiant}
            etiquette={t("connexion.identifiant")}
            value={identifiant}
            onChange={(e) => definirIdentifiant(e.target.value)}
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            {...(erreurs.identifiant ? { erreur: erreurs.identifiant } : {})}
          />
          <div className="connexion__mot-de-passe">
            <Champ
              ref={refMotDePasse}
              etiquette={t("connexion.mot_de_passe")}
              type={visible ? "text" : "password"}
              value={motDePasse}
              onChange={(e) => definirMotDePasse(e.target.value)}
              autoComplete="current-password"
              {...(erreurs.motDePasse ? { erreur: erreurs.motDePasse } : {})}
            />
            <button
              type="button"
              className="connexion__oeil"
              aria-pressed={visible}
              onClick={() => definirVisible((v) => !v)}
            >
              {visible ? t("connexion.masquer") : t("connexion.afficher")}
            </button>
          </div>
          <Bouton type="submit" chargement={envoi}>
            {t("connexion.valider")}
          </Bouton>
        </form>
      </Carte>
    </div>
  );
}
