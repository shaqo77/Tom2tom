/** Ce que renvoie l'API des réglages de devises. Voir backend/niveau1_socle/referentiels/api.py. */

export type TypeTaux = "officiel" | "bailleur" | "cloture" | "budget";
export const TYPES_TAUX: TypeTaux[] = ["officiel", "bailleur", "cloture", "budget"];

export type Provenance = "projet" | "organisation" | null;

export interface ReglagesResolus {
  jour: string;
  devise_reference: string | null;
  /** Nul : aucune restriction paramétrée. */
  devises_autorisees: string[] | null;
  type_taux: TypeTaux | null;
  origine: Record<"devise_reference" | "devises_autorisees" | "type_taux", Provenance>;
  versions: { organisation: number | null; projet: number | null };
}

export interface VersionReglages {
  id: string;
  version: number;
  project_id: string | null;
  devise_reference: string | null;
  devises_autorisees: string[] | null;
  type_taux: TypeTaux | null;
  valid_from: string;
  valid_to: string | null;
  motif: string;
}

export interface DeviseCatalogue {
  code: string;
  label: { fr?: string; en?: string };
  decimales: number;
}

export interface NouvelleVersion {
  devise_reference?: string;
  devises_autorisees?: string[];
  type_taux?: TypeTaux;
  date_effet: string;
  motif?: string;
}
