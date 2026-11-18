import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ErreurApi } from "../../shared/api/client";
import { Carte } from "../../shared/ui/Carte";
import { Chargement } from "../../shared/ui/Chargement";
import { Message } from "../../shared/ui/Message";
import { Montant } from "../../shared/ui/Montant";
import { Pastille } from "../../shared/ui/Pastille";
import { Selecteur } from "../../shared/ui/Selecteur";
import { lireConsolidation } from "./api";
import type { CodeIndicateur, FiltresTableau, Origine } from "./types";

const INDICATEURS: CodeIndicateur[] = [
  "budget_approuve",
  "budget_initial",
  "execution_engage",
  "execution_consomme",
  "financements_accordes",
  "financements_recus",
  "soldes_comptables",
  "soldes_releves",
  "engagements_ouverts",
  "avances_non_justifiees",
];
const TYPES_TAUX = ["officiel", "bailleur", "cloture", "budget"];
const DECIMALES_PAR_DEFAUT = 2;

/**
 * Un total dans UNE devise de référence. La devise et le type de taux viennent des réglages de
 * l'organisation ou du projet ; en choisir un ici l'emporte, mais rien n'est jamais deviné : sans
 * réglage ni choix, le serveur dit pourquoi il ne consolide pas, et cet écran le répète tel quel.
 */
export function Consolidation({
  filtres,
  devises,
}: {
  filtres: FiltresTableau & { jour: string };
  devises: Record<string, number>;
}) {
  const { t } = useTranslation();
  const [indicateur, definirIndicateur] = useState<CodeIndicateur>("financements_accordes");
  const [reference, definirReference] = useState("");
  const [typeTaux, definirTypeTaux] = useState("");

  const { data, error, isPending } = useQuery({
    queryKey: ["consolidation", indicateur, filtres, reference, typeTaux],
    queryFn: ({ signal }) =>
      lireConsolidation(
        indicateur,
        filtres,
        { ...(reference ? { devise_reference: reference } : {}), ...(typeTaux ? { type_taux: typeTaux } : {}) },
        signal,
      ),
  });
  const origine = (o: Origine | null | undefined) => (o ? <Pastille variante="selection">{t(`tableau.origine.${o}`)}</Pastille> : null);

  return (
    <Carte titre={t("tableau.consolidation.titre")}>
      <p>{t("tableau.consolidation.intro")}</p>
      <div className="filtres">
        <Selecteur
          etiquette={t("tableau.consolidation.indicateur")}
          valeur={indicateur}
          options={INDICATEURS.map((c) => ({ valeur: c, libelle: t(`tableau.i.${c}`) }))}
          onChange={(v) => definirIndicateur(v as CodeIndicateur)}
        />
        <Selecteur
          etiquette={t("tableau.consolidation.reference")}
          valeur={reference}
          options={[
            { valeur: "", libelle: t("tableau.consolidation.selon_reglages") },
            ...Object.keys(devises)
              .sort()
              .map((d) => ({ valeur: d, libelle: d })),
          ]}
          onChange={definirReference}
        />
        <Selecteur
          etiquette={t("tableau.consolidation.type_taux")}
          valeur={typeTaux}
          options={[
            { valeur: "", libelle: t("tableau.consolidation.selon_reglages") },
            ...TYPES_TAUX.map((x) => ({ valeur: x, libelle: t(`devises.taux.${x}`) })),
          ]}
          onChange={definirTypeTaux}
        />
      </div>
      <div aria-live="polite">
        {isPending && <Chargement />}
        {error && (
          <Message variante="danger">
            {error instanceof ErreurApi && error.statut < 500 ? error.message : t("erreur.inconnue")}
          </Message>
        )}
        {data && !data.consolide && (
          <Message variante="attention">{data.raison ?? t("erreur.inconnue")}</Message>
        )}
        {data?.consolide && data.montant !== null && data.devise_reference && (
          <div className="consolidation__resultat">
            <p className="indicateur__valeur chiffres">
              <Montant
                valeur={data.montant}
                decimales={devises[data.devise_reference] ?? DECIMALES_PAR_DEFAUT}
                devise={data.devise_reference}
              />
            </p>
            <p className="consolidation__origines">
              {origine(data.origine.devise_reference)} {origine(data.origine.type_taux)}
            </p>
            {data.methode && <p className="technique-texte">{data.methode}</p>}
            {Object.keys(data.taux).length > 0 && (
              <ul className="liste-pastilles" aria-label={t("tableau.consolidation.taux_utilises")}>
                {Object.entries(data.taux)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([devise, { taux, date }]) => (
                    <li key={devise}>
                      <Pastille>
                        {devise} · {taux} · {date}
                      </Pastille>
                    </li>
                  ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </Carte>
  );
}
