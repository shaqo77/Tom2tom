import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ErreurApi } from "../../shared/api/client";
import { Bouton } from "../../shared/ui/Bouton";
import { Carte } from "../../shared/ui/Carte";
import { Champ } from "../../shared/ui/Champ";
import { Message } from "../../shared/ui/Message";
import { Selecteur } from "../../shared/ui/Selecteur";
import { creerAccord, creerCategorie, lireBailleurs } from "./api";
import { FormulaireBailleur } from "./FormulairesAvenant";
import { accordVide, categorieVide, construireAccord, construireCategorie } from "./creation";
import type { Faute, SaisieAccord, SaisieCategorie } from "./creation";
import type { AccordResume, CategorieAccord } from "./types";

const DATES = ["date_effet", "date_fin_eligibilite", "date_cloture", "date_limite_decaissement"] as const;

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

/** Crée un accord en brouillon. Le serveur reste l'autorité : son refus s'affiche tel quel. */
export function FormulaireAccord({ projetId, surTermine, surAnnulation }: { projetId: string; surTermine: (a: AccordResume) => void; surAnnulation: () => void }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const bailleurs = useQuery({ queryKey: ["bailleurs"], queryFn: lireBailleurs });
  const [nouveauBailleur, definirNouveauBailleur] = useState(false);
  const [saisie, definirSaisie] = useState<SaisieAccord>(accordVide);
  const [fautes, definirFautes] = useState<Faute[]>([]);
  const [echec, definirEchec] = useState<string | null>(null);
  const ecriture = useMutation({
    mutationFn: (corps: Record<string, unknown>) => creerAccord(projetId, corps),
    onSuccess: surTermine,
    onError: (e) => definirEchec(texteErreur(e, t("erreur.inconnue"))),
  });
  const modifier = (champ: Partial<SaisieAccord>) => definirSaisie((s) => ({ ...s, ...champ }));

  function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    definirEchec(null);
    if (ecriture.isPending) return;
    const r = construireAccord(saisie, i18n.language);
    if (!r.ok) return definirFautes(r.fautes);
    definirFautes([]);
    ecriture.mutate(r.corps);
  }

  return (
    <Carte titre={t("accords.form.titre_accord")}>
      <form className="accords__form" onSubmit={soumettre} noValidate>
        <Fautes fautes={fautes} />
        {echec && <Message variante="danger">{echec}</Message>}
        {bailleurs.error && <Message variante="danger">{texteErreur(bailleurs.error, t("accords.form.erreur_bailleurs"))}</Message>}
        <Selecteur
          etiquette={t("accords.form.bailleur")}
          valeur={saisie.bailleur}
          options={[{ valeur: "", libelle: t("accords.form.choisir_bailleur") }, ...(bailleurs.data ?? []).map((b) => ({ valeur: b.code, libelle: `${b.code} · ${b.nom}` }))]}
          onChange={(v) => modifier({ bailleur: v })}
        />
        {nouveauBailleur ? (
          <FormulaireBailleur
            surAnnulation={() => definirNouveauBailleur(false)}
            surTermine={(b) => {
              definirNouveauBailleur(false);
              void queryClient.invalidateQueries({ queryKey: ["bailleurs"] });
              modifier({ bailleur: b.code });
            }}
          />
        ) : (
          <Bouton variante="secondaire" onClick={() => definirNouveauBailleur(true)}>
            {t("accords.form.nouveau_bailleur")}
          </Bouton>
        )}
        <Champ etiquette={t("accords.form.numero")} autoComplete="off" value={saisie.numero} onChange={(e) => modifier({ numero: e.target.value })} />
        <Champ etiquette={t("accords.form.libelle")} autoComplete="off" value={saisie.libelle} onChange={(e) => modifier({ libelle: e.target.value })} />
        <Selecteur
          etiquette={t("accords.form.nature")}
          valeur={saisie.nature}
          options={(["don", "pret", "contrepartie"] as const).map((n) => ({ valeur: n, libelle: t(`accords.nature.${n}`) }))}
          onChange={(v) => modifier({ nature: v as SaisieAccord["nature"] })}
        />
        <Champ etiquette={t("accords.form.devise")} autoComplete="off" maxLength={3} value={saisie.devise} onChange={(e) => modifier({ devise: e.target.value })} />
        <Champ etiquette={t("accords.form.montant_initial")} inputMode="decimal" autoComplete="off" value={saisie.montant_initial} onChange={(e) => modifier({ montant_initial: e.target.value })} />
        {DATES.map((d) => (
          <Champ key={d} etiquette={t(`accords.date.${d}`)} type="date" value={saisie[d]} onChange={(e) => modifier({ [d]: e.target.value })} />
        ))}
        <div className="accords__actions">
          <Bouton type="submit" chargement={ecriture.isPending}>
            {t("accords.form.creer_accord")}
          </Bouton>
          <Bouton variante="secondaire" disabled={ecriture.isPending} onClick={surAnnulation}>
            {t("accords.form.annuler")}
          </Bouton>
        </div>
      </form>
    </Carte>
  );
}

