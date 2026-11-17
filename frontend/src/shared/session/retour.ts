/**
 * La page où revenir après la connexion. Elle vient de l'adresse, donc d'un tiers : on n'accepte
 * qu'un chemin DE CE SITE (« /… »), jamais une adresse complète ni « //hote » (redirection ouverte,
 * qui enverrait l'utilisateur, mot de passe tout juste saisi, sur le site d'un attaquant).
 */
export function retourSur(brut: unknown): string {
  if (typeof brut !== "string") return "/";
  if (!brut.startsWith("/") || brut.startsWith("//") || brut.startsWith("/\\")) return "/";
  if ([...brut].some((c) => c.charCodeAt(0) < 32)) return "/"; // retours à la ligne et autres caractères de contrôle
  if (brut.startsWith("/connexion")) return "/"; // ne pas revenir sur la page de connexion
  return brut;
}
