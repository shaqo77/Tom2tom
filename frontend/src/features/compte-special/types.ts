/** Ce que renvoie l'API du compte spécial. Voir backend/niveau1_socle/tresorerie/api.py. */

export interface CompteBancaire {
  id: string;
  code: string;
  libelle: string;
  type: "designe" | "special" | "operationnel" | "contrepartie" | "transit";
  devise: string;
  accord: string | null;
  /** Le numéro MASQUÉ : le numéro complet ne sort jamais de l'API. */
  numero_masque: string;
  actif: boolean;
}

export interface LigneAvance {
  demande: string;
  montant: string;
}

export interface LigneJustification {
  demande: string;
  montant: string;
  date_soumission: string;
  en_cours: boolean;
  comptee: boolean;
}

/** La situation du compte à une date (lignes 2 à 7 de l'annexe 9 du manuel BAD). Tous les montants sont des chaînes. */
export interface Situation {
  compte: string;
  devise: string;
  date: string;
  complet: boolean;
  manques: string[];
  avances: LigneAvance[];
  justifications: LigneJustification[];
  total_avances: string;
  solde_cloture: string | null;
  justifie_cette_demande: string;
  justifie_precedemment: string;
  total_justifie: string | null;
  ecart: string | null;
}

export interface JustificationBanque {
  id: string;
  demande: string;
  montant: string;
  date_soumission: string;
  annulee: boolean;
  motif_annulation: string;
}

export interface RapportPublie {
  id: string;
  modele: string;
  /** Le sceau SHA-256 du rapport, en hexadécimal. */
  scelle: string;
  valeurs: Record<string, string>;
}

export interface DemandePublication {
  date_fin: string;
  demande?: string;
  note_ecart?: string;
}

/** La taille maximale de la note qui explique l'écart, comme le serveur. */
export const NOTE_MAX = 4000;

/** Une demande de retrait, telle que la liste l'offre au choix. Voir backend/niveau1_socle/decaissements/api.py. */
export interface DemandeRetrait {
  id: string;
  numero: string;
  type: string;
  statut: "preparee" | "soumise" | "acceptee" | "rejetee" | "contestee" | "remboursee" | "annulee";
  accord: string;
  periode_debut: string;
  periode_fin: string;
  montant_total: string;
}
