/** Ce que renvoie l'API des écritures. Voir backend/niveau1_socle/comptabilite/api.py (`_ecriture`, `_ligne`). */

export type StatutEcriture = "draft" | "validated" | "posted" | "locked";

export interface LigneEcriture {
  line_no: number;
  compte: string;
  debit: string;
  credit: string;
  label: string;
  /** Le numéro de l'accord qui porte cette ligne (une ligne à clé en donne une par accord). */
  accord: string | null;
  cle_version: string | null;
}

export interface EcritureResume {
  id: string;
  number: string | null;
  status: StatutEcriture;
  label: string;
  document_ref: string;
  fx_rate: string;
  journal: string;
  date_comptable: string;
  devise: string;
}

export interface EcritureDetail extends EcritureResume {
  lignes: LigneEcriture[];
  total_debit: string;
  total_credit: string;
  /** Seulement après une validation. */
  avertissements?: string[];
}
