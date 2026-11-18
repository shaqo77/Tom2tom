import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { ErreurApi } from "../../shared/api/client";
import { useMoi } from "../../shared/session/moi";
import { Bouton } from "../../shared/ui/Bouton";
import { Carte } from "../../shared/ui/Carte";
import { Chargement } from "../../shared/ui/Chargement";
import { Message } from "../../shared/ui/Message";
import { Montant } from "../../shared/ui/Montant";
import { Pastille } from "../../shared/ui/Pastille";
import { Selecteur } from "../../shared/ui/Selecteur";
import { enPourcentage } from "../../shared/money/montant";
import { libelleProjet } from "../projets/libelle";
import { aujourdhui, lireTableau } from "./api";
import { Consolidation } from "./Consolidation";
import { IndicateurMontants, IndicateurTaux } from "./Indicateur";
import type { CodeIndicateur, FiltresTableau, MontantsParDevise, TableauDto } from "./types";
import "./tableau.css";

const DECIMALES_PAR_DEFAUT = 2;

/** Des modifications de filtres : une valeur `undefined` retire le filtre. */
type Modifs = { [K in keyof FiltresTableau]?: FiltresTableau[K] | undefined };

function plusieursDevises(tableau: TableauDto): boolean {
  return Object.values(tableau.indicateurs).some((i) => Object.keys(i.total_par_devise).length > 1);
}

export function TableauDeBord() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const recherche = useSearch({ from: "/protege/tableau-de-bord" });
  const { data: moi } = useMoi();
  const jour = recherche.jour ?? aujourdhui();
  const filtres: FiltresTableau & { jour: string } = { ...nettoyer(recherche), jour };

  const { data: tableau, error, isPending, isFetching, refetch } = useQuery({
    queryKey: ["tableau", filtres],
    queryFn: ({ signal }) => lireTableau(filtres, signal),
    placeholderData: keepPreviousData,
  });

  function changer(modifs: Modifs) {
    void navigate({
      to: "/tableau-de-bord",
      search: (precedent) => nettoyer({ ...precedent, ...modifs }),
      replace: true,
    });
  }

  const langue = i18n.language === "pseudo" ? "fr" : i18n.language;
  const jourLisible = new Intl.DateTimeFormat(langue, { dateStyle: "long" }).format(
    new Date(`${jour}T12:00:00`),
  );
  const devisesConnues = Object.keys(tableau?.devises ?? {});
  const choisis = new Set(recherche.projets ?? []);

  return (
    <>
      <div className="page__entete">
        <h1>{t("tableau.titre")}</h1>
        <p className="page__sous-titre">{t("tableau.sous_titre", { jour: jourLisible })}</p>
      </div>

      <Carte titre={t("tableau.filtres")}>
        <form className="filtres" onSubmit={(e) => e.preventDefault()}>
          <div className="reglage">
            <label className="reglage__nom" htmlFor="filtre-jour">
              {t("tableau.jour")}
            </label>
            <input
              id="filtre-jour"
              type="date"
              className="reglage__choix"
              value={jour}
              onChange={(e) => e.target.value && changer({ jour: e.target.value })}
            />
          </div>
          <Selecteur
            etiquette={t("tableau.statut")}
            valeur={recherche.statut ?? ""}
            options={[
              { valeur: "", libelle: t("tableau.statut_actifs") },
              { valeur: "tous", libelle: t("tableau.statut_tous") },
            ]}
            onChange={(v) => changer(v === "tous" ? { statut: "tous" } : { statut: undefined })}
          />
          <Selecteur
            etiquette={t("tableau.devise")}
            valeur={recherche.devise ?? ""}
            options={[
              { valeur: "", libelle: t("tableau.toutes_devises") },
              ...[...new Set([...devisesConnues, ...(recherche.devise ? [recherche.devise] : [])])]
                .sort()
                .map((d) => ({ valeur: d, libelle: d })),
            ]}
            onChange={(v) => changer({ devise: v || undefined })}
          />
          {moi && moi.projets.length > 1 && (
            <fieldset className="filtres__projets">
              <legend>{t("tableau.projets")}</legend>
              {moi.projets.map((p) => (
                <label key={p.id} className="filtres__case">
                  <input
                    type="checkbox"
                    checked={choisis.size === 0 || choisis.has(p.id)}
                    onChange={(e) => {
                      const tous = moi.projets.map((x) => x.id);
                      const actuels = new Set(choisis.size === 0 ? tous : choisis);
                      if (e.target.checked) actuels.add(p.id);
                      else actuels.delete(p.id);
                      changer({ projets: actuels.size === tous.length || actuels.size === 0 ? undefined : [...actuels] });
                    }}
                  />
                  <span className="technique">{p.code}</span>
                </label>
              ))}
            </fieldset>
          )}
          <Bouton variante="discret" onClick={() => void navigate({ to: "/tableau-de-bord", search: {}, replace: true })}>
            {t("tableau.reinitialiser")}
          </Bouton>
        </form>
      </Carte>

      <div aria-live="polite" aria-busy={isFetching} className="tableau__etat">
        {isPending && (
          <p className="tableau__chargement">
            <Chargement /> <span>{t("tableau.chargement")}</span>
          </p>
        )}
        {error && !tableau && (
          <>
            <Message variante="danger">
              {t("tableau.erreur")}{" "}
              {error instanceof ErreurApi ? t(`erreur.${error.code}`, { defaultValue: t("erreur.inconnue") }) : null}
            </Message>
            <Bouton variante="secondaire" onClick={() => void refetch()}>
              {t("commun.reessayer")}
            </Bouton>
          </>
        )}
      </div>

      {tableau && tableau.projets.length > 0 && <Consolidation filtres={filtres} devises={tableau.devises} />}
      {tableau && <Contenu tableau={tableau} langue={langue} filtres={filtres} />}
    </>
  );
}

