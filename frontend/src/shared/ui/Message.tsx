import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import "./ui.css";

type Variante = "info" | "succes" | "attention" | "danger";

/**
 * Un message à l'utilisateur. Le type est écrit en toutes lettres (« Erreur », « Attention ») :
 * la couleur ne porte jamais seule le sens. Une erreur ou une attention est annoncée tout de suite
 * aux lecteurs d'écran ; le reste, poliment.
 */
export function Message({ variante, children }: { variante: Variante; children: ReactNode }) {
  const { t } = useTranslation();
  const urgent = variante === "danger" || variante === "attention";
  return (
    <div className={`message message--${variante}`} role={urgent ? "alert" : "status"}>
      <strong className="message__type">{t(`message.${variante}`)}</strong>
      <span>{children}</span>
    </div>
  );
}
