import { appeler } from "../../shared/api/client";
import type { FiltresTableau, TableauDto } from "./types";

export function lireTableau(filtres: FiltresTableau & { jour: string }, signal?: AbortSignal): Promise<TableauDto> {
  const recherche = new URLSearchParams({ jour: filtres.jour });
  if (filtres.statut === "tous") recherche.set("statut_projet", "tous");
  if (filtres.devise) recherche.set("devise", filtres.devise);
  if (filtres.projets?.length) recherche.set("projets", filtres.projets.join(","));
  return appeler<TableauDto>(`/tableau-de-bord/?${recherche.toString()}`, signal ? { signal } : {});
}

/** La date du jour dans le fuseau de l'utilisateur, `AAAA-MM-JJ` (jamais en UTC : minuit décale d'un jour). */
export function aujourdhui(maintenant: Date = new Date()): string {
  const deux = (n: number) => String(n).padStart(2, "0");
  return `${maintenant.getFullYear()}-${deux(maintenant.getMonth() + 1)}-${deux(maintenant.getDate())}`;
}

/** Une vraie date `AAAA-MM-JJ` : le 31 février n'existe pas, même si le format est bon. */
export function dateIsoValide(texte: unknown): texte is string {
  if (typeof texte !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(texte)) return false;
  const date = new Date(`${texte}T12:00:00`);
  return !Number.isNaN(date.getTime()) && aujourdhui(date) === texte;
}
