import { appeler } from "../../shared/api/client";
import type { CompteBancaire, DemandePublication, JustificationBanque, RapportPublie, Situation } from "./types";

export const lireComptes = (projetId: string) => appeler<CompteBancaire[]>(`/projets/${projetId}/comptes-bancaires/`);

export function lireSituation(compteId: string, date: string, demande?: string) {
  const recherche = new URLSearchParams({ date });
  if (demande) recherche.set("demande", demande);
  return appeler<Situation>(`/comptes/${compteId}/situation-compte-special/?${recherche.toString()}`);
}

export const lireJustifications = (compteId: string) =>
  appeler<JustificationBanque[]>(`/comptes/${compteId}/justifications-banque/`);

export const annulerJustification = (justificationId: string, motif: string) =>
  appeler<JustificationBanque>(`/justifications-banque/${justificationId}/annulation/`, { methode: "POST", corps: { motif } });

export const publierRapport = (compteId: string, corps: DemandePublication) =>
  appeler<RapportPublie>(`/comptes/${compteId}/rapport-compte-special/`, { methode: "POST", corps });
