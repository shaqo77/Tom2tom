import { appeler } from "../../shared/api/client";
import type { EcritureDetail, EcritureResume, StatutEcriture } from "./types";

const base = (projetId: string) => `/projets/${projetId}/ecritures/`;

export const lireEcritures = (projetId: string, statut: StatutEcriture | "") =>
  appeler<EcritureResume[]>(`${base(projetId)}${statut ? `?statut=${statut}` : ""}`);

export const lireEcriture = (projetId: string, ecritureId: string) => appeler<EcritureDetail>(`${base(projetId)}${ecritureId}/`);

export const creerEcriture = (projetId: string, corps: Record<string, unknown>) =>
  appeler<EcritureDetail>(base(projetId), { methode: "POST", corps });

export const validerEcriture = (projetId: string, ecritureId: string) =>
  appeler<EcritureDetail>(`${base(projetId)}${ecritureId}/valider/`, { methode: "POST", corps: {} });

export const comptabiliserEcriture = (projetId: string, ecritureId: string) =>
  appeler<EcritureDetail>(`${base(projetId)}${ecritureId}/comptabiliser/`, { methode: "POST", corps: {} });
