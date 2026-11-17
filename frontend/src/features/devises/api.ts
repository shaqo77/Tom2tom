import { appeler } from "../../shared/api/client";
import type { DeviseCatalogue, NouvelleVersion, ReglagesResolus, VersionReglages } from "./types";

/** `projetId` absent : le niveau de l'organisation. */
const base = (projetId?: string) => (projetId ? `/projets/${projetId}/parametres-devises/` : "/parametres-devises/");

export const lireReglages = (jour: string, projetId?: string) =>
  appeler<ReglagesResolus>(`${base(projetId)}?jour=${jour}`);

export const lireHistorique = (projetId?: string) => appeler<VersionReglages[]>(`${base(projetId)}historique/`);

export const lireCatalogue = () => appeler<DeviseCatalogue[]>("/devises/");

export const poserReglages = (corps: NouvelleVersion, projetId?: string) =>
  appeler<VersionReglages>(base(projetId), { methode: "POST", corps });
