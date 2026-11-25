import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ErreurApi } from "../../shared/api/client";
import { useMoi } from "../../shared/session/moi";
import { Bouton } from "../../shared/ui/Bouton";
import { Carte } from "../../shared/ui/Carte";
import { Champ } from "../../shared/ui/Champ";
import { Chargement } from "../../shared/ui/Chargement";
import { Message } from "../../shared/ui/Message";
import { Selecteur } from "../../shared/ui/Selecteur";
import { lireCatalogue } from "../devises/api";
import { TYPES_TAUX } from "../devises/types";
import type { TypeTaux } from "../devises/types";
import { enregistrerTaux, lireTaux, LIMITE } from "./api";
import "./taux.css";

/** Un taux est une chaîne décimale exacte, strictement positive : jamais un `number`, jamais d'exposant. */
function taux(brut: string): string | null {
  const valeur = brut.trim().replace(",", ".");
  return /^\d+(\.\d+)?$/.test(valeur) && /[1-9]/.test(valeur) ? valeur : null;
}

function texteErreur(erreur: unknown, secours: string): string {
  return erreur instanceof ErreurApi && erreur.message ? erreur.message : secours;
}

/**
 * Les taux de change de l'organisation : consulter (les plus récents d'abord) et enregistrer.
 * Un taux n'est jamais écrasé : le serveur refuse un second taux le même jour pour le même type.
 */
export function TauxDeChange() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const { data: moi } = useMoi();
  const [filtreDevise, definirFiltreDevise] = useState("");
  const [filtreType, definirFiltreType] = useState("");
  const [devise, definirDevise] = useState("");
  const [date, definirDate] = useState("");
  const [type, definirType] = useState<TypeTaux>("officiel");
  const [valeur, definirValeur] = useState("");
  const [source, definirSource] = useState("");
  const [erreurs, definirErreurs] = useState<{ date?: string; valeur?: string }>({});
  const [echec, definirEchec] = useState<string | null>(null);
  const [succes, definirSucces] = useState(false);
  const enVol = useRef(false);

  const catalogue = useQuery({ queryKey: ["devises"], queryFn: lireCatalogue, staleTime: Infinity });
  const liste = useQuery({
    queryKey: ["taux", filtreDevise, filtreType],
    queryFn: () => lireTaux({ ...(filtreDevise ? { devise: filtreDevise } : {}), ...(filtreType ? { type_taux: filtreType as TypeTaux } : {}) }),
  });
  const tenue = moi?.organisation?.monnaie_tenue;
  const atteintLimite = (liste.data?.length ?? 0) >= LIMITE;
  const peutParametrer = moi?.projets.some((p) => p.operations.includes("parametrer")) ?? false;
  const devises = (catalogue.data ?? []).filter((d) => d.code !== tenue); // la monnaie de tenue vaut 1 par définition
  const nomDevise = (code: string, label: { fr?: string; en?: string }) => `${code} · ${label[i18n.language === "en" ? "en" : "fr"] ?? code}`;
  const choisie = devise || devises[0]?.code || "";

  const ecriture = useMutation({
    mutationFn: enregistrerTaux,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["taux"] });
      definirSucces(true);
      definirValeur("");
    },
    onError: (e) => definirEchec(texteErreur(e, t("erreur.inconnue"))),
    onSettled: () => {
      enVol.current = false;
    },
  });

  function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    definirEchec(null);
    definirSucces(false);
    const exact = taux(valeur);
    const manques = {
      ...(date ? {} : { date: t("taux.date_requise") }),
      ...(exact ? {} : { valeur: t("taux.taux_invalide") }),
    };
    definirErreurs(manques);
    if (!date || !exact || enVol.current) return;
    enVol.current = true;
    ecriture.mutate({ devise: choisie, date, taux: exact, type_taux: type, ...(source.trim() ? { source: source.trim() } : {}) });
  }

  return (
    <>
      <div className="page__entete">
        <h1>{t("taux.titre")}</h1>
        <p>{t("taux.intro", { tenue: tenue ?? "" })}</p>
      </div>

      <Carte titre={t("taux.liste")}>
        <div className="taux__filtres">
          <Selecteur
            etiquette={t("taux.filtre_devise")}
            valeur={filtreDevise}
            options={[{ valeur: "", libelle: t("taux.toutes") }, ...devises.map((d) => ({ valeur: d.code, libelle: nomDevise(d.code, d.label) }))]}
            onChange={definirFiltreDevise}
          />
          <Selecteur
            etiquette={t("taux.filtre_type")}
            valeur={filtreType}
            options={[{ valeur: "", libelle: t("taux.tous") }, ...TYPES_TAUX.map((x) => ({ valeur: x, libelle: t(`devises.taux.${x}`) }))]}
            onChange={definirFiltreType}
          />
        </div>
        {liste.isPending && <Chargement />}
        {liste.error && <Message variante="danger">{texteErreur(liste.error, t("taux.erreur_lecture"))}</Message>}
        {liste.data && liste.data.length === 0 && <p>{t("taux.vide")}</p>}
        {liste.data && liste.data.length > 0 && (
          <>
            <div className="taux__defilement">
              <table className="taux__tableau">
                <caption className="visuellement-cache">{t("taux.enregistres")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("taux.col_date")}</th>
                    <th scope="col">{t("taux.col_devise")}</th>
                    <th scope="col">{t("taux.col_type")}</th>
                    <th scope="col">{t("taux.col_taux")}</th>
                    <th scope="col">{t("taux.col_source")}</th>
                  </tr>
                </thead>
                <tbody>
                  {liste.data.map((x) => (
                    <tr key={x.id}>
                      <td>{x.date}</td>
                      <td className="technique">{x.devise}</td>
                      <td>{t(`devises.taux.${x.type_taux}`)}</td>
                      <td className="taux__valeur">{x.taux}</td>
                      <td>{x.source || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {atteintLimite && <p>{t("taux.limite", { n: LIMITE })}</p>}
          </>
        )}
      </Carte>

      <Carte titre={t("taux.nouveau")}>
        {!peutParametrer ? (
          <p>{t("taux.lecture_seule")}</p>
        ) : (
          <form className="taux__formulaire" onSubmit={soumettre} noValidate>
            {succes && <Message variante="succes">{t("taux.enregistre")}</Message>}
            {echec && <Message variante="danger">{echec}</Message>}
            <Selecteur
              etiquette={t("taux.devise")}
              valeur={choisie}
              options={devises.map((d) => ({ valeur: d.code, libelle: nomDevise(d.code, d.label) }))}
              onChange={definirDevise}
            />
            <Champ
              etiquette={t("taux.date")}
              type="date"
              value={date}
              onChange={(e) => definirDate(e.target.value)}
              {...(erreurs.date ? { erreur: erreurs.date } : {})}
            />
            <Selecteur
              etiquette={t("taux.type")}
              valeur={type}
              options={TYPES_TAUX.map((x) => ({ valeur: x, libelle: t(`devises.taux.${x}`) }))}
              onChange={(v) => definirType(v as TypeTaux)}
            />
            <Champ
              etiquette={t("taux.taux")}
              inputMode="decimal"
              autoComplete="off"
              value={valeur}
              onChange={(e) => definirValeur(e.target.value)}
              {...(erreurs.valeur ? { erreur: erreurs.valeur } : {})}
            />
            <Champ etiquette={t("taux.source")} value={source} onChange={(e) => definirSource(e.target.value)} />
            <Bouton type="submit" chargement={ecriture.isPending}>
              {t("taux.enregistrer")}
            </Bouton>
          </form>
        )}
      </Carte>
    </>
  );
}
