import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { ErreurApi } from "../../shared/api/client";
import type { Appel } from "./types";

function texteErreur(erreur: unknown, secours: string): string {
  return erreur instanceof ErreurApi && erreur.message ? erreur.message : secours;
}

/**
 * Une écriture déclenchée à la demande : un seul appel à la fois (un double clic n'envoie qu'une demande), le refus du
 * serveur gardé tel quel dans `echec`, `attente` pendant l'envoi. `lancer()` rend `false` si un appel est déjà en vol.
 */
export function useAction<T>(appel: Appel<T>, apres: () => void, t: (c: string) => string) {
  const [echec, definirEchec] = useState<string | null>(null);
  const enVol = useRef(false);
  const mutation = useMutation({
    mutationFn: appel,
    onSuccess: apres,
    onError: (e) => definirEchec(texteErreur(e, t("erreur.inconnue"))),
    onSettled: () => {
      enVol.current = false;
    },
  });
  const lancer = () => {
    if (enVol.current) return false;
    enVol.current = true;
    definirEchec(null);
    mutation.mutate();
    return true;
  };
  return { echec, lancer, attente: mutation.isPending };
}

