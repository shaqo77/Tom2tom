import type { ReactNode } from "react";
import { useId } from "react";

import "./ui.css";

export function Carte({ titre, children }: { titre?: string; children: ReactNode }) {
  const id = useId();
  return (
    <section className="carte" aria-labelledby={titre ? id : undefined}>
      {titre && (
        <h2 id={id} className="carte__titre">
          {titre}
        </h2>
      )}
      {children}
    </section>
  );
}
