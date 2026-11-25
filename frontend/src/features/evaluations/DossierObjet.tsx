import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ErreurApi } from "../../shared/api/client";
import { Bouton } from "../../shared/ui/Bouton";
import { Carte } from "../../shared/ui/Carte";
import { Champ } from "../../shared/ui/Champ";
import { Chargement } from "../../shared/ui/Chargement";
import { Message } from "../../shared/ui/Message";
import { lireDossier, lireEnAttente } from "./api";
import { lireObjet } from "./objet";
import { RESULTATS, STATUTS_DEROGATION } from "./types";
import type { LigneDossier } from "./types";

function texteErreur(erreur: unknown, secours: string): string {
  return erreur instanceof ErreurApi && erreur.message ? erreur.message : secours;
}

/** Le détail d'une ligne du fil : un résultat et un statut se traduisent, le texte d'une justification s'affiche tel quel. */
function detail(ligne: LigneDossier, t: (cle: string) => string): string {
  if (ligne.genre === "evaluation" && (RESULTATS as string[]).includes(ligne.detail)) return t(`evaluations.resultat.${ligne.detail}`);
  if (ligne.genre === "derogation" && (STATUTS_DEROGATION as string[]).includes(ligne.detail)) return t(`evaluations.statut.${ligne.detail}`);
  return ligne.detail;
}

/**
 * Le dossier de conformité d'un objet (une écriture, une avance…) : d'abord ce qui l'empêche d'avancer, puis le fil
 * complet — échecs, justifications, dérogations — dans l'ordre. Lecture seule : le serveur calcule, l'écran n'invente rien.
 */
export function DossierObjet({ projetId }: { projetId: string }) {
  const { t } = useTranslation();
  const [type, definirType] = useState("");
  const [id, definirId] = useState("");
  const [faute, definirFaute] = useState<string | null>(null);
  const [demande, definirDemande] = useState<{ type: string; id: string } | null>(null);
  const attente = useQuery({ queryKey: ["en-attente", projetId, demande?.type, demande?.id], queryFn: () => lireEnAttente(projetId, demande!.type, demande!.id), enabled: demande !== null });
  const dossier = useQuery({ queryKey: ["dossier-objet", projetId, demande?.type, demande?.id], queryFn: () => lireDossier(projetId, demande!.type, demande!.id), enabled: demande !== null });

  function consulter(evenement: FormEvent) {
    evenement.preventDefault();
    const r = lireObjet(type, id);
    if (!r.ok) {
      definirFaute(r.cle);
      return;
    }
    definirFaute(null);
    definirDemande({ type: r.type, id: r.id });
  }

  return (
    <Carte titre={t("evaluations.dossier.titre")}>
      <form className="evaluations__filtres" onSubmit={consulter} noValidate aria-label={t("evaluations.dossier.titre")}>
        <Champ etiquette={t("evaluations.dossier.type")} value={type} onChange={(e) => definirType(e.target.value)} autoComplete="off" />
        <Champ etiquette={t("evaluations.dossier.id")} value={id} onChange={(e) => definirId(e.target.value)} autoComplete="off" />
        <Bouton type="submit">{t("evaluations.dossier.consulter")}</Bouton>
      </form>
      {faute && <Message variante="attention">{t(faute)}</Message>}
      {demande && (
        <>
          <h3>{t("evaluations.dossier.en_attente")}</h3>
          {attente.isPending && <Chargement />}
          {attente.error && <Message variante="danger">{texteErreur(attente.error, t("evaluations.dossier.erreur"))}</Message>}
          {attente.data && attente.data.length === 0 && <p>{t("evaluations.dossier.rien_en_attente")}</p>}
          {attente.data && attente.data.length > 0 && (
            <ul>
              {attente.data.map((a) => (
                <li key={a.evaluation}>
                  <span className="technique">{a.controle}</span> — {a.raison}
                </li>
              ))}
            </ul>
          )}

          <h3>{t("evaluations.dossier.fil")}</h3>
          {dossier.isPending && <Chargement />}
          {dossier.error && <Message variante="danger">{texteErreur(dossier.error, t("evaluations.dossier.erreur"))}</Message>}
          {dossier.data && dossier.data.length === 0 && <p>{t("evaluations.dossier.fil_vide")}</p>}
          {dossier.data && dossier.data.length > 0 && (
            <div className="evaluations__defilement">
              <table className="evaluations__tableau">
                <caption className="visuellement-cache">{t("evaluations.dossier.fil")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("evaluations.col_date")}</th>
                    <th scope="col">{t("evaluations.dossier.col_genre")}</th>
                    <th scope="col">{t("evaluations.col_controle")}</th>
                    <th scope="col">{t("evaluations.dossier.col_detail")}</th>
                  </tr>
                </thead>
                <tbody>
                  {dossier.data.map((l, i) => (
                    <tr key={`${l.le}-${l.genre}-${i}`}>
                      <td>{l.le.slice(0, 16).replace("T", " ")}</td>
                      <td>{t(`evaluations.dossier.genre.${l.genre}`)}</td>
                      <th scope="row" className="technique">{l.controle}</th>
                      <td>{detail(l, t)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Carte>
  );
}
