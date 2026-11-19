/** Ce que l'API de session (`/api/v1/session/moi/`) renvoie. Voir backend/niveau1_socle/organisations/api.py. */

export type Operation =
  | "consulter"
  | "saisir"
  | "valider"
  | "comptabiliser"
  | "parametrer"
  | "exporter"
  | "publier"
  | "voir_numero_compte";

export interface LibelleMultilingue {
  fr?: string;
  en?: string;
}

export interface ProjetAccessible {
  id: string;
  code: string;
  libelle: LibelleMultilingue;
  statut: string;
  /** Opérations sur TOUT le projet. Une habilitation limitée à un site n'y figure jamais. */
  operations: Operation[];
  operations_par_site: Record<string, Operation[]>;
}

export interface OrganisationCourante {
  id: string;
  code: string;
  raison_sociale: string;
  monnaie_tenue: string;
  langues_actives: string[];
}

export interface Moi {
  id: string;
  identifiant: string;
  nom_complet: string;
  langue: string;
  /** Nul pour un compte de plateforme : il ne voit alors aucune donnée métier. */
  organisation: OrganisationCourante | null;
  projets: ProjetAccessible[];
}
