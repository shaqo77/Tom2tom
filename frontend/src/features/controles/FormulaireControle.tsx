import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ErreurApi } from "../../shared/api/client";
import { Bouton } from "../../shared/ui/Bouton";
import { Carte } from "../../shared/ui/Carte";
import { Champ } from "../../shared/ui/Champ";
import { Chargement } from "../../shared/ui/Chargement";
import { Message } from "../../shared/ui/Message";
import { Selecteur } from "../../shared/ui/Selecteur";
import { creerControle, lireLangage } from "./api";
import { conditionVide, construireControle, controleVide, operateursDuChamp, saisieDe } from "./creation";
import type { Faute, SaisieCondition, SaisieControle } from "./creation";
import type { ControleDetail, Langage, Severite } from "./types";

function texteErreur(erreur: unknown, secours: string): string {
  return erreur instanceof ErreurApi && erreur.message ? erreur.message : secours;
}

/**
 * Crée un contrôle sur mesure, en BROUILLON, par un formulaire guidé : un champ, un opérateur, une valeur. Jamais de
 * texte libre pour la règle. Les champs et les opérateurs viennent du serveur (`/controles/langage/`) : l'écran ne
 * propose que ce que l'enregistrement acceptera, et le serveur valide quand même.
 */
export function FormulaireControle({ projetId, surTermine, surAnnulation }: { projetId: string; surTermine: (c: ControleDetail) => void; surAnnulation: () => void }) {
  const { t, i18n } = useTranslation();
  const langage = useQuery({ queryKey: ["langage-controles"], queryFn: lireLangage });
  if (langage.isPending) return <Chargement />;
  if (langage.error) return <Message variante="danger">{texteErreur(langage.error, t("controles.form.erreur_langage"))}</Message>;
  return <Formulaire projetId={projetId} langage={langage.data} langue={i18n.language} surTermine={surTermine} surAnnulation={surAnnulation} />;
}

