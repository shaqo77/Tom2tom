import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useRef, useState } from "react";
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
import { libelleProjet } from "../projets/libelle";
import { changerStatut, lireAccord, lireAccords, reglerNumerotation } from "./api";
import type { AccordDetail, FormatNumero, StatutAccord } from "./types";
import "./accords.css";

const STATUTS: StatutAccord[] = ["brouillon", "actif", "suspendu", "clos", "annule"];
const VARIANTE: Record<StatutAccord, "attention" | "succes" | "accent" | "neutre" | "alerte"> = {
  brouillon: "attention",
  actif: "succes",
  suspendu: "accent",
  clos: "neutre",
  annule: "alerte",
};
const DATES = ["date_effet", "date_fin_eligibilite", "date_cloture", "date_limite_decaissement"] as const;
const SUFFIXE = /^[A-Z]{3}$/;

/** Le message du serveur tel quel (déjà dans la langue de la requête), sinon un message générique. */
function texteErreur(erreur: unknown, secours: string): string {
  return erreur instanceof ErreurApi && erreur.message ? erreur.message : secours;
}

/**
 * Les accords d'un projet : consulter (catégories en arbre, avenants, dates), changer le statut et régler
 * la numérotation des demandes de retrait. Le serveur reste l'autorité : les transitions de statut ne sont
 * pas dupliquées ici, il refuse celles qui sont interdites et son message est affiché.
 */
