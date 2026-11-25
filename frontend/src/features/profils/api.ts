import { appeler } from "../../shared/api/client";
import type { AccordResume, CompteListe, ProfilDetail, ProfilResume } from "./types";

const base = (projetId: string, accordId: string) =>
  `/projets/${projetId}/accords/${accordId}/profils-decaissement/`;

export const lireAccords = (projetId: string) => appeler<AccordResume[]>(`/projets/${projetId}/accords/`);

export const lireProfils = (projetId: string, accordId: string) =>
  appeler<ProfilResume[]>(base(projetId, accordId));

export const lireProfil = (projetId: string, accordId: string, profilId: string) =>
  appeler<ProfilDetail>(`${base(projetId, accordId)}${profilId}/`);

export const validerProfil = (projetId: string, accordId: string, profilId: string) =>
  appeler<ProfilDetail>(`${base(projetId, accordId)}${profilId}/valider/`, { methode: "POST", corps: {} });

export const activerProfil = (projetId: string, accordId: string, profilId: string) =>
  appeler<ProfilDetail>(`${base(projetId, accordId)}${profilId}/activer/`, { methode: "POST", corps: {} });

export const rejeterProfil = (projetId: string, accordId: string, profilId: string, motif: string) =>
  appeler<ProfilDetail>(`${base(projetId, accordId)}${profilId}/rejeter/`, { methode: "POST", corps: { motif } });

export const supprimerBrouillon = (projetId: string, accordId: string, profilId: string) =>
  appeler<{ supprime: boolean }>(`${base(projetId, accordId)}${profilId}/`, { methode: "DELETE" });

/** Le profil entier, d'un bloc : création d'un BROUILLON (le serveur ne crée jamais autre chose). */
export const creerProfil = (projetId: string, accordId: string, corps: Record<string, unknown>) =>
  appeler<ProfilDetail>(base(projetId, accordId), { methode: "POST", corps });

/** Remplace TOUT le contenu d'un brouillon : tout est accepté ou rien ne change. */
export const remplacerProfil = (projetId: string, accordId: string, profilId: string, corps: Record<string, unknown>) =>
  appeler<ProfilDetail>(`${base(projetId, accordId)}${profilId}/`, { methode: "PUT", corps });

export const lireComptesDesignes = (projetId: string) => appeler<CompteListe[]>(`/projets/${projetId}/comptes-bancaires/`);
