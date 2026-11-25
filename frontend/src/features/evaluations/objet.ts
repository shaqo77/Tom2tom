const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Ce que le dossier demande : le type d'objet est obligatoire, l'identifiant facultatif mais, s'il est donné, un UUID. */
export function lireObjet(type: string, id: string): { ok: true; type: string; id: string } | { ok: false; cle: string } {
  const t = type.trim();
  const i = id.trim();
  if (!t) return { ok: false, cle: "evaluations.dossier.faute_type" };
  if (i && !UUID.test(i)) return { ok: false, cle: "evaluations.dossier.faute_id" };
  return { ok: true, type: t, id: i };
}
