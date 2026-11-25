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
import { lireAccord } from "../accords/api";
import { creerProfil, lireComptesDesignes, remplacerProfil } from "./api";
import { CODES_METHODE, JALONS, PIECES, construireCorps, saisieVide } from "./corps";
import type { Faute, Saisie, SaisieCompte, SaisieMethode, SaisieRegle } from "./corps";
import type { ProfilDetail, Regime } from "./types";

function texteErreur(erreur: unknown, secours: string): string {
  return erreur instanceof ErreurApi && erreur.message ? erreur.message : secours;
}

/** La saisie de départ : vide, ou celle d'un brouillon existant (ses règles, méthodes et comptes). */
function saisieDe(profil: ProfilDetail | undefined, categories: string[]): Saisie {
  const s = saisieVide(categories);
  if (!profil) return s;
  s.valid_from = profil.valid_from;
  s.regime = profil.regime;
  s.exigence = profil.exigence ?? "";
  for (const j of JALONS) s.jalons[j] = profil[j] ?? "";
  for (const m of profil.methodes) {
    if (!m.is_enabled) continue;
    s.methodes[m.method] = {
      autorisee: true,
      pieces: [...m.supporting_docs],
      seuil_complet: m.full_doc_threshold ?? "",
      min_montant: m.min_application_amount ?? "",
      min_pourcentage: m.min_application_pct_of_ceiling ?? "",
    };
  }
  for (const r of profil.regles) {
    s.regles[r.category] = {
      incluse: true,
      allocation: r.allocation,
      taux: r.funding_rate,
      assiette: r.tax_basis,
      de: r.eligibility_from ?? "",
      a: r.eligibility_to ?? "",
      revue: r.requires_prior_review,
      max_contrat: r.max_per_contract ?? "",
      fin_propre: r.fin_propre_a_la_categorie,
    };
  }
  s.comptes = profil.comptes.map((c) => ({
    compte: c.compte,
    devise: c.devise,
    genre: c.ceiling_kind,
    plafond: c.ceiling_amount ?? "",
    seuil: c.replenishment_threshold_pct ?? "",
  }));
  return s;
}

/**
 * Création ou remplacement d'un BROUILLON de profil de décaissement, d'un bloc. Tout est accepté ou rien ne change :
 * le profil entier est renvoyé à chaque fois. Les taux et montants restent des chaînes exactes ; la validation locale
 * (taux entre 0 exclu et 1, pourcentages de 0 à 100…) évite un envoi inutile, le serveur reste l'autorité.
 */
export function FormulaireProfil({
  projetId,
  accordId,
  profil,
  modele,
  surTermine,
  surAnnulation,
}: {
  projetId: string;
  accordId: string;
  profil?: ProfilDetail;
  /** Une version existante dont on repart pour en créer une nouvelle (la date d'effet est à saisir). */
  modele?: ProfilDetail;
  surTermine: (profil: ProfilDetail) => void;
  surAnnulation: () => void;
}) {
  const { t } = useTranslation();
  const accord = useQuery({ queryKey: ["accord", projetId, accordId], queryFn: () => lireAccord(projetId, accordId) });
  const comptes = useQuery({ queryKey: ["comptes-bancaires", projetId], queryFn: () => lireComptesDesignes(projetId) });
  if (accord.isPending || comptes.isPending) return <Chargement />;
  if (accord.error) return <Message variante="danger">{texteErreur(accord.error, t("profils.erreur_lecture"))}</Message>;
  const codes = accord.data.categories.map((c) => c.code);
  return (
    <Formulaire
      projetId={projetId}
      accordId={accordId}
      profil={profil}
      modele={modele}
      codes={codes}
      finEligibiliteAccord={accord.data.date_fin_eligibilite}
      comptesDesignes={(comptes.data ?? []).filter((c) => c.type === "designe")}
      surTermine={surTermine}
      surAnnulation={surAnnulation}
    />
  );
}

