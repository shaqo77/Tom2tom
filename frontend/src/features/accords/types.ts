/** Ce que renvoie l'API des accords. Voir backend/niveau1_socle/financements/api.py (`_accord`, `_categorie`, `_avenant`). */

export type StatutAccord = "brouillon" | "actif" | "suspendu" | "clos" | "annule";
export type FormatNumero = "standard" | "bad";

export interface AccordResume {
  id: string;
  numero: string;
  libelle: string;
  bailleur: string;
  nature: "don" | "pret" | "contrepartie";
  statut: StatutAccord;
  devise: string;
  montant_initial: string;
  montant_courant: string;
  date_effet: string | null;
  date_fin_eligibilite: string | null;
  date_cloture: string | null;
  date_limite_decaissement: string | null;
  format_numero_demande: FormatNumero;
  suffixe_agence: string;
}

export interface CategorieAccord {
  id: string;
  code: string;
  label: { fr?: string; en?: string };
  /** Le code de la catégorie parente, ou nul pour une racine. */
  parent: string | null;
  plafond: string | null;
  devise: string;
}

export interface AvenantAccord {
  id: string;
  reference: string;
  date_avenant: string;
  montant_revise: string;
  motif: string;
  document_id: string | null;
}

export interface AccordDetail extends AccordResume {
  categories: CategorieAccord[];
  avenants: AvenantAccord[];
}

/** La situation de l'accord avant et après un avenant. Voir backend/niveau1_socle/financements/services.py (`situation_avant_apres`). */
export interface SituationAvenant {
  reference: string;
  date: string;
  montant_avant: string;
  montant_apres: string;
  variation: string;
}
