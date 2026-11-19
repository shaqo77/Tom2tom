import { appeler } from "../../shared/api/client";
import type {
  CodeIndicateur,
  ConsolidationDto,
  DetailDto,
  EcritureDto,
  EcrituresDuDetailDto,
  FiltresTableau,
  TableauDto,
} from "./types";

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

function filtresEnRecherche(filtres: { jour: string; devise?: string | undefined }): URLSearchParams {
  const recherche = new URLSearchParams({ jour: filtres.jour });
  if (filtres.devise) recherche.set("devise", filtres.devise);
  return recherche;
}

/** La devise de référence et le type de taux, quand ils sont donnés, l'emportent sur les réglages. */
export function lireConsolidation(
  code: CodeIndicateur,
  filtres: FiltresTableau & { jour: string },
  choix: { devise_reference?: string; type_taux?: string },
  signal?: AbortSignal,
): Promise<ConsolidationDto> {
  const recherche = new URLSearchParams({ jour: filtres.jour });
  if (filtres.statut === "tous") recherche.set("statut_projet", "tous");
  if (filtres.projets?.length) recherche.set("projets", filtres.projets.join(","));
  if (choix.devise_reference) recherche.set("devise_reference", choix.devise_reference);
  if (choix.type_taux) recherche.set("type_taux", choix.type_taux);
  return appeler<ConsolidationDto>(`/tableau-de-bord/${code}/consolidation/?${recherche.toString()}`, signal ? { signal } : {});
}

export const lireDetail = (projetId: string, code: CodeIndicateur, filtres: { jour: string; devise?: string | undefined }) =>
  appeler<DetailDto[]>(`/projets/${projetId}/tableau-de-bord/${code}/detail/?${filtresEnRecherche(filtres)}`);

export const lireEcrituresDuDetail = (
  projetId: string,
  code: CodeIndicateur,
  detailId: string,
  filtres: { jour: string; devise?: string | undefined },
) =>
  appeler<EcrituresDuDetailDto>(
    `/projets/${projetId}/tableau-de-bord/${code}/detail/${detailId}/ecritures/?${filtresEnRecherche(filtres)}`,
  );

export const lireEcriture = (projetId: string, ecritureId: string) =>
  appeler<EcritureDto>(`/projets/${projetId}/tableau-de-bord/ecritures/${ecritureId}/`);
