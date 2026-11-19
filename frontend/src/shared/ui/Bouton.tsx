import type { ButtonHTMLAttributes } from "react";

import "./ui.css";

type Variante = "primaire" | "secondaire" | "discret" | "danger";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: Variante;
  chargement?: boolean;
}

export function Bouton({ variante = "primaire", chargement = false, className, children, disabled, type = "button", ...reste }: Props) {
  return (
    <button
      type={type}
      className={["bouton", `bouton--${variante}`, className].filter(Boolean).join(" ")}
      disabled={disabled || chargement}
      aria-busy={chargement || undefined}
      {...reste}
    >
      {chargement && <span className="bouton__rotation" aria-hidden="true" />}
      {children}
    </button>
  );
}
