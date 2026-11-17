import type { LibelleMultilingue, ProjetAccessible } from "../../shared/session/types";

/** Le libellé d'un projet dans la langue de l'interface, sinon dans l'autre, sinon son code. */
export function libelleProjet(projet: Pick<ProjetAccessible, "code" | "libelle">, langue: string): string {
  const l: LibelleMultilingue = projet.libelle;
  const choisie = langue === "en" ? l.en ?? l.fr : l.fr ?? l.en;
  return choisie?.trim() || projet.code;
}
