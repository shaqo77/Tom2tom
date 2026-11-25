import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ErreurApi } from "../../shared/api/client";
import { peut, projetParId } from "../../shared/session/droits";
import { useMoi } from "../../shared/session/moi";
import type { ProjetAccessible } from "../../shared/session/types";
import { Bouton } from "../../shared/ui/Bouton";
import { Carte } from "../../shared/ui/Carte";
import { Champ } from "../../shared/ui/Champ";
import { Chargement } from "../../shared/ui/Chargement";
import { Message } from "../../shared/ui/Message";
import { Pastille } from "../../shared/ui/Pastille";
import { Selecteur } from "../../shared/ui/Selecteur";
import { libelleProjet } from "../projets/libelle";
import { useAction } from "./action";
import { deciderDerogation, demanderDerogation, justifier, lireDerogations, lireEvaluation, lireEvaluations, trancher } from "./api";
import { RESULTATS } from "./types";
import type { DecisionControle, Derogation, Resultat, StatutDerogation } from "./types";
import "./evaluations.css";

const VARIANTE: Record<Resultat, "succes" | "alerte" | "attention" | "neutre" | "accent"> = {
  reussi: "succes",
  bloquant: "alerte",
  avertissement: "attention",
  information: "neutre",
  a_verifier: "accent",
  non_applicable: "neutre",
};
const VARIANTE_DEROGATION: Record<StatutDerogation, "attention" | "succes" | "alerte"> = { demandee: "attention", approuvee: "succes", refusee: "alerte" };

function texteErreur(erreur: unknown, secours: string): string {
  return erreur instanceof ErreurApi && erreur.message ? erreur.message : secours;
}

/**
 * Le journal des évaluations de contrôles d'un projet et leurs suites : trancher un contrôle « à vérifier », ajouter une
 * justification, demander une dérogation (résultat bloquant, période à fin EXCLUE) et décider des dérogations. Le journal
 * est en ajout seul : chaque action ajoute une ligne, aucune n'en réécrit une. Le serveur reste l'autorité.
 */
