/** Ce que renvoie l'API des profils de décaissement. Voir backend/niveau3_config/api.py (`_profil`). */

export type StatutProfil = "draft" | "validated" | "active" | "superseded" | "rejected";
export type Regime = "transaction_based" | "report_based";

/** Un accord de financement, tel que la liste des accords d'un projet le rend (`_accord`). */
export interface AccordResume {
  id: string;
  numero: string;
  libelle: string;
  bailleur: string;
  statut: string;
  devise: string;
}

export interface MethodeProfil {
  method: "advance" | "reimbursement" | "direct_payment" | "special_commitment";
  is_enabled: boolean;
  supporting_docs: string[];
  full_doc_threshold: string | null;
  min_application_amount: string | null;
  min_application_pct_of_ceiling: string | null;
}

export interface RegleProfil {
  category: string;
  allocation: string;
  /** Un taux entre 0 (exclu) et 1, en chaîne : jamais un `number`. */
  funding_rate: string;
  tax_basis: "taxes_included" | "net_of_taxes";
  eligibility_from: string | null;
  eligibility_to: string | null;
  requires_prior_review: boolean;
  max_per_contract: string | null;
  fin_propre_a_la_categorie: boolean;
}

export interface CompteProfil {
  compte: string;
  devise: string;
  ceiling_kind: "fixed" | "variable";
  ceiling_amount: string | null;
  replenishment_threshold_pct: string | null;
}

export interface AnomalieCompletude {
  code: string;
  message: string;
}

export interface Completude {
  complet: boolean;
  bloquantes: AnomalieCompletude[];
  avertissements: AnomalieCompletude[];
}

export interface ProfilResume {
  id: string;
  accord: string;
  version: number;
  status: StatutProfil;
  valid_from: string;
  valid_to: string | null;
  regime: Regime;
  exigence: string | null;
  rejection_reason: string;
  effectiveness_date: string | null;
  eligibility_date: string | null;
  closing_date: string | null;
  disbursement_deadline: string | null;
}

export interface ProfilDetail extends ProfilResume {
  methodes: MethodeProfil[];
  regles: RegleProfil[];
  comptes: CompteProfil[];
  /** Présente pour un brouillon seulement. */
  completude?: Completude;
}

/** Un appel de décision sur un profil (valider, activer, rejeter) : rend le profil à jour. */
export type AppelDecision = () => Promise<ProfilDetail>;
