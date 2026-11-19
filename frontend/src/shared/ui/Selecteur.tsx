import { useId } from "react";

import "./ui.css";

export interface OptionSelecteur {
  valeur: string;
  libelle: string;
}

/**
 * Une liste déroulante avec son étiquette. L'étiquette est LIÉE au champ (`htmlFor`), jamais autour
 * de lui : une liste placée dans son étiquette fait entrer ses options dans le nom du champ
 * (« Projet Tous les projets ») dans un vrai navigateur.
 */
export function Selecteur({
  etiquette,
  valeur,
  options,
  onChange,
}: {
  etiquette: string;
  valeur: string;
  options: OptionSelecteur[];
  onChange: (valeur: string) => void;
}) {
  const id = useId();
  return (
    <div className="reglage">
      <label className="reglage__nom" htmlFor={id}>
        {etiquette}
      </label>
      <select id={id} value={valeur} onChange={(e) => onChange(e.target.value)} className="reglage__choix">
        {options.map((o) => (
          <option key={o.valeur} value={o.valeur}>
            {o.libelle}
          </option>
        ))}
      </select>
    </div>
  );
}
