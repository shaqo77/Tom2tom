/** Ce que renvoie l'API des clés de cofinancement. Voir backend/niveau1_socle/financements/api.py (`_cle`, `_version`). */

export interface PartCle {
  /** Le numéro de l'accord. */
  accord: string;
  /** Une chaîne décimale entre 0 et 1 (la somme des parts d'une version vaut exactement 1). */
  part: string;
}

export interface VersionCle {
  id: string;
  version: number;
  valid_from: string;
  valid_to: string | null;
  /** Le numéro de l'accord qui reçoit le reste de l'arrondi. */
  porteur: string;
  motif: string;
  parts: PartCle[];
}

export interface CleResume {
  id: string;
  code: string;
  label: { fr?: string; en?: string };
  version_en_vigueur: VersionCle | null;
}

export interface CleDetail {
  id: string;
  code: string;
  label: { fr?: string; en?: string };
  versions: VersionCle[];
}

export interface NouvelleCle {
  code: string;
  label: { fr?: string; en?: string };
}

export interface NouvelleVersionCle {
  /** `{numéro d'accord: poids}` : des chaînes décimales strictement positives. */
  parts: Record<string, string>;
  porteur: string;
  valid_from: string;
  motif?: string;
}

export interface AccordPourCle {
  id: string;
  numero: string;
  bailleur: string;
  statut: string;
}
