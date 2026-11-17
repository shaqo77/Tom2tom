import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ErreurApi } from "../../shared/api/client";
import { peut, projetParId } from "../../shared/session/droits";
import { useMoi } from "../../shared/session/moi";
import { Bouton } from "../../shared/ui/Bouton";
import { Carte } from "../../shared/ui/Carte";
import { Champ } from "../../shared/ui/Champ";
import { Chargement } from "../../shared/ui/Chargement";
import { Message } from "../../shared/ui/Message";
import { Pastille } from "../../shared/ui/Pastille";
import { Selecteur } from "../../shared/ui/Selecteur";
import { aujourdhui } from "../tableau/api";
import { libelleProjet } from "../projets/libelle";
import { lireCatalogue, lireHistorique, lireReglages, poserReglages } from "./api";
import { TYPES_TAUX } from "./types";
import type { DeviseCatalogue, NouvelleVersion, Provenance, TypeTaux, VersionReglages } from "./types";
import "./devises.css";

/**
 * Les réglages de devises d'une organisation ou d'un projet. Rien n'est écrit dans le code : tout
 * vient du serveur. Une valeur vide signifie « hérite du niveau au-dessus » ; une nouvelle version
 * REMPLACE la précédente à sa date d'effet (l'ancienne reste dans l'historique).
 */
