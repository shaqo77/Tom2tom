import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ErreurApi } from "../../shared/api/client";
import { peut, projetParId } from "../../shared/session/droits";
import { useMoi } from "../../shared/session/moi";
import { Bouton } from "../../shared/ui/Bouton";
import { Carte } from "../../shared/ui/Carte";
import { Champ } from "../../shared/ui/Champ";
import { Chargement } from "../../shared/ui/Chargement";
import { Message } from "../../shared/ui/Message";
import { Pastille } from "../../shared/ui/Pastille";
import { Selecteur } from "../../shared/ui/Selecteur";
import { lireCles } from "../cles/api";
import { libelleProjet } from "../projets/libelle";
import { comptabiliserEcriture, creerEcriture, lireEcriture, lireEcritures, validerEcriture } from "./api";
import { construireEcriture, ecritureVide, ligneVide, totaux } from "./saisie";
import type { Faute, SaisieEcriture, SaisieLigne } from "./saisie";
import type { EcritureDetail, StatutEcriture } from "./types";
import "./ecritures.css";

const STATUTS: StatutEcriture[] = ["draft", "validated", "posted", "locked"];
const VARIANTE: Record<StatutEcriture, "attention" | "accent" | "succes" | "neutre"> = {
  draft: "attention",
  validated: "accent",
  posted: "succes",
  locked: "neutre",
};

function texteErreur(erreur: unknown, secours: string): string {
  return erreur instanceof ErreurApi && erreur.message ? erreur.message : secours;
}

/**
 * Les écritures d'un projet : lister, saisir un brouillon (une ligne peut suivre une clé de cofinancement, le
 * serveur la ventile entre les accords), valider, comptabiliser. Le serveur reste l'autorité : équilibre,
 * période ouverte, séparation des tâches ; son refus est affiché tel quel.
 */
