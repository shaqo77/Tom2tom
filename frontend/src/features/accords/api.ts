import { appeler } from "../../shared/api/client";
import type { AccordDetail, AccordResume, CategorieAccord, FormatNumero, StatutAccord } from "./types";

export const lireAccords = (projetId: string) => appeler<AccordResume[]>(`/projets/${projetId}/accords/`);

export const lireAccord = (projetId: string, accordId: string) =>
  appeler<AccordDetail>(`/projets/${projetId}/accords/${accordId}/`);

export const changerStatut = (projetId: string, accordId: string, statut: StatutAccord, motif: string) =>
  appeler<AccordResume>(`/projets/${projetId}/accords/${accordId}/statut/`, { methode: "POST", corps: { statut, motif } });

export const reglerNumerotation = (projetId: string, accordId: string, format: FormatNumero, suffixe_agence: string) =>
  appeler<AccordResume>(`/projets/${projetId}/accords/${accordId}/numerotation/`, {
    methode: "POST",
    corps: { format, suffixe_agence },
  });

export const lireBailleurs = () => appeler<{ id: string; code: string; nom: string }[]>("/bailleurs/");

export const creerAccord = (projetId: string, corps: Record<string, unknown>) =>
  appeler<AccordResume>(`/projets/${projetId}/accords/`, { methode: "POST", corps });

export const creerCategorie = (projetId: string, accordId: string, corps: Record<string, unknown>) =>
  appeler<CategorieAccord>(`/projets/${projetId}/accords/${accordId}/categories/`, { methode: "POST", corps });
