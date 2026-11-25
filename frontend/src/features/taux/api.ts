import { appeler } from "../../shared/api/client";
import type { FiltreTaux, NouveauTaux, TauxDeChange } from "./types";

/** Les taux les plus récents d'abord ; la liste est bornée (le serveur refuse plus de 500 lignes d'un coup). */
export const LIMITE = 200;

export function lireTaux(filtre: FiltreTaux) {
  const recherche = new URLSearchParams({ limite: String(LIMITE) });
  if (filtre.devise) recherche.set("devise", filtre.devise);
  if (filtre.type_taux) recherche.set("type_taux", filtre.type_taux);
  return appeler<TauxDeChange[]>(`/taux/?${recherche.toString()}`);
}

export const enregistrerTaux = (corps: NouveauTaux) => appeler<TauxDeChange>("/taux/", { methode: "POST", corps });