export function Evaluations() {
  const { t, i18n } = useTranslation();
  const { data: moi } = useMoi();
  const { projet: projetId, evaluation: evaluationId } = useSearch({ from: "/protege/evaluations" });
  const navigate = useNavigate();
  const projet = projetId ? projetParId(moi, projetId) : undefined;
  const [resultat, definirResultat] = useState<"" | Resultat>("");
  const [controle, definirControle] = useState("");
  const [typeObjet, definirTypeObjet] = useState("");
  const [information, definirInformation] = useState<string | null>(null);
  const aller = (search: { projet?: string; evaluation?: string }) => void navigate({ to: "/evaluations", search, replace: true });
  const liste = useQuery({
    queryKey: ["evaluations", projetId, resultat, controle, typeObjet],
    queryFn: () => lireEvaluations(projetId!, { ...(resultat ? { resultat } : {}), ...(controle.trim() ? { controle: controle.trim() } : {}), ...(typeObjet.trim() ? { objet_type: typeObjet.trim() } : {}) }),
    enabled: Boolean(projetId),
  });

  return (
    <>
      <div className="page__entete">
        <h1>{t("evaluations.titre")}</h1>
        <p>{t("evaluations.intro")}</p>
      </div>
      <Carte>
        <Selecteur
          etiquette={t("evaluations.projet")}
          valeur={projetId ?? ""}
          options={[
            { valeur: "", libelle: t("evaluations.choisir_projet") },
            ...(moi?.projets ?? []).map((p) => ({ valeur: p.id, libelle: `${p.code} · ${libelleProjet(p, i18n.language)}` })),
          ]}
          onChange={(v) => aller(v ? { projet: v } : {})}
        />
      </Carte>

      {information && <Message variante="succes">{information}</Message>}

      {projetId && (
        <Carte titre={t("evaluations.journal")}>
          <div className="evaluations__filtres">
            <Selecteur
              etiquette={t("evaluations.filtre_resultat")}
              valeur={resultat}
              options={[{ valeur: "", libelle: t("evaluations.tous_resultats") }, ...RESULTATS.map((r) => ({ valeur: r, libelle: t(`evaluations.resultat.${r}`) }))]}
              onChange={(v) => definirResultat(v as "" | Resultat)}
            />
            <Champ etiquette={t("evaluations.filtre_controle")} value={controle} onChange={(e) => definirControle(e.target.value)} autoComplete="off" />
            <Champ etiquette={t("evaluations.filtre_objet")} value={typeObjet} onChange={(e) => definirTypeObjet(e.target.value)} autoComplete="off" />
          </div>
          {liste.isPending && <Chargement />}
          {liste.error && <Message variante="danger">{texteErreur(liste.error, t("evaluations.erreur_lecture"))}</Message>}
          {liste.data && liste.data.length === 0 && <p>{t("evaluations.vide")}</p>}
          {liste.data && liste.data.length > 0 && (
            <div className="evaluations__defilement">
              <table className="evaluations__tableau">
                <caption className="visuellement-cache">{t("evaluations.journal")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("evaluations.col_date")}</th>
                    <th scope="col">{t("evaluations.col_controle")}</th>
                    <th scope="col">{t("evaluations.col_resultat")}</th>
                    <th scope="col">{t("evaluations.col_objet")}</th>
                    <th scope="col">{t("evaluations.col_message")}</th>
                    <th scope="col">{t("evaluations.col_action")}</th>
                  </tr>
                </thead>
                <tbody>
                  {liste.data.map((e) => (
                    <tr key={e.id} aria-current={e.id === evaluationId ? "true" : undefined}>
                      <td>{e.evaluee_le.slice(0, 16).replace("T", " ")}</td>
                      <th scope="row" className="technique">{e.controle}</th>
                      <td>
                        <Pastille variante={VARIANTE[e.resultat]}>{t(`evaluations.resultat.${e.resultat}`)}</Pastille>
                      </td>
                      <td>{e.objet_type}</td>
                      <td>{e.message}</td>
                      <td>
                        <Bouton variante="secondaire" aria-label={t("evaluations.ouvrir", { controle: e.controle })} onClick={() => { definirInformation(null); aller({ projet: projetId, evaluation: e.id }); }}>
                          {t("evaluations.ouvrir_court")}
                        </Bouton>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Carte>
      )}

      {projetId && evaluationId && <DetailEvaluation key={evaluationId} projetId={projetId} evaluationId={evaluationId} projet={projet} surSucces={definirInformation} />}
      {projetId && <ListeDerogations projetId={projetId} peutValider={peut(projet, "valider")} surSucces={definirInformation} />}
    </>
  );
}

function DetailEvaluation({ projetId, evaluationId, projet, surSucces }: { projetId: string; evaluationId: string; projet: ProjetAccessible | undefined; surSucces: (t: string | null) => void }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const cle = ["evaluation", projetId, evaluationId];
  const detail = useQuery({ queryKey: cle, queryFn: () => lireEvaluation(projetId, evaluationId) });
  const rafraichir = () => {
    void queryClient.invalidateQueries({ queryKey: cle });
    void queryClient.invalidateQueries({ queryKey: ["evaluations", projetId] });
    void queryClient.invalidateQueries({ queryKey: ["derogations", projetId] });
  };
  if (detail.isPending) return <Chargement />;
  if (detail.error) return <Message variante="danger">{texteErreur(detail.error, t("evaluations.erreur_lecture"))}</Message>;
  const e = detail.data;
  const action = e.action_corrective?.[i18n.language === "en" ? "en" : "fr"] ?? e.action_corrective?.fr;
  return (
    <Carte>
      <h2 className="carte__titre">{t("evaluations.detail", { code: e.controle, version: e.controle_version })}</h2>
      <p className="evaluations__ligne">
        <Pastille variante={VARIANTE[e.resultat]}>{t(`evaluations.resultat.${e.resultat}`)}</Pastille>
        <span className="technique">{e.objet_type}</span>
      </p>
      <p>{e.message}</p>
      {e.valeur_constatee !== null && <p>{t("evaluations.constate", { valeur: e.valeur_constatee })}</p>}
      {e.valeur_attendue !== null && <p>{t("evaluations.attendu", { valeur: e.valeur_attendue })}</p>}
      {action && (
        <>
          <h3>{t("evaluations.action_corrective")}</h3>
          <p>{action}</p>
        </>
      )}

      <h3>{t("evaluations.decisions")}</h3>
      {e.decisions.length === 0 ? <p>{t("evaluations.aucune_decision")}</p> : (
        <ul className="evaluations__liste">
          {e.decisions.map((d) => (
            <li key={d.decided_at}>{`${t(`evaluations.decision.${d.decision}`)} : ${d.motif}`}</li>
          ))}
        </ul>
      )}
      {e.resultat === "a_verifier" && (peut(projet, "valider") ? <FormulaireDecision projetId={projetId} evaluationId={evaluationId} surSucces={(m) => { surSucces(m); rafraichir(); }} /> : <p>{t("evaluations.lecture_seule_decision")}</p>)}

      <h3>{t("evaluations.justifications")}</h3>
      {e.justifications.length === 0 ? <p>{t("evaluations.aucune_justification")}</p> : (
        <ul className="evaluations__liste">
          {e.justifications.map((j) => (
            <li key={j.created_at}>
              <span>{j.texte}</span> <small>{j.auteur}</small>
            </li>
          ))}
        </ul>
      )}
      {peut(projet, "saisir") && <FormulaireJustification projetId={projetId} evaluationId={evaluationId} surSucces={(m) => { surSucces(m); rafraichir(); }} />}

      <h3>{t("evaluations.derogations_evaluation")}</h3>
      {e.derogations.length === 0 ? <p>{t("evaluations.aucune_derogation")}</p> : (
        <ul className="evaluations__liste">
          {e.derogations.map((d) => (
            <li key={d.id}>{`${t(`evaluations.statut.${d.statut}`)} · ${d.valide_du} → ${d.valide_jusquau} (${t("evaluations.exclu")})`}</li>
          ))}
        </ul>
      )}
      {e.resultat === "bloquant" && peut(projet, "saisir") && <FormulaireDerogation projetId={projetId} evaluationId={evaluationId} surSucces={(m) => { surSucces(m); rafraichir(); }} />}
    </Carte>
  );
}

function FormulaireDecision({ projetId, evaluationId, surSucces }: { projetId: string; evaluationId: string; surSucces: (m: string) => void }) {
  const { t } = useTranslation();
  const [decision, definirDecision] = useState<DecisionControle>("conforme");
  const [motif, definirMotif] = useState("");
  const action = useAction(() => trancher(projetId, evaluationId, decision, motif.trim()), () => { definirMotif(""); surSucces(t("evaluations.decision_ok")); }, t);
  return (
    <form className="evaluations__formulaire" onSubmit={(ev: FormEvent) => { ev.preventDefault(); action.lancer(); }} noValidate>
      {action.echec && <Message variante="danger">{action.echec}</Message>}
      <Selecteur etiquette={t("evaluations.decision_champ")} valeur={decision} options={(["conforme", "non_conforme"] as const).map((d) => ({ valeur: d, libelle: t(`evaluations.decision.${d}`) }))} onChange={(v) => definirDecision(v as DecisionControle)} />
      <Champ etiquette={t("evaluations.motif_decision")} value={motif} onChange={(e) => definirMotif(e.target.value)} />
      <Bouton type="submit" chargement={action.attente}>{t("evaluations.enregistrer_decision")}</Bouton>
    </form>
  );
}

function FormulaireJustification({ projetId, evaluationId, surSucces }: { projetId: string; evaluationId: string; surSucces: (m: string) => void }) {
  const { t } = useTranslation();
  const [texte, definirTexte] = useState("");
  const [manquant, definirManquant] = useState(false);
  const action = useAction(() => justifier(projetId, evaluationId, texte.trim()), () => { definirTexte(""); surSucces(t("evaluations.justification_ok")); }, t);
  function soumettre(ev: FormEvent) {
    ev.preventDefault();
    if (!texte.trim()) return definirManquant(true);
    definirManquant(false);
    action.lancer();
  }
  return (
    <form className="evaluations__formulaire" onSubmit={soumettre} noValidate>
      {action.echec && <Message variante="danger">{action.echec}</Message>}
      <Champ etiquette={t("evaluations.justification_champ")} value={texte} onChange={(e) => definirTexte(e.target.value)} {...(manquant ? { erreur: t("evaluations.justification_requise") } : {})} />
      <Bouton type="submit" chargement={action.attente}>{t("evaluations.ajouter_justification")}</Bouton>
    </form>
  );
}

function FormulaireDerogation({ projetId, evaluationId, surSucces }: { projetId: string; evaluationId: string; surSucces: (m: string) => void }) {
  const { t } = useTranslation();
  const [motif, definirMotif] = useState("");
  const [justificatif, definirJustificatif] = useState("");
  const [du, definirDu] = useState("");
  const [jusquau, definirJusquau] = useState("");
  const [probleme, definirProbleme] = useState<string | null>(null);
  const action = useAction(
    () => demanderDerogation(projetId, evaluationId, { motif: motif.trim(), justificatif: justificatif.trim(), valide_du: du, valide_jusquau: jusquau }),
    () => surSucces(t("evaluations.derogation_ok")),
    t,
  );
  function soumettre(ev: FormEvent) {
    ev.preventDefault();
    const erreur = !motif.trim() ? t("evaluations.motif_derogation_requis") : !justificatif.trim() ? t("evaluations.justificatif_requis") : !du || !jusquau ? t("evaluations.dates_requises") : du >= jusquau ? t("evaluations.periode_vide") : null;
    definirProbleme(erreur);
    if (erreur) return;
    action.lancer();
  }
  return (
    <form className="evaluations__formulaire" onSubmit={soumettre} noValidate>
      <h4>{t("evaluations.demander_derogation_titre")}</h4>
      {probleme && <Message variante="attention">{probleme}</Message>}
      {action.echec && <Message variante="danger">{action.echec}</Message>}
      <Champ etiquette={t("evaluations.motif_derogation")} value={motif} onChange={(e) => definirMotif(e.target.value)} />
      <Champ etiquette={t("evaluations.justificatif")} value={justificatif} onChange={(e) => definirJustificatif(e.target.value)} />
      <Champ etiquette={t("evaluations.valable_du")} type="date" value={du} onChange={(e) => definirDu(e.target.value)} />
      <Champ etiquette={t("evaluations.jusquau")} type="date" value={jusquau} onChange={(e) => definirJusquau(e.target.value)} />
      <Bouton type="submit" chargement={action.attente}>{t("evaluations.demander_derogation")}</Bouton>
    </form>
  );
}

function ListeDerogations({ projetId, peutValider, surSucces }: { projetId: string; peutValider: boolean; surSucces: (m: string | null) => void }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const liste = useQuery({ queryKey: ["derogations", projetId], queryFn: () => lireDerogations(projetId) });
  const [choix, definirChoix] = useState<{ derogation: Derogation; approuver: boolean } | null>(null);
  const [motif, definirMotif] = useState("");
  const action = useAction(
    () => deciderDerogation(projetId, choix!.derogation.id, choix!.approuver, motif.trim()),
    () => {
      surSucces(t(choix!.approuver ? "evaluations.approuvee_ok" : "evaluations.refusee_ok"));
      definirChoix(null);
      definirMotif("");
      void queryClient.invalidateQueries({ queryKey: ["derogations", projetId] });
    },
    t,
  );
  return (
    <Carte titre={t("evaluations.derogations")}>
      {liste.isPending && <Chargement />}
      {liste.error && <Message variante="danger">{texteErreur(liste.error, t("evaluations.erreur_lecture"))}</Message>}
      {action.echec && <Message variante="danger">{action.echec}</Message>}
      {liste.data && liste.data.length === 0 && <p>{t("evaluations.derogations_vide")}</p>}
      {liste.data && liste.data.length > 0 && (
        <div className="evaluations__defilement">
          <table className="evaluations__tableau">
            <caption className="visuellement-cache">{t("evaluations.derogations")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("evaluations.col_controle")}</th>
                <th scope="col">{t("evaluations.col_statut")}</th>
                <th scope="col">{t("evaluations.col_periode")}</th>
                <th scope="col">{t("evaluations.col_motif")}</th>
                <th scope="col">{t("evaluations.col_action")}</th>
              </tr>
            </thead>
            <tbody>
              {liste.data.map((d) => (
                <tr key={d.id}>
                  <th scope="row" className="technique">{d.controle}</th>
                  <td>
                    <Pastille variante={VARIANTE_DEROGATION[d.statut]}>{t(`evaluations.statut.${d.statut}`)}</Pastille>
                  </td>
                  <td>{`${d.valide_du} → ${d.valide_jusquau} (${t("evaluations.exclu")})`}</td>
                  <td>{d.motif}</td>
                  <td>
                    {d.statut === "demandee" && peutValider && (
                      <div className="evaluations__actions">
                        <Bouton variante="secondaire" aria-label={t("evaluations.approuver", { controle: d.controle })} onClick={() => definirChoix({ derogation: d, approuver: true })}>{t("evaluations.approuver_court")}</Bouton>
                        <Bouton variante="secondaire" aria-label={t("evaluations.refuser", { controle: d.controle })} onClick={() => definirChoix({ derogation: d, approuver: false })}>{t("evaluations.refuser_court")}</Bouton>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {choix && (
        <form className="evaluations__formulaire" onSubmit={(ev: FormEvent) => { ev.preventDefault(); action.lancer(); }} noValidate>
          <Champ etiquette={t("evaluations.motif_decision")} value={motif} onChange={(e) => definirMotif(e.target.value)} />
          <div className="evaluations__actions">
            <Bouton type="submit" chargement={action.attente}>{t(choix.approuver ? "evaluations.confirmer_approbation" : "evaluations.confirmer_refus")}</Bouton>
            <Bouton variante="secondaire" disabled={action.attente} onClick={() => definirChoix(null)}>{t("evaluations.renoncer")}</Bouton>
          </div>
        </form>
      )}
    </Carte>
  );
}
