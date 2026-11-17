import type { Moi, Operation, ProjetAccessible } from "./types";

/** Les opérations dans l'ordre où l'interface les présente. */
export const OPERATIONS: Operation[] = [
  "consulter",
  "saisir",
  "valider",
  "comptabiliser",
  "parametrer",
  "exporter",
  "publier",
  "voir_numero_compte",
];

/**
 * Faut-il MONTRER cette action ? Une question d'interface, jamais de sécurité : le serveur revérifie
 * chaque action (« l'interface masque, elle ne protège pas »).
 */
export function peut(projet: ProjetAccessible | undefined, operation: Operation): boolean {
  return projet?.operations.includes(operation) ?? false;
}

export function projetParId(moi: Moi | null | undefined, id: string): ProjetAccessible | undefined {
  return moi?.projets.find((p) => p.id === id);
}
