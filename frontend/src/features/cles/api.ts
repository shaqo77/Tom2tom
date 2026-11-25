import { appeler } from "../../shared/api/client";
import type { AccordPourCle, CleDetail, CleResume, NouvelleCle, NouvelleVersionCle, VersionCle } from "./types";

const base = (projetId: string) => `/projets/${projetId}/cles-cofinancement/`;

export const lireCles = (projetId: string) => appeler<CleResume[]>(base(projetId));
export const lireCle = (projetId: string, cleId: string) => appeler<CleDetail>(`${base(projetId)}${cleId}/`);
export const lireAccordsDuProjet = (projetId: string) => appeler<AccordPourCle[]>(`/projets/${projetId}/accords/`);

export const creerCle = (projetId: string, corps: NouvelleCle) =>
  appeler<{ id: string; code: string }>(base(projetId), { methode: "POST", corps });

export const creerVersion = (projetId: string, cleId: string, corps: NouvelleVersionCle) =>
  appeler<VersionCle>(`${base(projetId)}${cleId}/versions/`, { methode: "POST", corps });