export function Accords() {
  const { t, i18n } = useTranslation();
  const { data: moi } = useMoi();
  const { projet: projetId, accord: accordId } = useSearch({ from: "/protege/accords" });
  const navigate = useNavigate();
  const projet = projetId ? projetParId(moi, projetId) : undefined;
  const aller = (search: { projet?: string; accord?: string }) => void navigate({ to: "/accords", search, replace: true });
  const liste = useQuery({ queryKey: ["accords", projetId], queryFn: () => lireAccords(projetId!), enabled: Boolean(projetId) });

  return (
    <>
      <div className="page__entete">
        <h1>{t("accords.titre")}</h1>
        <p>{t("accords.intro")}</p>
      </div>
      <Carte>
        <Selecteur
          etiquette={t("accords.projet")}
          valeur={projetId ?? ""}
          options={[
            { valeur: "", libelle: t("accords.choisir_projet") },
            ...(moi?.projets ?? []).map((p) => ({ valeur: p.id, libelle: `${p.code} · ${libelleProjet(p, i18n.language)}` })),
          ]}
          onChange={(v) => aller(v ? { projet: v } : {})}
        />
      </Carte>

      {projetId && (
        <Carte titre={t("accords.liste")}>
          {liste.isPending && <Chargement />}
          {liste.error && <Message variante="danger">{texteErreur(liste.error, t("accords.erreur_lecture"))}</Message>}
          {liste.data && liste.data.length === 0 && <p>{t("accords.vide")}</p>}
          {liste.data && liste.data.length > 0 && (
            <div className="accords__defilement">
              <table className="accords__tableau">
                <caption className="visuellement-cache">{t("accords.liste")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("accords.col_numero")}</th>
                    <th scope="col">{t("accords.col_bailleur")}</th>
                    <th scope="col">{t("accords.col_nature")}</th>
                    <th scope="col">{t("accords.col_statut")}</th>
                    <th scope="col">{t("accords.col_montant")}</th>
                    <th scope="col">{t("accords.col_action")}</th>
                  </tr>
                </thead>
                <tbody>
                  {liste.data.map((a) => (
                    <tr key={a.id} aria-current={a.id === accordId ? "true" : undefined}>
                      <th scope="row" className="technique">{a.numero}</th>
                      <td>{a.bailleur}</td>
                      <td>{t(`accords.nature.${a.nature}`)}</td>
                      <td>
                        <Pastille variante={VARIANTE[a.statut]}>{t(`accords.statut.${a.statut}`)}</Pastille>
                      </td>
                      <td className="accords__montant">
                        {a.montant_courant} {a.devise}
                      </td>
                      <td>
                        <Bouton variante="secondaire" aria-label={t("accords.ouvrir", { numero: a.numero })} onClick={() => aller({ projet: projetId, accord: a.id })}>
                          {t("accords.ouvrir", { numero: a.numero })}
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

      {projetId && accordId && <DetailAccord key={accordId} projetId={projetId} accordId={accordId} peutParametrer={peut(projet, "parametrer")} />}
    </>
  );
}

function DetailAccord({ projetId, accordId, peutParametrer }: { projetId: string; accordId: string; peutParametrer: boolean }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const cle = ["accord", projetId, accordId];
  const detail = useQuery({ queryKey: cle, queryFn: () => lireAccord(projetId, accordId) });
  const rafraichir = () => {
    void queryClient.invalidateQueries({ queryKey: cle });
    void queryClient.invalidateQueries({ queryKey: ["accords", projetId] });
  };
  if (detail.isPending) return <Chargement />;
  if (detail.error) return <Message variante="danger">{texteErreur(detail.error, t("accords.erreur_lecture"))}</Message>;
  const a = detail.data;
  const nom = (label: { fr?: string; en?: string }, code: string) => label[i18n.language === "en" ? "en" : "fr"] ?? label.fr ?? code;

  return (
    <Carte>
      <h2 className="carte__titre">{t("accords.detail", { numero: a.numero })}</h2>
      <p className="accords__ligne">
        <Pastille variante={VARIANTE[a.statut]}>{t(`accords.statut.${a.statut}`)}</Pastille>
        <span>{a.libelle}</span>
        <span className="technique">{a.bailleur}</span>
      </p>

      <h3>{t("accords.dates")}</h3>
      <dl className="accords__dates">
        {DATES.map((d) => (
          <div key={d}>
            <dt>{t(`accords.date.${d}`)}</dt>
            <dd>{a[d] ?? t("accords.non_renseigne")}</dd>
          </div>
        ))}
      </dl>

      <h3>{t("accords.categories")}</h3>
      {a.categories.length === 0 ? (
        <p>{t("accords.categories_vide")}</p>
      ) : (
        <div className="accords__defilement">
          <table className="accords__tableau">
            <caption className="visuellement-cache">{t("accords.categories")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("accords.col_code")}</th>
                <th scope="col">{t("accords.col_libelle")}</th>
                <th scope="col">{t("accords.col_plafond")}</th>
              </tr>
            </thead>
            <tbody>
              {a.categories.map((c) => (
                <tr key={c.id} className={c.parent ? "accords__enfant" : undefined}>
                  <th scope="row" className="technique">{c.code}</th>
                  <td>
                    {nom(c.label, c.code)}
                    {c.parent && <small className="accords__parent">{t("accords.sous", { parent: c.parent })}</small>}
                  </td>
                  <td className="accords__montant">{c.plafond ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>{t("accords.avenants")}</h3>
      {a.avenants.length === 0 ? (
        <p>{t("accords.avenants_vide")}</p>
      ) : (
        <div className="accords__defilement">
          <table className="accords__tableau">
            <caption className="visuellement-cache">{t("accords.avenants")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("accords.col_reference")}</th>
                <th scope="col">{t("accords.col_date")}</th>
                <th scope="col">{t("accords.col_revise")}</th>
                <th scope="col">{t("accords.col_motif")}</th>
              </tr>
            </thead>
            <tbody>
              {a.avenants.map((v) => (
                <tr key={v.id}>
                  <th scope="row" className="technique">{v.reference}</th>
                  <td>{v.date_avenant}</td>
                  <td className="accords__montant">{v.montant_revise}</td>
                  <td>{v.motif || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>{t("accords.numerotation")}</h3>
      <p>{a.format_numero_demande === "bad" ? t("accords.numerotation_bad", { suffixe: a.suffixe_agence }) : t("accords.numerotation_standard")}</p>

      {peutParametrer ? (
        <div className="accords__formulaires">
          <FormulaireStatut projetId={projetId} accord={a} surSucces={rafraichir} />
          <FormulaireNumerotation projetId={projetId} accord={a} surSucces={rafraichir} />
        </div>
      ) : (
        <p>{t("accords.lecture_seule")}</p>
      )}
    </Carte>
  );
}

function FormulaireStatut({ projetId, accord, surSucces }: { projetId: string; accord: AccordDetail; surSucces: () => void }) {
  const { t } = useTranslation();
  const autres = STATUTS.filter((s) => s !== accord.statut);
  const [choix, definirStatut] = useState<StatutAccord>(autres[0]!);
  const statut = autres.includes(choix) ? choix : autres[0]!; // après un changement, l'ancien choix peut être devenu l'état courant
  const [motif, definirMotif] = useState("");
  const [echec, definirEchec] = useState<string | null>(null);
  const [succes, definirSucces] = useState(false);
  const enVol = useRef(false);
  const ecriture = useMutation({
    mutationFn: () => changerStatut(projetId, accord.id, statut, motif.trim()),
    onSuccess: () => {
      definirSucces(true);
      surSucces();
    },
    onError: (e) => definirEchec(texteErreur(e, t("erreur.inconnue"))),
    onSettled: () => {
      enVol.current = false;
    },
  });
  function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    if (enVol.current) return;
    enVol.current = true;
    definirEchec(null);
    definirSucces(false);
    ecriture.mutate();
  }
  return (
    <form className="accords__formulaire" onSubmit={soumettre} noValidate aria-label={t("accords.statut_titre")}>
      <h4>{t("accords.statut_titre")}</h4>
      {succes && <Message variante="succes">{t("accords.statut_ok")}</Message>}
      {echec && <Message variante="danger">{echec}</Message>}
      <Selecteur etiquette={t("accords.nouveau_statut")} valeur={statut} options={autres.map((s) => ({ valeur: s, libelle: t(`accords.statut.${s}`) }))} onChange={(v) => definirStatut(v as StatutAccord)} />
      <Champ etiquette={t("accords.motif")} value={motif} onChange={(e) => definirMotif(e.target.value)} />
      <Bouton type="submit" chargement={ecriture.isPending}>
        {t("accords.changer_statut")}
      </Bouton>
    </form>
  );
}

function FormulaireNumerotation({ projetId, accord, surSucces }: { projetId: string; accord: AccordDetail; surSucces: () => void }) {
  const { t } = useTranslation();
  const [format, definirFormat] = useState<FormatNumero>(accord.format_numero_demande);
  const [suffixe, definirSuffixe] = useState(accord.suffixe_agence);
  const [erreurSuffixe, definirErreurSuffixe] = useState(false);
  const [echec, definirEchec] = useState<string | null>(null);
  const [succes, definirSucces] = useState(false);
  const enVol = useRef(false);
  const ecriture = useMutation({
    mutationFn: () => reglerNumerotation(projetId, accord.id, format, format === "bad" ? suffixe : ""),
    onSuccess: () => {
      definirSucces(true);
      surSucces();
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
    if (format === "bad" && !SUFFIXE.test(suffixe)) {
      definirErreurSuffixe(true);
      return;
    }
    definirErreurSuffixe(false);
    if (enVol.current) return;
    enVol.current = true;
    ecriture.mutate();
  }
  return (
    <form className="accords__formulaire" onSubmit={soumettre} noValidate aria-label={t("accords.numerotation")}>
      <h4>{t("accords.numerotation")}</h4>
      <p>{t("accords.numerotation_aide")}</p>
      {succes && <Message variante="succes">{t("accords.numerotation_ok")}</Message>}
      {echec && <Message variante="danger">{echec}</Message>}
      <Selecteur
        etiquette={t("accords.format")}
        valeur={format}
        options={(["standard", "bad"] as const).map((f) => ({ valeur: f, libelle: t(`accords.format.${f}`) }))}
        onChange={(v) => definirFormat(v as FormatNumero)}
      />
      {format === "bad" && (
        <Champ
          etiquette={t("accords.suffixe")}
          value={suffixe}
          autoComplete="off"
          onChange={(e) => definirSuffixe(e.target.value)}
          {...(erreurSuffixe ? { erreur: t("accords.suffixe_invalide") } : {})}
        />
      )}
      <Bouton type="submit" chargement={ecriture.isPending}>
        {t("accords.regler")}
      </Bouton>
    </form>
  );
}
