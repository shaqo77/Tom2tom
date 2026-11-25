import { appeler } from "../../shared/api/client";
import type { ControleDetail, ControleLivre, ControleResume, DemandeInstallation, ResultatInstallation, StatutControle } from "./types";

const base = (projetId: string) => `/projets/${projetId}/controles/`;

export const lireControles = (projetId: string, statut?: StatutControle) =>
  appeler<ControleResume[]>(`${base(projetId)}${statut ? `?status=${statut}` : ""}`);
export const lireControle = (projetId: string, controleId: string) => appeler<ControleDetail>(`${base(projetId)}${controleId}/`);
export const lireBibliotheque = (projetId: string) => appeler<ControleLivre[]>(`${base(projetId)}bibliotheque/`);

export const validerControle = (projetId: string, controleId: string) =>
  appeler<ControleDetail>(`${base(projetId)}${controleId}/valider/`, { methode: "POST", corps: {} });
export const activerControle = (projetId: string, controleId: string) =>
  appeler<ControleDetail>(`${base(projetId)}${controleId}/activer/`, { methode: "POST", corps: {} });
export const rejeterControle = (projetId: string, controleId: string, motif: string) =>
  appeler<ControleDetail>(`${base(projetId)}${controleId}/rejeter/`, { methode: "POST", corps: { motif } });

export const installerBibliotheque = (projetId: string, corps: DemandeInstallation) =>
  appeler<ResultatInstallation>(`${base(projetId)}bibliotheque/installer/`, { methode: "POST", corps });
