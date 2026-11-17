import type { InputHTMLAttributes } from "react";
import { useId } from "react";

import "./ui.css";

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  etiquette: string;
  aide?: string;
  erreur?: string;
}

export function Champ({ etiquette, aide, erreur, className, ...reste }: Props) {
  const id = useId();
  const idAide = `${id}-aide`;
  const idErreur = `${id}-erreur`;
  const decrit = [aide ? idAide : null, erreur ? idErreur : null].filter(Boolean).join(" ");
  return (
    <div className="champ">
      <label className="champ__etiquette" htmlFor={id}>
        {etiquette}
      </label>
      <input
        id={id}
        className={["champ__saisie", className].filter(Boolean).join(" ")}
        aria-invalid={erreur ? true : undefined}
        aria-describedby={decrit || undefined}
        {...reste}
      />
      {aide && (
        <p id={idAide} className="champ__aide">
          {aide}
        </p>
      )}
      {erreur && (
        <p id={idErreur} className="champ__erreur" role="alert">
          {erreur}
        </p>
      )}
    </div>
  );
}
