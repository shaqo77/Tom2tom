/** Ce que renvoie `GET /api/v1/tableau-de-bord/`. Voir backend/niveau4_reporting/tableau_de_bord/api.py. */

/** Des montants PAR DEVISE, en chaînes décimales. Deux devises ne s'additionnent jamais. */
export type MontantsParDevise = Record<string, string>;

export interface IndicateurDto {
  par_projet: Record<string, MontantsParDevise>;
  total_par_devise: MontantsParDevise;
}

export type CodeIndicateur =
  | "budget_approuve"
  | "budget_initial"
  | "financements_accordes"
  | "financements_recus"
  | "execution_budget"
  | "execution_engage"
  | "execution_consomme"
  | "soldes_comptables"
  | "soldes_releves"
  | "engagements_ouverts"
  | "avances_non_justifiees";

export interface ProjetDuTableau {
  id: string;
  code: string;
  libelle: { fr?: string; en?: string };
  statut: string;
  configuration: "configure" | "non_configure";
  bailleurs: string[];
}

export interface ConformiteProjetDto {
  echeances_a_remettre: number;
  echeances_imminentes: number;
  echeances_en_retard: number;
  echeances_en_escalade: number;
  rapports_en_attente: number;
  anomalies_ouvertes: number;
  premiers_envois_acceptes: number;
  premiers_envois_decides: number;
}

export interface TableauDto {
  jour: string;
  projets: ProjetDuTableau[];
  indicateurs: Record<CodeIndicateur, IndicateurDto>;
  /** consommé ÷ budget, par devise ; `null` quand le budget est nul. */
  taux_execution: Record<string, string | null>;
  /** Par composante (« » : sans composante) : budget, engagé, consommé et le taux d'exécution. */
  par_composante: Record<
    string,
    { budget: IndicateurDto; engage: IndicateurDto; consomme: IndicateurDto; taux_execution: Record<string, string | null> }
  >;
  conformite: {
    par_projet: Record<string, ConformiteProjetDto>;
    totaux: ConformiteProjetDto;
    /** acceptés ÷ décidés, calculé sur les SOMMES ; `null` sans envoi décidé. */
    taux_acceptation: string | null;
  };
  avertissements: { code: string; message: string }[];
  /** Le nombre de décimales de chaque devise affichée (DJF : 0, EUR : 2). */
  devises: Record<string, number>;
}

export interface FiltresTableau {
  jour?: string;
  statut?: "tous";
  devise?: string;
  projets?: string[];
}

/** La recherche de l'adresse du tableau de bord, après validation : une valeur invalide vaut `undefined`. */
export type RechercheTableau = { [K in keyof FiltresTableau]?: FiltresTableau[K] | undefined };

/** Ce que renvoie `GET /api/v1/tableau-de-bord/<indicateur>/consolidation/`. */
export interface ConsolidationDto {
  indicateur: CodeIndicateur;
  /** Nul tant qu'aucune référence n'est réglée ni demandée. */
  devise_reference: string | null;
  type_taux: string | null;
  /** D'où vient chaque valeur : le paramètre demandé, le réglage du projet ou celui de l'organisation. */
  origine: { devise_reference: Origine | null; type_taux: Origine | null };
  jour: string;
  consolide: boolean;
  montant: string | null;
  par_projet: Record<string, string>;
  taux: Record<string, { taux: string; date: string }>;
  methode: string | null;
  /** Pourquoi l'indicateur n'est pas consolidé, dans la langue de la requête. */
  raison: string | null;
}
export type Origine = "demande" | "projet" | "organisation";

/** Un objet qui compose un indicateur pour un projet (la somme des détails égale le chiffre). */
export interface DetailDto {
  type: string;
  id: string;
  libelle: string;
  devise: string;
  montant: string;
  a_une_ecriture: boolean;
}

export interface EcritureRefDto {
  ecriture_id: string;
  numero: string;
  date: string;
  libelle: string;
  montant: string;
}

export interface EcrituresDuDetailDto {
  detail: DetailDto;
  ecritures: EcritureRefDto[];
}

export interface EcritureDto {
  id: string;
  numero: string;
  journal: string;
  date: string;
  libelle: string;
  lignes: { id: string; compte: string; montant: string }[];
  pieces: { id: string; type: string; nom: string; taille: number }[];
}
