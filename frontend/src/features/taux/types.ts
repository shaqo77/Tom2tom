/** Ce que renvoie l'API des taux de change. Voir backend/niveau1_socle/referentiels/api.py (`_taux`). */
import type { TypeTaux } from "../devises/types";

export interface TauxDeChange {
  id: string;
  /** Le code de la devise (par exemple USD) : `devise` et `devise_id` portent la même valeur. */
  devise: string;
  devise_id: string;
  date: string;
  /** Une chaîne décimale exacte : jamais un `number`. */
  taux: string;
  type_taux: TypeTaux;
  source: string;
}

export interface NouveauTaux {
  devise: string;
  date: string;
  taux: string;
  type_taux: TypeTaux;
  source?: string;
}

export interface FiltreTaux {
  devise?: string;
  type_taux?: TypeTaux;
}