export function Ecritures() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const { data: moi } = useMoi();
  const { projet: projetId, ecriture: ecritureId } = useSearch({ from: "/protege/ecritures" });
  const navigate = useNavigate();
  const projet = projetId ? projetParId(moi, projetId) : undefined;
  const aller = (search: { projet?: string; ecriture?: string }) => void navigate({ to: "/ecritures", search, replace: true });
  const [statut, definirStatut] = useState<StatutEcriture | "">("");
  const [saisie, definirSaisie] = useState(false);
  const [information, definirInformation] = useState<string | null>(null);
  const liste = useQuery({ queryKey: ["ecritures", projetId, statut], queryFn: () => lireEcritures(projetId!, statut), enabled: Boolean(projetId) });

  return (
    <>
      <div className="page__entete">
        <h1>{t("ecritures.titre")}</h1>
        <p>{t("ecritures.intro")}</p>
      </div>
      <Carte>
        <Selecteur
          etiquette={t("ecritures.projet")}
          valeur={projetId ?? ""}
          options={[
            { valeur: "", libelle: t("ecritures.choisir_projet") },
            ...(moi?.projets ?? []).map((p) => ({ valeur: p.id, libelle: `${p.code} · ${libelleProjet(p, i18n.language)}` })),
          ]}
          onChange={(v) => {
            definirSaisie(false);
            aller(v ? { projet: v } : {});
          }}
        />
      </Carte>

      {information && <Message variante="succes">{information}</Message>}

      {projetId && peut(projet, "saisir") && !saisie && (
        <div className="ecritures__actions">
          <Bouton onClick={() => { definirInformation(null); definirSaisie(true); }}>{t("ecritures.nouvelle")}</Bouton>
        </div>
      )}
      {projetId && saisie && (
        <FormulaireEcriture
          projetId={projetId}
          surAnnulation={() => definirSaisie(false)}
          surTermine={(e) => {
            definirSaisie(false);
            definirInformation(t("ecritures.creee"));
            void queryClient.invalidateQueries({ queryKey: ["ecritures", projetId] });
            aller({ projet: projetId, ecriture: e.id });
          }}
        />
      )}

      {projetId && (
        <Carte titre={t("ecritures.liste")}>
          <Selecteur
            etiquette={t("ecritures.filtre_statut")}
            valeur={statut}
            options={[{ valeur: "", libelle: t("ecritures.tous") }, ...STATUTS.map((s) => ({ valeur: s, libelle: t(`ecritures.statut.${s}`) }))]}
            onChange={(v) => definirStatut(v as StatutEcriture | "")}
          />
          {liste.isPending && <Chargement />}
          {liste.error && <Message variante="danger">{texteErreur(liste.error, t("ecritures.erreur_lecture"))}</Message>}
          {liste.data && liste.data.length === 0 && <p>{t("ecritures.vide")}</p>}
          {liste.data && liste.data.length > 0 && (
            <div className="ecritures__defilement">
              <table className="ecritures__tableau">
                <caption className="visuellement-cache">{t("ecritures.liste")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("ecritures.col_numero")}</th>
                    <th scope="col">{t("ecritures.col_journal")}</th>
                    <th scope="col">{t("ecritures.col_date")}</th>
                    <th scope="col">{t("ecritures.col_libelle")}</th>
                    <th scope="col">{t("ecritures.col_statut")}</th>
                    <th scope="col">{t("ecritures.col_action")}</th>
                  </tr>
                </thead>
                <tbody>
                  {liste.data.map((e) => (
                    <tr key={e.id} aria-current={e.id === ecritureId ? "true" : undefined}>
                      <th scope="row" className="technique">{e.number ?? "—"}</th>
                      <td>{e.journal}</td>
                      <td>{e.date_comptable}</td>
                      <td>{e.label}</td>
                      <td>
                        <Pastille variante={VARIANTE[e.status]}>{t(`ecritures.statut.${e.status}`)}</Pastille>
                      </td>
                      <td>
                        <Bouton variante="secondaire" aria-label={t("ecritures.ouvrir", { libelle: e.label })} onClick={() => aller({ projet: projetId, ecriture: e.id })}>
                          {t("ecritures.ouvrir", { libelle: e.label })}
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

      {projetId && ecritureId && <DetailEcriture key={ecritureId} projetId={projetId} ecritureId={ecritureId} peutValider={peut(projet, "valider")} peutComptabiliser={peut(projet, "comptabiliser")} />}
    </>
  );
}

function DetailEcriture({ projetId, ecritureId, peutValider, peutComptabiliser }: { projetId: string; ecritureId: string; peutValider: boolean; peutComptabiliser: boolean }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const cle = ["ecriture", projetId, ecritureId];
  const detail = useQuery({ queryKey: cle, queryFn: () => lireEcriture(projetId, ecritureId) });
  const [echec, definirEchec] = useState<string | null>(null);
  const [avertissements, definirAvertissements] = useState<string[]>([]);
  const enVol = useRef(false);
  const action = useMutation({
    mutationFn: (quoi: "valider" | "comptabiliser") => (quoi === "valider" ? validerEcriture(projetId, ecritureId) : comptabiliserEcriture(projetId, ecritureId)),
    onSuccess: (e: EcritureDetail) => {
      queryClient.setQueryData(cle, e);
      definirAvertissements(e.avertissements ?? []);
      void queryClient.invalidateQueries({ queryKey: ["ecritures", projetId] });
    },
    onError: (e) => definirEchec(texteErreur(e, t("erreur.inconnue"))),
    onSettled: () => {
      enVol.current = false;
    },
  });
  function lancer(quoi: "valider" | "comptabiliser") {
    if (enVol.current) return;
    enVol.current = true;
    definirEchec(null);
    definirAvertissements([]);
    action.mutate(quoi);
  }
  if (detail.isPending) return <Chargement />;
  if (detail.error) return <Message variante="danger">{texteErreur(detail.error, t("ecritures.erreur_lecture"))}</Message>;
  const e = detail.data;
  return (
    <Carte>
      <h2 className="carte__titre">{t("ecritures.detail", { libelle: e.label })}</h2>
      <p className="ecritures__ligne">
        <Pastille variante={VARIANTE[e.status]}>{t(`ecritures.statut.${e.status}`)}</Pastille>
        <span className="technique">{e.number ?? t("ecritures.sans_numero")}</span>
        <span>{e.journal}</span>
        <span>{e.date_comptable}</span>
        <span>{e.devise}</span>
      </p>
      <div className="ecritures__defilement">
        <table className="ecritures__tableau">
          <caption className="visuellement-cache">{t("ecritures.lignes")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("ecritures.col_compte")}</th>
              <th scope="col">{t("ecritures.col_libelle")}</th>
              <th scope="col">{t("ecritures.col_accord")}</th>
              <th scope="col">{t("ecritures.col_debit")}</th>
              <th scope="col">{t("ecritures.col_credit")}</th>
            </tr>
          </thead>
          <tbody>
            {e.lignes.map((l) => (
              <tr key={l.line_no}>
                <th scope="row" className="technique">{l.compte}</th>
                <td>{l.label || "—"}</td>
                <td>{l.accord ?? "—"}</td>
                <td className="ecritures__montant">{l.debit}</td>
                <td className="ecritures__montant">{l.credit}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" colSpan={3}>{t("ecritures.totaux")}</th>
              <td className="ecritures__montant">{e.total_debit}</td>
              <td className="ecritures__montant">{e.total_credit}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      {echec && <Message variante="danger">{echec}</Message>}
      {avertissements.length > 0 && (
        <Message variante="attention">
          {t("ecritures.avertissements")}
          <ul>
            {avertissements.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </Message>
      )}
      <div className="ecritures__actions">
        {e.status === "draft" && peutValider && (
          <Bouton chargement={action.isPending} onClick={() => lancer("valider")}>
            {t("ecritures.valider")}
          </Bouton>
        )}
        {e.status === "validated" && peutComptabiliser && (
          <Bouton chargement={action.isPending} onClick={() => lancer("comptabiliser")}>
            {t("ecritures.comptabiliser")}
          </Bouton>
        )}
      </div>
    </Carte>
  );
}

function FormulaireEcriture({ projetId, surTermine, surAnnulation }: { projetId: string; surTermine: (e: EcritureDetail) => void; surAnnulation: () => void }) {
  const { t, i18n } = useTranslation();
  const cles = useQuery({ queryKey: ["cles-saisie", projetId], queryFn: () => lireCles(projetId) });
  const [saisie, definirSaisie] = useState<SaisieEcriture>(ecritureVide);
  const [fautes, definirFautes] = useState<Faute[]>([]);
  const [echec, definirEchec] = useState<string | null>(null);
  // Une clé d'idempotence par formulaire : un envoi répété (réseau, double clic) ne crée qu'une pièce.
  const idempotence = useRef(globalThis.crypto?.randomUUID?.());
  const ecriture = useMutation({
    mutationFn: (corps: Record<string, unknown>) => creerEcriture(projetId, corps),
    onSuccess: surTermine,
    onError: (e) => definirEchec(texteErreur(e, t("erreur.inconnue"))),
  });
  const total = totaux(saisie.lignes, i18n.language);
  const ligne = (i: number, champ: Partial<SaisieLigne>) => definirSaisie((s) => ({ ...s, lignes: s.lignes.map((l, j) => (j === i ? { ...l, ...champ } : l)) }));

  function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    definirEchec(null);
    if (ecriture.isPending) return;
    const r = construireEcriture(saisie, i18n.language);
    if (!r.ok) return definirFautes(r.fautes);
    definirFautes([]);
    ecriture.mutate(idempotence.current ? { ...r.corps, cle_idempotence: idempotence.current } : r.corps);
  }

  return (
    <Carte titre={t("ecritures.form.titre")}>
      <form className="ecritures__form" onSubmit={soumettre} noValidate>
        {fautes.length > 0 && (
          <Message variante="attention">
            {t("ecritures.form.a_corriger")}
            <ul>
              {fautes.map((f, i) => (
                <li key={`${f.cle}-${i}`}>{t(f.cle, f.params ?? {})}</li>
              ))}
            </ul>
          </Message>
        )}
        {echec && <Message variante="danger">{echec}</Message>}
        {cles.error && <Message variante="danger">{texteErreur(cles.error, t("ecritures.form.erreur_cles"))}</Message>}
        <Champ etiquette={t("ecritures.form.journal")} autoComplete="off" value={saisie.journal} onChange={(e) => definirSaisie((s) => ({ ...s, journal: e.target.value }))} />
        <Champ etiquette={t("ecritures.form.date")} type="date" value={saisie.date} onChange={(e) => definirSaisie((s) => ({ ...s, date: e.target.value }))} />
        <Champ etiquette={t("ecritures.form.libelle")} autoComplete="off" value={saisie.libelle} onChange={(e) => definirSaisie((s) => ({ ...s, libelle: e.target.value }))} />
        <Champ etiquette={t("ecritures.form.reference")} autoComplete="off" value={saisie.reference} onChange={(e) => definirSaisie((s) => ({ ...s, reference: e.target.value }))} />

        {saisie.lignes.map((l, i) => {
          const n = String(i + 1);
          return (
            <fieldset key={i} className="ecritures__groupe">
              <legend>{t("ecritures.form.ligne", { n })}</legend>
              <Champ etiquette={t("ecritures.form.compte", { n })} autoComplete="off" value={l.compte} onChange={(e) => ligne(i, { compte: e.target.value })} />
              <Champ etiquette={t("ecritures.form.debit", { n })} inputMode="decimal" autoComplete="off" value={l.debit} onChange={(e) => ligne(i, { debit: e.target.value })} />
              <Champ etiquette={t("ecritures.form.credit", { n })} inputMode="decimal" autoComplete="off" value={l.credit} onChange={(e) => ligne(i, { credit: e.target.value })} />
              <Champ etiquette={t("ecritures.form.libelle_ligne", { n })} autoComplete="off" value={l.label} onChange={(e) => ligne(i, { label: e.target.value })} />
              <Selecteur
                etiquette={t("ecritures.form.cle", { n })}
                valeur={l.cle}
                options={[{ valeur: "", libelle: t("ecritures.form.aucune_cle") }, ...(cles.data ?? []).map((c) => ({ valeur: c.code, libelle: c.code }))]}
                onChange={(v) => ligne(i, { cle: v })}
              />
              <Champ etiquette={t("ecritures.form.accord", { n })} autoComplete="off" value={l.accord} onChange={(e) => ligne(i, { accord: e.target.value })} />
              {saisie.lignes.length > 2 && (
                <Bouton variante="secondaire" aria-label={t("ecritures.form.retirer_ligne", { n })} onClick={() => definirSaisie((s) => ({ ...s, lignes: s.lignes.filter((_, j) => j !== i) }))}>
                  {t("ecritures.form.retirer")}
                </Bouton>
              )}
            </fieldset>
          );
        })}
        <Bouton variante="secondaire" onClick={() => definirSaisie((s) => ({ ...s, lignes: [...s.lignes, ligneVide()] }))}>
          {t("ecritures.form.ajouter_ligne")}
        </Bouton>

        <p role="status" className="ecritures__totaux">
          {t("ecritures.form.totaux", { debit: total.debit, credit: total.credit })} {total.equilibre ? t("ecritures.form.equilibree") : t("ecritures.form.ecart")}
        </p>
        <div className="ecritures__actions">
          <Bouton type="submit" chargement={ecriture.isPending}>
            {t("ecritures.form.enregistrer")}
          </Bouton>
          <Bouton variante="secondaire" disabled={ecriture.isPending} onClick={surAnnulation}>
            {t("ecritures.form.annuler")}
          </Bouton>
        </div>
      </form>
    </Carte>
  );
}