/** Ajoute une catégorie (racine ou sous-catégorie) à un accord. */
export function FormulaireCategorie({
  projetId,
  accordId,
  existantes,
  surTermine,
  surAnnulation,
}: {
  projetId: string;
  accordId: string;
  existantes: CategorieAccord[];
  surTermine: (c: CategorieAccord) => void;
  surAnnulation: () => void;
}) {
  const { t, i18n } = useTranslation();
  const [saisie, definirSaisie] = useState<SaisieCategorie>(categorieVide);
  const [fautes, definirFautes] = useState<Faute[]>([]);
  const [echec, definirEchec] = useState<string | null>(null);
  const ecriture = useMutation({
    mutationFn: (corps: Record<string, unknown>) => creerCategorie(projetId, accordId, corps),
    onSuccess: surTermine,
    onError: (e) => definirEchec(texteErreur(e, t("erreur.inconnue"))),
  });
  const modifier = (champ: Partial<SaisieCategorie>) => definirSaisie((s) => ({ ...s, ...champ }));

  function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    definirEchec(null);
    if (ecriture.isPending) return;
    const r = construireCategorie(saisie, i18n.language);
    if (!r.ok) return definirFautes(r.fautes);
    definirFautes([]);
    ecriture.mutate(r.corps);
  }

  return (
    <form className="accords__form" onSubmit={soumettre} noValidate aria-label={t("accords.form.titre_categorie")}>
      <h4>{t("accords.form.titre_categorie")}</h4>
      <Fautes fautes={fautes} />
      {echec && <Message variante="danger">{echec}</Message>}
      <Champ etiquette={t("accords.form.code")} autoComplete="off" value={saisie.code} onChange={(e) => modifier({ code: e.target.value })} />
      <Champ etiquette={t("accords.form.libelle_fr")} autoComplete="off" value={saisie.fr} onChange={(e) => modifier({ fr: e.target.value })} />
      <Champ etiquette={t("accords.form.libelle_en")} autoComplete="off" value={saisie.en} onChange={(e) => modifier({ en: e.target.value })} />
      <Selecteur
        etiquette={t("accords.form.parent")}
        valeur={saisie.parent}
        options={[{ valeur: "", libelle: t("accords.form.aucun_parent") }, ...existantes.filter((c) => !c.parent).map((c) => ({ valeur: c.code, libelle: c.code }))]}
        onChange={(v) => modifier({ parent: v })}
      />
      <Champ etiquette={t("accords.form.plafond")} inputMode="decimal" autoComplete="off" value={saisie.plafond} onChange={(e) => modifier({ plafond: e.target.value })} />
      <Champ etiquette={t("accords.form.devise_categorie")} autoComplete="off" maxLength={3} value={saisie.devise} onChange={(e) => modifier({ devise: e.target.value })} />
      <div className="accords__actions">
        <Bouton type="submit" chargement={ecriture.isPending}>
          {t("accords.form.creer_categorie")}
        </Bouton>
        <Bouton variante="secondaire" disabled={ecriture.isPending} onClick={surAnnulation}>
          {t("accords.form.annuler")}
        </Bouton>
      </div>
    </form>
  );
}
