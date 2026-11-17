import type { ReactNode } from "react";

import "./ui.css";

type Variante = "neutre" | "accent" | "succes" | "attention" | "alerte";

export function Pastille({ variante = "neutre", children }: { variante?: Variante; children: ReactNode }) {
  return <span className={`pastille pastille--${variante}`}>{children}</span>;
}
