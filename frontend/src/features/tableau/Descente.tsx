import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { ErreurApi } from "../../shared/api/client";
import { additionner } from "../../shared/money/montant";
import { projetParId } from "../../shared/session/droits";
import { useMoi } from "../../shared/session/moi";
import { Bouton } from "../../shared/ui/Bouton";
import { Carte } from "../../shared/ui/Carte";
import { Chargement } from "../../shared/ui/Chargement";
import { Message } from "../../shared/ui/Message";
import { Montant } from "../../shared/ui/Montant";
import { libelleProjet } from "../projets/libelle";
import { lireDetail, lireEcriture, lireEcrituresDuDetail } from "./api";
import type { DetailDto } from "./types";
import "./tableau.css";

const DECIMALES_PAR_DEFAUT = 2;

/**
 * La descente : d'un chiffre du tableau de bord aux objets qui le composent, puis aux écritures, puis à
 * l'écriture elle-même (lignes et pièces). Chaque pas vient du serveur ; ce que l'écran additionne n'est
 * qu'un contrôle (la somme des détails doit retomber sur le chiffre du tableau), jamais une source.
 */
export function Descente() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { projet: projetId, indicateur, jour, devise, detail: detailId, ecriture: ecritureId } = useSearch({
    from: "/protege/tableau-de-bord/descente",
  });
  const { data: moi } = useMoi();
  const projet = projetParId(moi, projetId);
  const filtres = { jour, ...(devise ? { devise } : {}) };

  const details = useQuery({
    queryKey: ["descente", projetId, indicateur, filtres],
    queryFn: () => lireDetail(projetId, indicateur, filtres),
  });
  const ecritures = useQuery({
    queryKey: ["descente-ecritures", projetId, indicateur, detailId, filtres],
    queryFn: () => lireEcrituresDuDetail(projetId, indicateur, detailId as string, filtres),
    enabled: Boolean(detailId),
  });
  const ecriture = useQuery({
    queryKey: ["descente-ecriture", projetId, ecritureId],
    queryFn: () => lireEcriture(projetId, ecritureId as string),
    enabled: Boolean(ecritureId),
  });

  function aller(modifs: { detail?: string | undefined; ecriture?: string | undefined }) {
    void navigate({
      to: "/tableau-de-bord/descente",
      search: (precedent) => ({ ...precedent, ...modifs }),
    });
  }
  const decimales = (d: string) => (d in decimalesConnues ? decimalesConnues[d] : DECIMALES_PAR_DEFAUT) ?? DECIMALES_PAR_DEFAUT;
  const decimalesConnues: Record<string, number> = { DJF: 0 };
  const erreur = (e: unknown) => (e instanceof ErreurApi && e.statut < 500 ? e.message : t("erreur.inconnue"));

  const totaux: Record<string, string> = {};
  for (const d of details.data ?? []) totaux[d.devise] = additionner(totaux[d.devise] ?? "0", d.montant);

  return (
    <>
      <nav aria-label={t("tableau.descente.fil")} className="fil">
        <Link to="/tableau-de-bord" search={{ jour }}>
          {t("tableau.titre")}
        </Link>
        {" › "}
        <span aria-current="page">{t("tableau.descente.titre")}</span>
      </nav>
      <div className="page__entete">
        <h1>
          {t(`tableau.i.${indicateur}`)}
          {" — "}
          <span className="technique">{projet?.code ?? projetId}</span>
          {projet && <> · {libelleProjet(projet, i18n.language)}</>}
        </h1>
        <p className="page__sous-titre">{t("tableau.descente.sous_titre", { jour })}</p>
      </div>

      <Carte titre={t("tableau.descente.composition")}>
        {details.isPending && <Chargement />}
        {details.error && <Message variante="danger">{erreur(details.error)}</Message>}
        {details.data && details.data.length === 0 && <p>{t("tableau.descente.aucun_objet")}</p>}
        {details.data && details.data.length > 0 && (
          <div className="table-defilante">
            <table className="table">
              <caption className="visuellement-cache">{t("tableau.descente.composition")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("tableau.descente.col_objet")}</th>
                  <th scope="col">{t("tableau.descente.col_type")}</th>
                  <th scope="col">{t("tableau.descente.col_montant")}</th>
                  <th scope="col">{t("tableau.descente.col_ecritures")}</th>
                </tr>
              </thead>
              <tbody>
                {details.data.map((d) => (
                  <LigneDetail key={d.id} d={d} choisi={d.id === detailId} decimales={decimales(d.devise)} onOuvrir={() => aller({ detail: d.id, ecriture: undefined })} />
                ))}
              </tbody>
              <tfoot>
                {Object.entries(totaux)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([d, total]) => (
                    <tr key={d}>
                      <th scope="row" colSpan={2}>
                        {t("tableau.descente.total")}
                      </th>
                      <td colSpan={2}>
                        <Montant valeur={total} decimales={decimales(d)} devise={d} />
                      </td>
                    </tr>
                  ))}
              </tfoot>
            </table>
          </div>
        )}
      </Carte>

      {detailId && (
        <Carte titre={t("tableau.descente.ecritures")}>
          {ecritures.isPending && <Chargement />}
          {ecritures.error && <Message variante="danger">{erreur(ecritures.error)}</Message>}
          {ecritures.data && ecritures.data.ecritures.length === 0 && <p>{t("tableau.descente.aucune_ecriture")}</p>}
          {ecritures.data && ecritures.data.ecritures.length > 0 && (
            <div className="table-defilante">
              <table className="table">
                <caption className="visuellement-cache">{t("tableau.descente.ecritures")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("tableau.descente.col_numero")}</th>
                    <th scope="col">{t("tableau.descente.col_date")}</th>
                    <th scope="col">{t("tableau.descente.col_libelle")}</th>
                    <th scope="col">{t("tableau.descente.col_montant")}</th>
                    <th scope="col">
                      <span className="visuellement-cache">{t("tableau.descente.ouvrir")}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {ecritures.data.ecritures.map((e) => (
                    <tr key={e.ecriture_id} aria-current={e.ecriture_id === ecritureId ? "true" : undefined}>
                      <th scope="row" className="technique">
                        {e.numero || "—"}
                      </th>
                      <td>{e.date}</td>
                      <td>{e.libelle}</td>
                      <td>
                        <Montant valeur={e.montant} decimales={decimales(ecritures.data.detail.devise)} devise={ecritures.data.detail.devise} />
                      </td>
                      <td>
                        <Bouton variante="secondaire" onClick={() => aller({ ecriture: e.ecriture_id })}>
                          {t("tableau.descente.ouvrir_ecriture", { numero: e.numero || e.libelle })}
                        </Bouton>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Carte>
      )}

      {ecritureId && (
        <Carte titre={t("tableau.descente.ecriture")}>
          {ecriture.isPending && <Chargement />}
          {ecriture.error && <Message variante="danger">{erreur(ecriture.error)}</Message>}
          {ecriture.data && (
            <>
              <p>
                <strong className="technique">{ecriture.data.numero}</strong> · {ecriture.data.journal} · {ecriture.data.date} · {ecriture.data.libelle}
              </p>
              <div className="table-defilante">
                <table className="table">
                  <caption className="visuellement-cache">{t("tableau.descente.lignes")}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{t("tableau.descente.col_compte")}</th>
                      <th scope="col">{t("tableau.descente.col_montant")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ecriture.data.lignes.map((l) => (
                      <tr key={l.id}>
                        <th scope="row" className="technique">
                          {l.compte}
                        </th>
                        <td>
                          <Montant valeur={l.montant} decimales={decimales(ecritures.data?.detail.devise ?? "")} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <h3>{t("tableau.descente.pieces")}</h3>
              {ecriture.data.pieces.length === 0 ? (
                <p>{t("tableau.descente.aucune_piece")}</p>
              ) : (
                <ul>
                  {ecriture.data.pieces.map((p) => (
                    <li key={p.id}>
                      <span className="technique">{p.nom}</span> · {t(`tableau.descente.type_piece.${p.type}`, { defaultValue: p.type })} ·{" "}
                      {t("tableau.descente.taille", { octets: p.taille })}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </Carte>
      )}
    </>
  );
}

function LigneDetail({
  d,
  choisi,
  decimales,
  onOuvrir,
}: {
  d: DetailDto;
  choisi: boolean;
  decimales: number;
  onOuvrir: () => void;
}) {
  const { t } = useTranslation();
  return (
    <tr aria-current={choisi ? "true" : undefined}>
      <th scope="row">{d.libelle}</th>
      <td>{t(`tableau.descente.type.${d.type}`, { defaultValue: d.type })}</td>
      <td>
        <Montant valeur={d.montant} decimales={decimales} devise={d.devise} />
      </td>
      <td>
        {d.a_une_ecriture ? (
          <Bouton variante="secondaire" onClick={onOuvrir}>
            {t("tableau.descente.voir_ecritures")}
            <span className="visuellement-cache"> — {d.libelle}</span>
          </Bouton>
        ) : (
          <span className="technique-texte">{t("tableau.descente.sans_ecriture")}</span>
        )}
      </td>
    </tr>
  );
}