function Formulaire({
  projetId,
  accordId,
  profil,
  modele,
  codes,
  finEligibiliteAccord,
  comptesDesignes,
  surTermine,
  surAnnulation,
}: {
  projetId: string;
  accordId: string;
  profil: ProfilDetail | undefined;
  modele: ProfilDetail | undefined;
  codes: string[];
  finEligibiliteAccord: string | null;
  comptesDesignes: { code: string; devise: string }[];
  surTermine: (profil: ProfilDetail) => void;
  surAnnulation: () => void;
}) {
  const { t } = useTranslation();
  const [saisie, definirSaisie] = useState<Saisie>(() => (modele ? { ...saisieDe(modele, codes), valid_from: "" } : saisieDe(profil, codes)));
  const [fautes, definirFautes] = useState<Faute[]>([]);
  const [echec, definirEchec] = useState<string | null>(null);
  const ecriture = useMutation({
    mutationFn: (corps: Record<string, unknown>) => (profil ? remplacerProfil(projetId, accordId, profil.id, corps) : creerProfil(projetId, accordId, corps)),
    onSuccess: surTermine,
    onError: (e) => definirEchec(texteErreur(e, t("erreur.inconnue"))),
  });

  const modifier = (suite: (s: Saisie) => Saisie) => definirSaisie((s) => suite(structuredClone(s)));
  const methode = (code: (typeof CODES_METHODE)[number], champ: Partial<SaisieMethode>) => modifier((s) => ({ ...s, methodes: { ...s.methodes, [code]: { ...s.methodes[code], ...champ } } }));
  const regle = (code: string, champ: Partial<SaisieRegle>) => modifier((s) => ({ ...s, regles: { ...s.regles, [code]: { ...s.regles[code]!, ...champ } } }));
  const compte = (i: number, champ: Partial<SaisieCompte>) => modifier((s) => ({ ...s, comptes: s.comptes.map((c, j) => (j === i ? { ...c, ...champ } : c)) }));

  function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    definirEchec(null);
    if (ecriture.isPending) return;
    const r = construireCorps(saisie);
    if (!r.ok) return definirFautes(r.fautes);
    definirFautes([]);
    ecriture.mutate(r.corps);
  }

  return (
    <Carte titre={t(profil ? "profils.form.titre_edition" : modele ? "profils.form.titre_version" : "profils.form.titre_creation")}>
      <form className="profils__form" onSubmit={soumettre} noValidate>
        {fautes.length > 0 && (
          <Message variante="attention">
            {t("profils.form.a_corriger")}
            <ul className="profils__liste">
              {fautes.map((f, i) => (
                <li key={`${f.cle}-${i}`}>{t(f.cle, f.params ?? {})}</li>
              ))}
            </ul>
          </Message>
        )}
        {echec && <Message variante="danger">{echec}</Message>}

        <fieldset className="profils__groupe">
          <legend>{t("profils.form.generalites")}</legend>
          <Champ etiquette={t("profils.form.date_effet")} type="date" value={saisie.valid_from} onChange={(e) => modifier((s) => ({ ...s, valid_from: e.target.value }))} />
          <Selecteur etiquette={t("profils.form.regime")} valeur={saisie.regime} options={(["transaction_based", "report_based"] as const).map((r) => ({ valeur: r, libelle: t(`profils.regime.${r}`) }))} onChange={(v) => modifier((s) => ({ ...s, regime: v as Regime }))} />
          {JALONS.map((j) => (
            <Champ key={j} etiquette={t(`profils.jalon.${j}`)} type="date" value={saisie.jalons[j]} onChange={(e) => modifier((s) => ({ ...s, jalons: { ...s.jalons, [j]: e.target.value } }))} />
          ))}
        </fieldset>

        <fieldset className="profils__groupe">
          <legend>{t("profils.methodes")}</legend>
          {CODES_METHODE.map((code) => {
            const m = saisie.methodes[code];
            return (
              <div key={code} className="profils__methode">
                <label className="profils__case">
                  <input type="checkbox" checked={m.autorisee} onChange={(e) => methode(code, { autorisee: e.target.checked })} />
                  {t(`profils.methode.${code}`)}
                </label>
                {m.autorisee && (
                  <div className="profils__sous">
                    <fieldset className="profils__pieces">
                      <legend>{t("profils.form.pieces", { methode: t(`profils.methode.${code}`) })}</legend>
                      {PIECES.map((p) => (
                        <label key={p} className="profils__case">
                          <input type="checkbox" checked={m.pieces.includes(p)} onChange={(e) => methode(code, { pieces: e.target.checked ? [...m.pieces, p] : m.pieces.filter((x) => x !== p) })} />
                          {t(`profils.form.piece.${p}`)}
                        </label>
                      ))}
                    </fieldset>
                    <Champ etiquette={t("profils.form.seuil_complet", { methode: t(`profils.methode.${code}`) })} inputMode="decimal" autoComplete="off" value={m.seuil_complet} onChange={(e) => methode(code, { seuil_complet: e.target.value })} />
                    <Champ etiquette={t("profils.form.min_montant", { methode: t(`profils.methode.${code}`) })} inputMode="decimal" autoComplete="off" value={m.min_montant} onChange={(e) => methode(code, { min_montant: e.target.value })} />
                    <Champ etiquette={t("profils.form.min_pourcentage", { methode: t(`profils.methode.${code}`) })} inputMode="decimal" autoComplete="off" value={m.min_pourcentage} onChange={(e) => methode(code, { min_pourcentage: e.target.value })} />
                  </div>
                )}
              </div>
            );
          })}
        </fieldset>

        <fieldset className="profils__groupe">
          <legend>{t("profils.regles")}</legend>
          {codes.length === 0 && <p>{t("profils.form.aucune_categorie")}</p>}
          {codes.map((code) => {
            const r = saisie.regles[code]!;
            const depasse = r.fin_propre && r.a && finEligibiliteAccord !== null && r.a > finEligibiliteAccord;
            return (
              <div key={code} className="profils__methode">
                <label className="profils__case">
                  <input type="checkbox" checked={r.incluse} onChange={(e) => regle(code, { incluse: e.target.checked })} />
                  {t("profils.form.regle_pour", { categorie: code })}
                </label>
                {r.incluse && (
                  <div className="profils__sous">
                    <Champ etiquette={t("profils.form.allocation", { categorie: code })} inputMode="decimal" autoComplete="off" value={r.allocation} onChange={(e) => regle(code, { allocation: e.target.value })} />
                    <Champ etiquette={t("profils.form.taux", { categorie: code })} inputMode="decimal" autoComplete="off" aide={t("profils.form.taux_aide")} value={r.taux} onChange={(e) => regle(code, { taux: e.target.value })} />
                    <Selecteur etiquette={t("profils.form.assiette", { categorie: code })} valeur={r.assiette} options={(["taxes_included", "net_of_taxes"] as const).map((a) => ({ valeur: a, libelle: t(`profils.assiette.${a}`) }))} onChange={(v) => regle(code, { assiette: v as SaisieRegle["assiette"] })} />
                    <Champ etiquette={t("profils.form.eligible_de", { categorie: code })} type="date" value={r.de} onChange={(e) => regle(code, { de: e.target.value })} />
                    <Champ etiquette={t("profils.form.eligible_a", { categorie: code })} type="date" value={r.a} onChange={(e) => regle(code, { a: e.target.value })} />
                    <Champ etiquette={t("profils.form.max_contrat", { categorie: code })} inputMode="decimal" autoComplete="off" value={r.max_contrat} onChange={(e) => regle(code, { max_contrat: e.target.value })} />
                    <label className="profils__case">
                      <input type="checkbox" checked={r.revue} onChange={(e) => regle(code, { revue: e.target.checked })} />
                      {t("profils.form.revue", { categorie: code })}
                    </label>
                    <label className="profils__case">
                      <input type="checkbox" checked={r.fin_propre} onChange={(e) => regle(code, { fin_propre: e.target.checked })} />
                      {t("profils.form.fin_propre", { categorie: code })}
                    </label>
                    {depasse && <Message variante="attention">{t("profils.form.fin_depasse", { categorie: code, fin: finEligibiliteAccord ?? "" })}</Message>}
                  </div>
                )}
              </div>
            );
          })}
        </fieldset>

        <fieldset className="profils__groupe">
          <legend>{t("profils.comptes")}</legend>
          {saisie.comptes.map((c, i) => (
            <div key={i} className="profils__methode">
              <Selecteur
                etiquette={t("profils.form.compte", { n: i + 1 })}
                valeur={c.compte}
                options={[{ valeur: "", libelle: t("profils.form.choisir_compte") }, ...comptesDesignes.map((x) => ({ valeur: x.code, libelle: `${x.code} · ${x.devise}` }))]}
                onChange={(v) => compte(i, { compte: v, devise: comptesDesignes.find((x) => x.code === v)?.devise ?? c.devise })}
              />
              <Selecteur etiquette={t("profils.form.plafond_genre", { n: i + 1 })} valeur={c.genre} options={(["fixed", "variable"] as const).map((g) => ({ valeur: g, libelle: t(`profils.plafond.${g}`) }))} onChange={(v) => compte(i, { genre: v as SaisieCompte["genre"] })} />
              <Champ etiquette={t("profils.form.plafond_montant", { n: i + 1 })} inputMode="decimal" autoComplete="off" value={c.plafond} onChange={(e) => compte(i, { plafond: e.target.value })} />
              <Champ etiquette={t("profils.form.seuil_reconstitution", { n: i + 1 })} inputMode="decimal" autoComplete="off" value={c.seuil} onChange={(e) => compte(i, { seuil: e.target.value })} />
              <Bouton variante="secondaire" aria-label={t("profils.form.retirer_compte", { n: i + 1 })} onClick={() => modifier((s) => ({ ...s, comptes: s.comptes.filter((_, j) => j !== i) }))}>
                {t("profils.form.retirer")}
              </Bouton>
            </div>
          ))}
          <Bouton variante="secondaire" onClick={() => modifier((s) => ({ ...s, comptes: [...s.comptes, { compte: "", devise: comptesDesignes[0]?.devise ?? "", genre: "fixed", plafond: "", seuil: "" }] }))}>
            {t("profils.form.ajouter_compte")}
          </Bouton>
        </fieldset>

        <div className="profils__actions">
          <Bouton type="submit" chargement={ecriture.isPending}>
            {t(profil ? "profils.form.enregistrer_modifs" : "profils.form.creer")}
          </Bouton>
          <Bouton variante="secondaire" disabled={ecriture.isPending} onClick={surAnnulation}>
            {t("profils.annuler")}
          </Bouton>
        </div>
      </form>
    </Carte>
  );
}
