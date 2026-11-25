/** Ce que renvoie l'API des documents. Voir backend/niveau3_config/api.py (`_document`, `DocumentIntegrite`). */

export type TypeDocument = "financing_agreement" | "dfil" | "implementation_manual" | "awp_budget" | "report_template" | "instruction";
export const TYPES_DOCUMENT: TypeDocument[] = ["financing_agreement", "dfil", "implementation_manual", "awp_budget", "report_template", "instruction"];

/** La taille maximale d'un dépôt, comme le serveur (50 Mio). Le serveur la refuse aussi : l'écran n'évite qu'un envoi inutile. */
export const TAILLE_MAX = 50 * 1024 * 1024;

export interface DocumentReference {
  id: string;
  kind: TypeDocument;
  title: string;
  version: string;
  issued_on: string | null;
  /** L'empreinte SHA-256, en hexadécimal. */
  sha256: string;
  /** L'identifiant du document qui le remplace, ou nul s'il est le plus récent. */
  remplace_par: string | null;
}

export interface DocumentRemplace extends DocumentReference {
  /** Les exigences dont la citation visait l'ancien document et qu'il faut revérifier. */
  exigences_a_reverifier: string[];
}

export interface Integrite {
  integre: boolean;
  probleme: string | null;
}
