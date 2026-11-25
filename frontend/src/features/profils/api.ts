import { appeler } from "../../shared/api/client";
import type { AccordResume, ProfilDetail, ProfilResume } from "./types";

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