export function ReglagesDevises() {
  const { t, i18n } = useTranslation();
  const { data: moi } = useMoi();
  const { portee } = useSearch({ from: "/protege/parametres-devises" });
  const navigate = useNavigate();
  const projet = portee ? projetParId(moi, portee) : undefined;
  const jour = aujourdhui();

  const catalogue = useQuery({ queryKey: ["devises"], queryFn: lireCatalogue, staleTime: Infinity });
  const reglages = useQuery({ queryKey: ["reglages-devises", portee ?? "org", jour], queryFn: () => lireReglages(jour, portee) });
  const historique = useQuery({ queryKey: ["historique-devises", portee ?? "org"], queryFn: () => lireHistorique(portee) });

  const peutParametrer = portee
    ? peut(projet, "parametrer")
    : (moi?.projets.some((p) => p.operations.includes("parametrer")) ?? false);

  if (portee && !projet) return <Message variante="attention">{t("projets.introuvable")}</Message>;

  const ouverte = historique.data?.find((v) => v.valid_to === null);
  const nomDevise = (d: DeviseCatalogue) => d.label[i18n.language === "en" ? "en" : "fr"] ?? d.code;
  const provenance = (p: Provenance) =>
    p === null ? (
      <Pastille>{t("devises.non_parametre")}</Pastille>
    ) : p === "projet" ? (
      <Pastille variante="accent">{t("devises.propre_projet")}</Pastille>
    ) : (
      <Pastille variante="selection">{t(portee ? "devises.herite_organisation" : "devises.defini_organisation")}</Pastille>
    );

  return (
    <>
      <div className="page__entete">
        <h1>{t("devises.titre")}</h1>
        <p>{t("devises.intro")}</p>
      </div>
      <Carte>
        <Selecteur
          etiquette={t("devises.portee")}
          valeur={portee ?? ""}
          options={[
            { valeur: "", libelle: t("devises.organisation", { nom: moi?.organisation?.raison_sociale ?? "" }) },
            ...(moi?.projets ?? []).map((p) => ({ valeur: p.id, libelle: `${p.code} · ${libelleProjet(p, i18n.language)}` })),
          ]}
          onChange={(v) => void navigate({ to: "/parametres-devises", search: v ? { portee: v } : {}, replace: true })}
        />
      </Carte>

      <Carte titre={t("devises.en_vigueur", { jour })}>
        {reglages.isPending && <Chargement />}
        {reglages.error && <Message variante="danger">{t("devises.erreur_lecture")}</Message>}
        {reglages.data && (
          <div className="reglages__grille">
            <div>
              <h3>{t("devises.reference")}</h3>
              <p className="reglages__valeur">
                <strong className="technique">{reglages.data.devise_reference ?? "—"}</strong>
                {provenance(reglages.data.origine.devise_reference)}
              </p>
            </div>
            <div>
              <h3>{t("devises.type_taux")}</h3>
              <p className="reglages__valeur">
                <strong>{reglages.data.type_taux ? t(`devises.taux.${reglages.data.type_taux}`) : "—"}</strong>
                {provenance(reglages.data.origine.type_taux)}
              </p>
            </div>
            <div>
              <h3>{t("devises.autorisees")}</h3>
              <p className="reglages__valeur">
                {reglages.data.devises_autorisees ? (
                  <strong className="technique">{reglages.data.devises_autorisees.join(", ")}</strong>
                ) : (
                  <strong>{t("devises.aucune_restriction")}</strong>
                )}
                {provenance(reglages.data.origine.devises_autorisees)}
              </p>
            </div>
          </div>
        )}
      </Carte>

      <Carte titre={t("devises.nouvelle_version")}>
        {!peutParametrer ? (
          <p>{t("devises.lecture_seule")}</p>
        ) : catalogue.data && historique.data ? (
          <FormulaireVersion
            // Il repart des valeurs de la version ouverte (une nouvelle version REMPLACE l'ancienne), donc
            // n'apparaît qu'une fois l'historique chargé. Sa clé ne dépend que de la portée : après un
            // enregistrement il garde son message de succès au lieu de se recréer.
            key={portee ?? "org"}
            portee={portee}
            catalogue={catalogue.data}
            nomDevise={nomDevise}
            depart={ouverte}
            herite={portee !== undefined}
          />
        ) : (
          <Chargement />
        )}
      </Carte>

      <Carte titre={t("devises.historique")}>
        {historique.data && historique.data.length === 0 && <p>{t("devises.historique_vide")}</p>}
        {historique.data && historique.data.length > 0 && (
          <div className="reglages__defilement">
            <table className="reglages__tableau">
              <caption className="visuellement-cache">{t("devises.historique")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("devises.col_version")}</th>
                  <th scope="col">{t("devises.col_du")}</th>
                  <th scope="col">{t("devises.col_au")}</th>
                  <th scope="col">{t("devises.reference")}</th>
                  <th scope="col">{t("devises.type_taux")}</th>
                  <th scope="col">{t("devises.autorisees")}</th>
                  <th scope="col">{t("devises.motif")}</th>
                </tr>
              </thead>
              <tbody>
                {historique.data.map((v) => (
                  <tr key={v.id}>
                    <th scope="row">{v.version}</th>
                    <td>{v.valid_from}</td>
                    <td>{v.valid_to ?? t("devises.en_cours")}</td>
                    <td className="technique">{v.devise_reference ?? "—"}</td>
                    <td>{v.type_taux ? t(`devises.taux.${v.type_taux}`) : "—"}</td>
                    <td className="technique">{v.devises_autorisees?.join(", ") ?? "—"}</td>
                    <td>{v.motif || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Carte>
    </>
  );
}

function FormulaireVersion({
  portee,
  catalogue,
  nomDevise,
  depart,
  herite,
}: {
  portee: string | undefined;
  catalogue: DeviseCatalogue[];
  nomDevise: (d: DeviseCatalogue) => string;
  depart: VersionReglages | undefined;
  herite: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [restreindre, definirRestreindre] = useState(depart?.devises_autorisees != null);
  const [choisies, definirChoisies] = useState<Set<string>>(new Set(depart?.devises_autorisees ?? []));
  const [reference, definirReference] = useState(depart?.devise_reference ?? "");
  const [typeTaux, definirTypeTaux] = useState<string>(depart?.type_taux ?? "");
  const [dateEffet, definirDateEffet] = useState(aujourdhui());
  const [motif, definirMotif] = useState("");
  const [erreurLocale, definirErreurLocale] = useState<string | null>(null);

  const pose = useMutation({
    mutationFn: (corps: NouvelleVersion) => poserReglages(corps, portee),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["reglages-devises"] });
      await queryClient.invalidateQueries({ queryKey: ["historique-devises"] });
    },
  });

  function envoyer(e: FormEvent) {
    e.preventDefault();
    definirErreurLocale(null);
    const corps: NouvelleVersion = { date_effet: dateEffet };
    if (restreindre) corps.devises_autorisees = [...choisies].sort();
    if (reference) corps.devise_reference = reference;
    if (typeTaux) corps.type_taux = typeTaux as TypeTaux;
    if (motif.trim()) corps.motif = motif.trim();
    if (!corps.devises_autorisees && !corps.devise_reference && !corps.type_taux) {
      definirErreurLocale(t("devises.rien_a_parametrer"));
      return;
    }
    if (corps.devises_autorisees?.length === 0) {
      definirErreurLocale(t("devises.liste_vide"));
      return;
    }
    pose.mutate(corps);
  }

  const vide = herite ? t("devises.heriter") : t("devises.non_parametre");
  return (
    <form className="reglages__formulaire" onSubmit={envoyer} noValidate>
      <Selecteur
        etiquette={t("devises.reference")}
        valeur={reference}
        options={[{ valeur: "", libelle: vide }, ...catalogue.map((d) => ({ valeur: d.code, libelle: `${d.code} · ${nomDevise(d)}` }))]}
        onChange={definirReference}
      />
      <Selecteur
        etiquette={t("devises.type_taux")}
        valeur={typeTaux}
        options={[{ valeur: "", libelle: vide }, ...TYPES_TAUX.map((x) => ({ valeur: x, libelle: t(`devises.taux.${x}`) }))]}
        onChange={definirTypeTaux}
      />
      <label className="reglages__case">
        <input type="checkbox" checked={restreindre} onChange={(e) => definirRestreindre(e.target.checked)} />
        <span>{t("devises.restreindre")}</span>
      </label>
      {restreindre && (
        <fieldset className="reglages__liste">
          <legend>{t("devises.autorisees")}</legend>
          {catalogue.map((d) => (
            <label key={d.code} className="reglages__case">
              <input
                type="checkbox"
                checked={choisies.has(d.code)}
                onChange={(e) => {
                  const suite = new Set(choisies);
                  if (e.target.checked) suite.add(d.code);
                  else suite.delete(d.code);
                  definirChoisies(suite);
                }}
              />
              <span className="technique">{d.code}</span>
            </label>
          ))}
        </fieldset>
      )}
      <Champ etiquette={t("devises.date_effet")} type="date" value={dateEffet} onChange={(e) => definirDateEffet(e.target.value)} aide={t("devises.date_effet_aide")} />
      <Champ etiquette={t("devises.motif")} value={motif} onChange={(e) => definirMotif(e.target.value)} />
      {erreurLocale && <Message variante="attention">{erreurLocale}</Message>}
      {pose.error && (
        <Message variante="danger">
          {pose.error instanceof ErreurApi && pose.error.statut < 500 ? pose.error.message : t("erreur.inconnue")}
        </Message>
      )}
      {pose.isSuccess && <Message variante="succes">{t("devises.enregistre")}</Message>}
      <div>
        <Bouton type="submit" chargement={pose.isPending}>
          {t("devises.enregistrer")}
        </Bouton>
      </div>
    </form>
  );
}
