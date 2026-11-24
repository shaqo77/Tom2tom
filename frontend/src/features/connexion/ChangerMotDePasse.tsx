import type { FormEvent } from "react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ErreurApi } from "../../shared/api/client";
import { changerMotDePasse } from "../../shared/session/api";
import { Bouton } from "../../shared/ui/Bouton";
import { Carte } from "../../shared/ui/Carte";
import { Champ } from "../../shared/ui/Champ";
import { Message } from "../../shared/ui/Message";
import "./connexion.css";

type Erreurs = { actuel?: string; nouveau?: string; confirmation?: string };

/**
 * Changer son mot de passe. Aucune règle de robustesse n'est codée ici : c'est le serveur qui la
 * connaît (validateurs de Django) et son message, dans la langue de la personne, est affiché tel quel.
 */
export function ChangerMotDePasse() {
  const { t } = useTranslation();
  const [actuel, definirActuel] = useState("");
  const [nouveau, definirNouveau] = useState("");
  const [confirmation, definirConfirmation] = useState("");
  const [envoi, definirEnvoi] = useState(false);
  const [erreurs, definirErreurs] = useState<Erreurs>({});
  const [echec, definirEchec] = useState<string | null>(null);
  const [change, definirChange] = useState(false);
  const refActuel = useRef<HTMLInputElement>(null);
  const refNouveau = useRef<HTMLInputElement>(null);
  const refConfirmation = useRef<HTMLInputElement>(null);

  async function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    definirEchec(null);
    definirChange(false);
    const manques: Erreurs = {
      ...(actuel ? {} : { actuel: t("mdp.actuel_requis") }),
      ...(nouveau ? {} : { nouveau: t("mdp.nouveau_requis") }),
      ...(nouveau && confirmation !== nouveau ? { confirmation: t("mdp.confirmation_differente") } : {}),
    };
    definirErreurs(manques);
    if (manques.actuel) return refActuel.current?.focus();
    if (manques.nouveau) return refNouveau.current?.focus();
    if (manques.confirmation) return refConfirmation.current?.focus();

    definirEnvoi(true);
    try {
      await changerMotDePasse(actuel, nouveau);
      definirChange(true);
    } catch (erreur) {
      // Le message du serveur (règle violée, mot de passe actuel faux) est celui que la personne lit.
      definirEchec(
        erreur instanceof ErreurApi && erreur.message
          ? erreur.message
          : t(`erreur.${erreur instanceof ErreurApi ? erreur.code : "inconnue"}`, { defaultValue: t("erreur.inconnue") }),
      );
    } finally {
      // On ne garde jamais un mot de passe à l'écran, réussi ou refusé.
      definirActuel("");
      definirNouveau("");
      definirConfirmation("");
      definirEnvoi(false);
    }
  }

  return (
    <div className="connexion">
      <Carte>
        <form onSubmit={(e) => void soumettre(e)} noValidate aria-labelledby="titre-mdp" className="connexion__formulaire">
          <div className="page__entete">
            <h1 id="titre-mdp">{t("mdp.titre")}</h1>
            <p className="page__sous-titre">{t("mdp.sous_titre")}</p>
          </div>
          {change && <Message variante="succes">{t("mdp.change")}</Message>}
          {echec && <Message variante="danger">{echec}</Message>}
          <Champ
            ref={refActuel}
            etiquette={t("mdp.actuel")}
            type="password"
            value={actuel}
            onChange={(e) => definirActuel(e.target.value)}
            autoComplete="current-password"
            {...(erreurs.actuel ? { erreur: erreurs.actuel } : {})}
          />
          <Champ
            ref={refNouveau}
            etiquette={t("mdp.nouveau")}
            type="password"
            value={nouveau}
            onChange={(e) => definirNouveau(e.target.value)}
            autoComplete="new-password"
            {...(erreurs.nouveau ? { erreur: erreurs.nouveau } : {})}
          />
          <Champ
            ref={refConfirmation}
            etiquette={t("mdp.confirmation")}
            type="password"
            value={confirmation}
            onChange={(e) => definirConfirmation(e.target.value)}
            autoComplete="new-password"
            {...(erreurs.confirmation ? { erreur: erreurs.confirmation } : {})}
          />
          <Bouton type="submit" chargement={envoi}>
            {t("mdp.valider")}
          </Bouton>
        </form>
      </Carte>
    </div>
  );
}