function Formulaire({ projetId, langage, langue, surTermine, surAnnulation }: { projetId: string; langage: Langage; langue: string; surTermine: (c: ControleDetail) => void; surAnnulation: () => void }) {
  const { t } = useTranslation();
  const [saisie, definirSaisie] = useState<SaisieControle>(controleVide);
  const [fautes, definirFautes] = useState<Faute[]>([]);
  const [echec, definirEchec] = useState<string | null>(null);
  const ecriture = useMutation({
    mutationFn: (corps: Record<string, unknown>) => creerControle(projetId, corps),
    onSuccess: surTermine,
    onError: (e) => definirEchec(texteErreur(e, t("erreur.inconnue"))),
  });
  const champs = langage.types_regle[saisie.type_regle] ?? {};
  const modifier = (champ: Partial<SaisieControle>) => definirSaisie((s) => ({ ...s, ...champ }));
  const condition = (i: number, champ: Partial<SaisieCondition>) => definirSaisie((s) => ({ ...s, conditions: s.conditions.map((c, j) => (j === i ? { ...c, ...champ } : c)) }));

  function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    definirEchec(null);
    if (ecriture.isPending) return;
    const r = construireControle(saisie, langage, langue);
    if (!r.ok) return definirFautes(r.fautes);
    definirFautes([]);
    ecriture.mutate(r.corps);
  }

  return (
    <Carte titre={t("controles.form.titre")}>
      <form className="controles__form" onSubmit={soumettre} noValidate>
        {fautes.length > 0 && (
          <Message variante="attention">
            {t("controles.form.a_corriger")}
            <ul>
              {fautes.map((f, i) => (
                <li key={`${f.cle}-${i}`}>{t(f.cle, f.params ?? {})}</li>
              ))}
            </ul>
          </Message>
        )}
        {echec && <Message variante="danger">{echec}</Message>}
        <Champ etiquette={t("controles.form.code")} autoComplete="off" value={saisie.code} onChange={(e) => modifier({ code: e.target.value })} />
        <Champ etiquette={t("controles.form.libelle_fr")} autoComplete="off" value={saisie.fr} onChange={(e) => modifier({ fr: e.target.value })} />
        <Champ etiquette={t("controles.form.libelle_en")} autoComplete="off" value={saisie.en} onChange={(e) => modifier({ en: e.target.value })} />
        <Selecteur
          etiquette={t("controles.form.type_regle")}
          valeur={saisie.type_regle}
          options={[{ valeur: "", libelle: t("controles.form.choisir_type") }, ...Object.keys(langage.types_regle).map((r) => ({ valeur: r, libelle: r }))]}
          onChange={(v) => modifier({ type_regle: v, conditions: [conditionVide()] })}
        />
        <Selecteur
          etiquette={t("controles.form.severite")}
          valeur={saisie.severity}
          options={langage.severites.map((s) => ({ valeur: s, libelle: t(`controles.severite.${s}`) }))}
          onChange={(v) => modifier({ severity: v as Severite })}
        />
        <Champ etiquette={t("controles.form.date_effet")} type="date" value={saisie.valid_from} onChange={(e) => modifier({ valid_from: e.target.value })} />
        <Champ etiquette={t("controles.form.action_fr")} autoComplete="off" value={saisie.action_fr} onChange={(e) => modifier({ action_fr: e.target.value })} />
        <Champ etiquette={t("controles.form.action_en")} autoComplete="off" value={saisie.action_en} onChange={(e) => modifier({ action_en: e.target.value })} />
        <label className="controles__case">
          <input type="checkbox" checked={saisie.manuel} onChange={(e) => modifier({ manuel: e.target.checked })} />
          {t("controles.form.manuel")}
        </label>

        {!saisie.manuel && saisie.type_regle && (
          <fieldset className="controles__groupe">
            <legend>{t("controles.form.regle")}</legend>
            <p>{t("controles.form.regle_aide")}</p>
            {saisie.conditions.map((c, i) => {
              const n = String(i + 1);
              const champ = champs[c.champ];
              const operateurs = operateursDuChamp(langage, champ);
              const demande = champ && c.op ? saisieDe(c.op, champ.type, langage) : "aucune";
              const numeriques = Object.entries(champ?.elements ?? {}).filter(([, ty]) => ty === "decimal" || ty === "entier").map(([nom]) => nom);
              return (
                <div key={i} className="controles__condition">
                  <Selecteur
                    etiquette={t("controles.form.champ", { n })}
                    valeur={c.champ}
                    options={[{ valeur: "", libelle: t("controles.form.choisir_champ") }, ...Object.keys(champs).map((nom) => ({ valeur: nom, libelle: nom }))]}
                    onChange={(v) => condition(i, { champ: v, op: "", valeur: "", valeur2: "", somme_de: "" })}
                  />
                  {champ && (
                    <Selecteur
                      etiquette={t("controles.form.operateur", { n })}
                      valeur={c.op}
                      options={[{ valeur: "", libelle: t("controles.form.choisir_operateur") }, ...operateurs.map((op) => ({ valeur: op, libelle: t(`controles.operateur.${op}`) }))]}
                      onChange={(v) => condition(i, { op: v, valeur: "", valeur2: "", somme_de: "" })}
                    />
                  )}
                  {demande === "somme" && (
                    <Selecteur
                      etiquette={t("controles.form.somme_de", { n })}
                      valeur={c.somme_de}
                      options={[{ valeur: "", libelle: t("controles.form.choisir_champ") }, ...numeriques.map((nom) => ({ valeur: nom, libelle: nom }))]}
                      onChange={(v) => condition(i, { somme_de: v })}
                    />
                  )}
                  {(demande === "valeur" || demande === "somme" || demande === "entier" || demande === "liste" || demande === "deux_dates") && (
                    <Champ
                      etiquette={t(demande === "liste" ? "controles.form.valeurs" : demande === "deux_dates" ? "controles.form.du" : "controles.form.valeur", { n })}
                      {...(champ?.type === "date" || demande === "deux_dates" ? { type: "date" as const } : { inputMode: champ?.type === "texte" ? ("text" as const) : ("decimal" as const) })}
                      autoComplete="off"
                      value={c.valeur}
                      onChange={(e) => condition(i, { valeur: e.target.value })}
                    />
                  )}
                  {demande === "deux_dates" && <Champ etiquette={t("controles.form.au", { n })} type="date" value={c.valeur2} onChange={(e) => condition(i, { valeur2: e.target.value })} />}
                  {saisie.conditions.length > 1 && (
                    <Bouton variante="secondaire" aria-label={t("controles.form.retirer_condition", { n })} onClick={() => definirSaisie((s) => ({ ...s, conditions: s.conditions.filter((_, j) => j !== i) }))}>
                      {t("controles.form.retirer")}
                    </Bouton>
                  )}
                </div>
              );
            })}
            {saisie.conditions.length < langage.max_conditions && (
              <Bouton variante="secondaire" onClick={() => definirSaisie((s) => ({ ...s, conditions: [...s.conditions, conditionVide()] }))}>
                {t("controles.form.ajouter_condition")}
              </Bouton>
            )}
          </fieldset>
        )}

        <div className="controles__actions">
          <Bouton type="submit" chargement={ecriture.isPending}>
            {t("controles.form.creer")}
          </Bouton>
          <Bouton variante="secondaire" disabled={ecriture.isPending} onClick={surAnnulation}>
            {t("controles.form.annuler")}
          </Bouton>
        </div>
      </form>
    </Carte>
  );
}
