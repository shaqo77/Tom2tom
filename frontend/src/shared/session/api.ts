import { ErreurApi, appeler } from "../api/client";
import type { Moi } from "./types";

/** Qui est connecté ? `null` quand personne : ce n'est pas une erreur, c'est l'état de départ. */
export async function lireMoi(): Promise<Moi | null> {
  try {
    return await appeler<Moi>("/session/moi/", { sansAlerteSession: true });
  } catch (erreur) {
    if (erreur instanceof ErreurApi && erreur.statut === 401) return null;
    throw erreur;
  }
}

export function seConnecter(identifiant: string, motDePasse: string): Promise<Moi> {
  return appeler<Moi>("/session/connexion/", {
    methode: "POST",
    corps: { identifiant, mot_de_passe: motDePasse },
  });
}

export function seDeconnecter(): Promise<void> {
  return appeler<void>("/session/deconnexion/", { methode: "POST" });
}

export function enregistrerLangue(langue: string): Promise<Moi> {
  return appeler<Moi>("/session/moi/", { methode: "PATCH", corps: { langue } });
}
