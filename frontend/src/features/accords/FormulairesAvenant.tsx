import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ErreurApi } from "../../shared/api/client";
import { Bouton } from "../../shared/ui/Bouton";
import { Champ } from "../../shared/ui/Champ";
import { Message } from "../../shared/ui/Message";
import { Selecteur } from "../../shared/ui/Selecteur";
import { lireDocuments } from "../documents/api";
import { creerAvenant, creerBailleur } from "./api";
import { avenantVide, bailleurVide, construireAvenant, construireBailleur } from "./creation";
import type { Faute, SaisieAvenant, SaisieBailleur } from "./creation";
import type { SituationAvenant } from "./types";

function texteErreur(erreur: unknown, secours: string): string {
  return erreur instanceof ErreurApi && erreur.message ? erreur.message : secours;
}

function Fautes({ fautes }: { fautes: Faute[] }) {
  const { t } = useTranslation();
  if (fautes.length === 0) return null;
  return (
    <Message variante="attention">
      {t("accords.form.a_corriger")}
      <ul>
        {fautes.map((f, i) => (
          <li key={`${f.cle}-${i}`}>{t(f.cle, f.params ?? {})}</li>
        ))}
      </ul>
    </Message>
  );
}

/**
 * Enregistre un avenant : une nouvelle valeur du montant de l'accord, appuyée par un document de référence déjà déposé.
 * Le serveur calcule la situation avant et après ; l'écran la montre telle quelle, sans rien recalculer.
 */
export function FormulaireAvenant({ projetId, accordId, surTermine, surAnnulation }: { projetId: string; accordId: string; surTermine: (s: SituationAvenant) => void; surAnnulation: () => void }) {
  const { t, i18n } = useTranslation();
  const documents = useQuery({ queryKey: ["documents", projetId], queryFn: () => lireDocuments(projetId) });
  const [saisie, definirSaisie] = useState<SaisieAvenant>(avenantVide);
  const [fautes, definirFautes] = useState<Faute[]>([]);
  const [echec, definirEchec] = useState<string | null>(null);
  const ecriture = useMutation({
    mutationFn: (corps: Record<string, unknown>) => creerAvenant(projetId, accordId, corps),
    onSuccess: surTermine,
    onError: (e) => definirEchec(texteErreur(e, t("erreur.inconnue"))),
  });
  const modifier = (champ: Partial<SaisieAvenant>) => definirSaisie((s) => ({ ...s, ...champ }));

  function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    definirEchec(null);
    if (ecriture.isPending) return;
    const r = construireAvenant(saisie, i18n.language);
    if (!r.ok) return definirFautes(r.fautes);
    definirFautes([]);
    ecriture.mutate(r.corps);
  }

  return (
    <form className="accords__form" onSubmit={soumettre} noValidate aria-label={t("accords.form.titre_avenant")}>
      <h4>{t("accords.form.titre_avenant")}</h4>
      <Fautes fautes={fautes} />
      {echec && <Message variante="danger">{echec}</Message>}
      {documents.error && <Message variante="danger">{texteErreur(documents.error, t("accords.form.erreur_documents"))}</Message>}
      <Champ etiquette={t("accords.form.reference")} autoComplete="off" value={saisie.reference} onChange={(e) => modifier({ reference: e.target.value })} />
      <Champ etiquette={t("accords.form.date_avenant")} type="date" value={saisie.date} onChange={(e) => modifier({ date: e.target.value })} />
      <Selecteur
        etiquette={t("accords.form.document")}
        valeur={saisie.document}
        options={[{ valeur: "", libelle: t("accords.form.choisir_document") }, ...(documents.data ?? []).map((d) => ({ valeur: d.id, libelle: `${d.title} · ${d.version}` }))]}
        onChange={(v) => modifier({ document: v })}
      />
      <Champ etiquette={t("accords.form.montant_revise")} inputMode="decimal" autoComplete="off" value={saisie.montant} onChange={(e) => modifier({ montant: e.target.value })} />
      <Champ etiquette={t("accords.form.motif")} autoComplete="off" value={saisie.motif} onChange={(e) => modifier({ motif: e.target.value })} />
      <div className="accords__actions">
        <Bouton type="submit" chargement={ecriture.isPending}>
          {t("accords.form.creer_avenant")}
        </Bouton>
        <Bouton variante="secondaire" disabled={ecriture.isPending} onClick={surAnnulation}>
          {t("accords.form.annuler")}
        </Bouton>
      </div>
    </form>
  );
}

/** Crée un bailleur ; le code se saisit une fois, le pays est facultatif (deux lettres). */
export function FormulaireBailleur({ surTermine, surAnnulation }: { surTermine: (b: { id: string; code: string; nom: string }) => void; surAnnulation: () => void }) {
  const { t } = useTranslation();
  const [saisie, definirSaisie] = useState<SaisieBailleur>(bailleurVide);
  const [fautes, definirFautes] = useState<Faute[]>([]);
  const [echec, definirEchec] = useState<string | null>(null);
  const ecriture = useMutation({
    mutationFn: (corps: Record<string, unknown>) => creerBailleur(corps),
    onSuccess: surTermine,
    onError: (e) => definirEchec(texteErreur(e, t("erreur.inconnue"))),
  });
  const modifier = (champ: Partial<SaisieBailleur>) => definirSaisie((s) => ({ ...s, ...champ }));

  function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    definirEchec(null);
    if (ecriture.isPending) return;
    const r = construireBailleur(saisie);
    if (!r.ok) return definirFautes(r.fautes);
    definirFautes([]);
    ecriture.mutate(r.corps);
  }

  return (
    <form className="accords__form" onSubmit={soumettre} noValidate aria-label={t("accords.form.titre_bailleur")}>
      <h4>{t("accords.form.titre_bailleur")}</h4>
      <Fautes fautes={fautes} />
      {echec && <Message variante="danger">{echec}</Message>}
      <Champ etiquette={t("accords.form.code_bailleur")} autoComplete="off" value={saisie.code} onChange={(e) => modifier({ code: e.target.value })} />
      <Champ etiquette={t("accords.form.nom_bailleur")} autoComplete="off" value={saisie.nom} onChange={(e) => modifier({ nom: e.target.value })} />
      <Champ etiquette={t("accords.form.pays")} autoComplete="off" maxLength={2} value={saisie.pays} onChange={(e) => modifier({ pays: e.target.value })} />
      <div className="accords__actions">
        <Bouton type="submit" chargement={ecriture.isPending}>
          {t("accords.form.creer_bailleur")}
        </Bouton>
        <Bouton variante="secondaire" disabled={ecriture.isPending} onClick={surAnnulation}>
          {t("accords.form.annuler")}
        </Bouton>
      </div>
    </form>
  );
}
