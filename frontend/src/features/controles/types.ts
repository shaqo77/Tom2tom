/** Ce que renvoie l'API des contrôles. Voir backend/niveau4_reporting/controles/api.py (`_controle`, `Bibliotheque`). */

export type StatutControle = "draft" | "validated" | "active" | "superseded" | "rejected";
export type Severite = "bloquant" | "avertissement" | "information";
export const STATUTS: StatutControle[] = ["draft", "validated", "active", "superseded", "rejected"];

export interface Libelle {
  fr?: string;
  en?: string;
}

export interface ControleResume {
  id: string;
  code: string;
  version: number;
  status: StatutControle;
  mode: string;
  type_regle: string;
  severity: Severite;
  label: Libelle;
  valid_from: string;
  valid_to: string | null;
}

export interface ControleDetail extends ControleResume {
  expression: unknown;
  applicable_si: unknown;
  parametres: unknown;
  action_corrective: Libelle | null;
}

export interface ControleLivre {
  code: string;
  famille: string;
  type_regle: string;
  severity: Severite;
  label: Libelle;
  action_corrective: Libelle | null;
  installe: boolean;
}

/** Les trois contrôles de risque dont le seuil se règle à l'installation, et ce que le serveur attend de chacun. */
export const SEUILS = {
  "RIS-CATEGORIE-SEUIL": { nature: "pourcentage" },
  "RIS-AVANCE-NON-APUREE": { nature: "jours" },
  "RIS-REJETS-REPETES": { nature: "maximum" },
} as const;
export type CodeSeuil = keyof typeof SEUILS;

export interface ResultatInstallation {
  crees: string[];
  deja_presents: string[];
}

/** Un appel de décision sur un contrôle (valider, activer, rejeter) : rend le contrôle à jour. */
export type AppelDecision = () => Promise<ControleDetail>;

export interface DemandeInstallation {
  codes: string[];
  valid_from: string;
  seuils?: Record<string, string | number>;
}

/** Le langage de conditions tel que le serveur l'accepte. Voir backend/niveau4_reporting/controles/api.py (`LangageControles`). */
export type TypeChamp = "decimal" | "entier" | "date" | "texte" | "booleen" | "liste";
export interface ChampLangage {
  type: TypeChamp;
  /** Pour une liste : le type de chaque champ de ses éléments. */
  elements?: Record<string, TypeChamp>;
}
export interface Langage {
  types_regle: Record<string, Record<string, ChampLangage>>;
  operateurs: Record<string, { types: TypeChamp[]; sans_valeur: boolean }>;
  severites: Severite[];
  max_conditions: number;
}
