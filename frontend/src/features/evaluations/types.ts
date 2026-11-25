/** Ce que renvoie l'API des évaluations et des dérogations. Voir backend/niveau4_reporting/controles/api.py. */

export type Resultat = "reussi" | "bloquant" | "avertissement" | "information" | "a_verifier" | "non_applicable";
export const RESULTATS: Resultat[] = ["reussi", "bloquant", "avertissement", "information", "a_verifier", "non_applicable"];
export type DecisionControle = "conforme" | "non_conforme";
export type StatutDerogation = "demandee" | "approuvee" | "refusee";
export const STATUTS_DEROGATION: StatutDerogation[] = ["demandee", "approuvee", "refusee"];

export interface Libelle {
  fr?: string;
  en?: string;
}

export interface Evaluation {
  id: string;
  controle: string;
  controle_version: number;
  objet_type: string;
  objet_id: string | null;
  resultat: Resultat;
  severity: string;
  message: string;
  action_corrective: Libelle | null;
  valeur_constatee: string | null;
  valeur_attendue: string | null;
  exigence: string | null;
  evaluee_le: string;
}

export interface Derogation {
  id: string;
  evaluation: string;
  controle: string;
  objet_type: string;
  objet_id: string | null;
  motif: string;
  justificatif: string;
  /** Début inclus. */
  valide_du: string;
  /** Fin EXCLUE (intervalle semi-ouvert). */
  valide_jusquau: string;
  statut: StatutDerogation;
  motif_decision: string;
}

export interface EvaluationDetail extends Evaluation {
  decisions: { decision: DecisionControle; motif: string; decided_at: string }[];
  justifications: { texte: string; auteur: string; created_at: string }[];
  derogations: Derogation[];
}

export interface FiltreEvaluations {
  resultat?: Resultat;
  controle?: string;
  objet_type?: string;
}

export interface DemandeDerogation {
  motif: string;
  justificatif: string;
  valide_du: string;
  valide_jusquau: string;
}

/** Un appel d'écriture sur une évaluation : rend ce que le serveur a créé. */
export type Appel<T> = () => Promise<T>;
