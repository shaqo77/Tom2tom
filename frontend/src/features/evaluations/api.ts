import { appeler } from "../../shared/api/client";
import type { DecisionControle, DemandeDerogation, Derogation, EnAttente, EvaluationDetail, Evaluation, FiltreEvaluations, LigneDossier, StatutDerogation } from "./types";

const base = (projetId: string) => `/projets/${projetId}`;

export function lireEvaluations(projetId: string, filtre: FiltreEvaluations) {
  const recherche = new URLSearchParams();
  for (const [cle, valeur] of Object.entries(filtre)) if (valeur) recherche.set(cle, valeur);
  const suite = recherche.toString();
  return appeler<Evaluation[]>(`${base(projetId)}/evaluations-controles/${suite ? `?${suite}` : ""}`);
}

export const lireEvaluation = (projetId: string, evaluationId: string) =>
  appeler<EvaluationDetail>(`${base(projetId)}/evaluations-controles/${evaluationId}/`);

export const trancher = (projetId: string, evaluationId: string, decision: DecisionControle, motif: string) =>
  appeler<EvaluationDetail>(`${base(projetId)}/evaluations-controles/${evaluationId}/decision/`, { methode: "POST", corps: { decision, motif } });

export const justifier = (projetId: string, evaluationId: string, texte: string) =>
  appeler<EvaluationDetail>(`${base(projetId)}/evaluations-controles/${evaluationId}/justification/`, { methode: "POST", corps: { texte } });

export const demanderDerogation = (projetId: string, evaluationId: string, corps: DemandeDerogation) =>
  appeler<Derogation>(`${base(projetId)}/evaluations-controles/${evaluationId}/derogation/`, { methode: "POST", corps });

export const lireDerogations = (projetId: string, statut?: StatutDerogation) =>
  appeler<Derogation[]>(`${base(projetId)}/derogations/${statut ? `?statut=${statut}` : ""}`);

export const deciderDerogation = (projetId: string, derogationId: string, approuver: boolean, motif: string) =>
  appeler<Derogation>(`${base(projetId)}/derogations/${derogationId}/decision/`, { methode: "POST", corps: { approuver, motif } });

function objet(objetType: string, objetId: string) {
  const recherche = new URLSearchParams({ objet_type: objetType });
  if (objetId) recherche.set("objet_id", objetId);
  return recherche.toString();
}

export const lireEnAttente = (projetId: string, objetType: string, objetId: string) =>
  appeler<EnAttente[]>(`${base(projetId)}/controles-en-attente/?${objet(objetType, objetId)}`);

export const lireDossier = (projetId: string, objetType: string, objetId: string) =>
  appeler<LigneDossier[]>(`${base(projetId)}/dossier-conformite-objet/?${objet(objetType, objetId)}`);
