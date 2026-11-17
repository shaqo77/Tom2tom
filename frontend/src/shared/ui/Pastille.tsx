import type { ReactNode } from "react";

import "./ui.css";

/** accent : action · selection : navigation et sélection · donnees : séries de données · chaud : mise en avant. */
type Variante = "neutre" | "accent" | "selection" | "donnees" | "chaud" | "succes" | "attention" | "alerte";

export function Pastille({ variante = "neutre", children }: { variante?: Variante; children: ReactNode }) {
  return <span className={`pastille pastille--${variante}`}>{children}</span>;
}