function Contenu({ tableau, langue, filtres }: { tableau: TableauDto; langue: string; filtres: FiltresTableau & { jour: string } }) {
  const { t, i18n } = useTranslation();
  const { indicateurs: ind, devises, conformite, projets } = tableau;

  if (projets.length === 0) return <Message variante="info">{t("tableau.vide")}</Message>;

  return (
    <>
      {tableau.avertissements.length > 0 && (
        <section aria-labelledby="t-avertissements" className="tableau__avertissements">
          <h2 id="t-avertissements" className="visuellement-cache">
            {t("tableau.section_avertissements")}
          </h2>
          {tableau.avertissements.map((a) => (
            <Message key={a.code} variante="attention">
              {a.message}
            </Message>
          ))}
        </section>
      )}
      {plusieursDevises(tableau) && <Message variante="info">{t("tableau.devises_separees")}</Message>}

      <Carte titre={t("tableau.section_projets")}>
        <p className="chiffres">{t("tableau.nb_projets", { count: projets.length })}</p>
        <ul className="liste-pastilles">
          {projets.map((p) => (
            <li key={p.id}>
              <Pastille variante={p.configuration === "configure" ? "selection" : "neutre"}>
                {p.code}
                {" · "}
                {t(`tableau.${p.configuration}`)}
              </Pastille>
            </li>
          ))}
        </ul>
      </Carte>

      <Carte titre={t("tableau.section_budget")}>
        <div className="indicateurs">
          <IndicateurMontants titre={t("tableau.i.budget_approuve")} montants={ind.budget_approuve.total_par_devise} devises={devises} />
          <IndicateurMontants titre={t("tableau.i.budget_initial")} montants={ind.budget_initial.total_par_devise} devises={devises} />
          <IndicateurMontants titre={t("tableau.i.execution_engage")} montants={ind.execution_engage.total_par_devise} devises={devises} />
          <IndicateurMontants titre={t("tableau.i.execution_consomme")} montants={ind.execution_consomme.total_par_devise} devises={devises} />
          <IndicateurTaux titre={t("tableau.i.taux_execution")} taux={tableau.taux_execution} />
        </div>
        <Composantes tableau={tableau} langue={langue} />
      </Carte>

      <Carte titre={t("tableau.section_financements")}>
        <div className="indicateurs">
          <IndicateurMontants titre={t("tableau.i.financements_accordes")} montants={ind.financements_accordes.total_par_devise} devises={devises} />
          <IndicateurMontants titre={t("tableau.i.financements_recus")} montants={ind.financements_recus.total_par_devise} devises={devises} />
        </div>
      </Carte>

      <Carte titre={t("tableau.section_tresorerie")}>
        <div className="indicateurs">
          <IndicateurMontants titre={t("tableau.i.soldes_comptables")} montants={ind.soldes_comptables.total_par_devise} devises={devises} />
          <IndicateurMontants titre={t("tableau.i.soldes_releves")} montants={ind.soldes_releves.total_par_devise} devises={devises} />
        </div>
      </Carte>

      <Carte titre={t("tableau.section_engagements")}>
        <div className="indicateurs">
          <IndicateurMontants titre={t("tableau.i.engagements_ouverts")} montants={ind.engagements_ouverts.total_par_devise} devises={devises} />
          <IndicateurMontants titre={t("tableau.i.avances_non_justifiees")} montants={ind.avances_non_justifiees.total_par_devise} devises={devises} />
        </div>
      </Carte>

      <Carte titre={t("tableau.section_conformite")}>
        <div className="indicateurs">
          <Compte titre={t("tableau.c.a_remettre")} valeur={conformite.totaux.echeances_a_remettre} />
          <Compte titre={t("tableau.c.imminentes")} valeur={conformite.totaux.echeances_imminentes} variante="attention" />
          <Compte titre={t("tableau.c.en_retard")} valeur={conformite.totaux.echeances_en_retard} variante="alerte" />
          <Compte titre={t("tableau.c.en_escalade")} valeur={conformite.totaux.echeances_en_escalade} variante="alerte" />
          <Compte titre={t("tableau.c.rapports_en_attente")} valeur={conformite.totaux.rapports_en_attente} />
          <Compte titre={t("tableau.c.anomalies_ouvertes")} valeur={conformite.totaux.anomalies_ouvertes} variante="alerte" />
          <div className="indicateur">
            <h3 className="indicateur__titre">{t("tableau.c.taux_acceptation")}</h3>
            {conformite.taux_acceptation === null ? (
              <p className="indicateur__vide">
                <span aria-hidden="true">—</span> <span className="technique-texte">{t("tableau.c.sans_envoi")}</span>
              </p>
            ) : (
              <p className="indicateur__valeur chiffres" dir="ltr">
                {enPourcentage(conformite.taux_acceptation, langue, 1)}
              </p>
            )}
          </div>
        </div>
      </Carte>

      <Carte titre={t("tableau.section_par_projet")}>
        <div className="table-defilante">
          <table className="table">
            <caption className="visuellement-cache">{t("tableau.section_par_projet")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("tableau.col_projet")}</th>
                <th scope="col">{t("tableau.col_bailleurs")}</th>
                <th scope="col">{t("tableau.col_budget")}</th>
                <th scope="col">{t("tableau.col_consomme")}</th>
                <th scope="col">{t("tableau.col_soldes")}</th>
                <th scope="col">{t("tableau.col_alertes")}</th>
              </tr>
            </thead>
            <tbody>
              {projets.map((p) => {
                const c = conformite.par_projet[p.id];
                return (
                  <tr key={p.id}>
                    <th scope="row">
                      <Link to="/projets/$projetId" params={{ projetId: p.id }}>
                        <span className="technique">{p.code}</span>
                      </Link>
                      <span className="table__libelle">{libelleProjet(p, i18n.language)}</span>
                    </th>
                    <td>{p.bailleurs.join(", ") || "—"}</td>
                    <td>
                      <Cellule montants={ind.budget_approuve.par_projet[p.id]} devises={devises} projetId={p.id} projetCode={p.code} indicateur="budget_approuve" filtres={filtres} />
                    </td>
                    <td>
                      <Cellule montants={ind.execution_consomme.par_projet[p.id]} devises={devises} projetId={p.id} projetCode={p.code} indicateur="execution_consomme" filtres={filtres} />
                    </td>
                    <td>
                      <Cellule montants={ind.soldes_comptables.par_projet[p.id]} devises={devises} projetId={p.id} projetCode={p.code} indicateur="soldes_comptables" filtres={filtres} />
                    </td>
                    <td>
                      {c && (c.echeances_en_retard + c.echeances_en_escalade > 0 || c.anomalies_ouvertes > 0) ? (
                        <>
                          {c.echeances_en_retard + c.echeances_en_escalade > 0 && (
                            <Pastille variante="alerte">
                              {t("tableau.retards", { retards: c.echeances_en_retard + c.echeances_en_escalade })}
                            </Pastille>
                          )}{" "}
                          {c.anomalies_ouvertes > 0 && (
                            <Pastille variante="chaud">{t("tableau.anomalies", { anomalies: c.anomalies_ouvertes })}</Pastille>
                          )}
                        </>
                      ) : (
                        <span className="technique-texte">{t("tableau.rien")}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Carte>
    </>
  );
}

function Compte({ titre, valeur, variante }: { titre: string; valeur: number; variante?: "attention" | "alerte" }) {
  return (
    <div className="indicateur">
      <h3 className="indicateur__titre">{titre}</h3>
      <p className="indicateur__valeur chiffres">
        {valeur}
        {variante && valeur > 0 && <span className={`pastille pastille--${variante} indicateur__signal`} aria-hidden="true">!</span>}
      </p>
    </div>
  );
}

function Montants({ montants, devises }: { montants: MontantsParDevise | undefined; devises: Record<string, number> }) {
  const lignes = Object.entries(montants ?? {}).sort(([a], [b]) => a.localeCompare(b));
  if (lignes.length === 0) return <span aria-hidden="true">—</span>;
  return (
    <ul className="indicateur__lignes">
      {lignes.map(([devise, valeur]) => (
        <li key={devise}>
          <Montant valeur={valeur} decimales={devises[devise] ?? DECIMALES_PAR_DEFAUT} devise={devise} />
        </li>
      ))}
    </ul>
  );
}

function Composantes({ tableau, langue }: { tableau: TableauDto; langue: string }) {
  const { t } = useTranslation();
  const composantes = Object.entries(tableau.par_composante).sort(([a], [b]) => a.localeCompare(b));
  if (composantes.length === 0) return null;
  return (
    <section aria-labelledby="t-composantes" className="composantes">
      <h3 id="t-composantes">{t("tableau.section_composantes")}</h3>
      <div className="table-defilante">
        <table className="table">
          <thead>
            <tr>
              <th scope="col">{t("tableau.col_composante")}</th>
              <th scope="col">{t("tableau.col_budget")}</th>
              <th scope="col">{t("tableau.col_engage")}</th>
              <th scope="col">{t("tableau.col_consomme")}</th>
              <th scope="col">{t("tableau.col_taux")}</th>
            </tr>
          </thead>
          <tbody>
            {composantes.map(([code, c]) => (
              <tr key={code}>
                <th scope="row">{code === "" ? t("tableau.sans_composante") : <span className="technique">{code}</span>}</th>
                <td><Montants montants={c.budget.total_par_devise} devises={tableau.devises} /></td>
                <td><Montants montants={c.engage.total_par_devise} devises={tableau.devises} /></td>
                <td><Montants montants={c.consomme.total_par_devise} devises={tableau.devises} /></td>
                <td>
                  <ul className="indicateur__lignes">
                    {Object.entries(c.taux_execution).sort(([a], [b]) => a.localeCompare(b)).map(([devise, taux]) => (
                      <li key={devise} className="chiffres" dir="ltr">
                        {taux === null ? "—" : enPourcentage(taux, langue, 1)} <span className="montant__devise">{devise}</span>
                      </li>
                    ))}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** Retire des filtres tout ce qui vaut « par défaut » : l'adresse ne porte que ce qui change. */
function nettoyer(f: Modifs): FiltresTableau {
  const propre: FiltresTableau = {};
  if (f.jour) propre.jour = f.jour;
  if (f.statut === "tous") propre.statut = "tous";
  if (f.devise) propre.devise = f.devise;
  if (f.projets && f.projets.length > 0) propre.projets = f.projets;
  return propre;
}

/** Les montants d'un projet pour un indicateur, et le lien qui descend vers ce qui les compose. */
function Cellule({
  montants,
  devises,
  projetId,
  projetCode,
  indicateur,
  filtres,
}: {
  montants: MontantsParDevise | undefined;
  devises: Record<string, number>;
  projetId: string;
  projetCode: string;
  indicateur: CodeIndicateur;
  filtres: FiltresTableau & { jour: string };
}) {
  const { t } = useTranslation();
  return (
    <>
      <Montants montants={montants} devises={devises} />
      {montants && Object.keys(montants).length > 0 && (
        <Link
          to="/tableau-de-bord/descente"
          search={{ projet: projetId, indicateur, jour: filtres.jour, ...(filtres.devise ? { devise: filtres.devise } : {}) }}
          className="cellule__detail"
        >
          {t("tableau.descente.voir_detail")}
          <span className="visuellement-cache">
            {" "}
            — {t(`tableau.i.${indicateur}`)} · {projetCode}
          </span>
        </Link>
      )}
    </>
  );
}
