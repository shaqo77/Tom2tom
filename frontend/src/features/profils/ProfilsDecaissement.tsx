import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ErreurApi } from "../../shared/api/client";
import { peut, projetParId } from "../../shared/session/droits";
import { useMoi } from "../../shared/session/moi";
import type { ProjetAccessible } from "../../shared/session/types";
import { Bouton } from "../../shared/ui/Bouton";
import { Carte } from "../../shared/ui/Carte";
import { Champ } from "../../shared/ui/Champ";
import { Chargement } from "../../shared/ui/Chargement";
import { Message } from "../../shared/ui/Message";
import { Pastille } from "../../shared/ui/Pastille";
import { Selecteur } from "../../shared/ui/Selecteur";
import { libelleProjet } from "../projets/libelle";
import { activerProfil, lireAccords, lireProfil, lireProfils, rejeterProfil, supprimerBrouillon, validerProfil } from "./api";
import { FormulaireProfil } from "./FormulaireProfil";
import type { AppelDecision, ProfilDetail, StatutProfil } from "./types";
import "./profils.css";

const VARIANTE: Record<StatutProfil, "neutre" | "succes" | "accent" | "alerte" | "attention"> = {
  draft: "attention",
  validated: "accent",
  active: "succes",
  superseded: "neutre",
  rejected: "alerte",
};
const JALONS = ["effectiveness_date", "eligibility_date", "closing_date", "disbursement_deadline"] as const;

/** Le message du serveur tel quel (déjà dans la langue de la requête), sinon un message générique. */
function texteErreur(erreur: unknown, secours: string): string {
  return erreur instanceof ErreurApi && erreur.message ? erreur.message : secours;
}

/**
 * Les profils de décaissement d'un accord : consulter ses versions et décider d'un brouillon
 * (valider, activer, rejeter, supprimer). Le serveur reste l'autorité : un bouton désactivé n'est
 * qu'une commodité, et son refus est toujours affiché.
 */
export function ProfilsDecaissement() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const { data: moi } = useMoi();
  const { projet: projetId, accord: accordId, profil: profilId, mode } = useSearch({ from: "/protege/profils-decaissement" });
  const navigate = useNavigate();
  const [information, definirInformation] = useState<string | null>(null);
  const projet = projetId ? projetParId(moi, projetId) : undefined;

  const aller = (search: { projet?: string; accord?: string; profil?: string; mode?: "creation" | "edition" }) =>
    void navigate({ to: "/profils-decaissement", search, replace: true });

  const accords = useQuery({ queryKey: ["accords", projetId], queryFn: () => lireAccords(projetId!), enabled: Boolean(projetId) });
  const profils = useQuery({
    queryKey: ["profils-decaissement", projetId, accordId],
    queryFn: () => lireProfils(projetId!, accordId!),
    enabled: Boolean(projetId && accordId),
  });

  return (
    <>
      <div className="page__entete">
        <h1>{t("profils.titre")}</h1>
        <p>{t("profils.intro")}</p>
      </div>
      <Carte>
        <div className="profils__choix">
          <Selecteur
            etiquette={t("profils.projet")}
            valeur={projetId ?? ""}
            options={[
              { valeur: "", libelle: t("profils.choisir_projet") },
              ...(moi?.projets ?? []).map((p) => ({ valeur: p.id, libelle: `${p.code} · ${libelleProjet(p, i18n.language)}` })),
            ]}
            onChange={(v) => aller(v ? { projet: v } : {})}
          />
          {projetId && accords.data && accords.data.length > 0 && (
            <Selecteur
              etiquette={t("profils.accord")}
              valeur={accordId ?? ""}
              options={[
                { valeur: "", libelle: t("profils.choisir_accord") },
                ...accords.data.map((a) => ({ valeur: a.id, libelle: `${a.numero} · ${a.bailleur}` })),
              ]}
              onChange={(v) => aller(v ? { projet: projetId, accord: v } : { projet: projetId })}
            />
          )}
        </div>
        {projetId && accords.isPending && <Chargement />}
        {projetId && accords.error && <Message variante="danger">{texteErreur(accords.error, t("profils.erreur_lecture"))}</Message>}
        {projetId && accords.data?.length === 0 && <p>{t("profils.aucun_accord")}</p>}
      </Carte>

      {information && <Message variante="succes">{information}</Message>}

      {projetId && accordId && peut(projet, "parametrer") && mode !== "creation" && (
        <div className="profils__actions">
          <Bouton onClick={() => { definirInformation(null); aller({ projet: projetId, accord: accordId, mode: "creation" }); }}>{t("profils.form.nouveau")}</Bouton>
        </div>
      )}

      {projetId && accordId && (
        <Carte titre={t("profils.liste")}>
          {profils.isPending && <Chargement />}
          {profils.error && <Message variante="danger">{texteErreur(profils.error, t("profils.erreur_lecture"))}</Message>}
          {profils.data && profils.data.length === 0 && <p>{t("profils.liste_vide")}</p>}
          {profils.data && profils.data.length > 0 && (
            <div className="profils__defilement">
              <table className="profils__tableau">
                <caption className="visuellement-cache">{t("profils.liste")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("profils.col_version")}</th>
                    <th scope="col">{t("profils.col_etat")}</th>
                    <th scope="col">{t("profils.col_effet")}</th>
                    <th scope="col">{t("profils.col_regime")}</th>
                    <th scope="col">{t("profils.col_action")}</th>
                  </tr>
                </thead>
                <tbody>
                  {profils.data.map((p) => (
                    <tr key={p.id} aria-current={p.id === profilId ? "true" : undefined}>
                      <td>{p.version}</td>
                      <td>
                        <Pastille variante={VARIANTE[p.status]}>{t(`profils.etat.${p.status}`)}</Pastille>
                      </td>
                      <td>{p.valid_from}</td>
                      <td>{t(`profils.regime.${p.regime}`)}</td>
                      <td>
                        <Bouton
                          variante="secondaire"
                          aria-label={t("profils.ouvrir", { version: p.version })}
                          onClick={() => {
                            definirInformation(null);
                            aller({ projet: projetId, accord: accordId, profil: p.id });
                          }}
                        >
                          {t("profils.ouvrir", { version: p.version })}
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

      {projetId && accordId && mode === "creation" && (
        <FormulaireProfil
          projetId={projetId}
          accordId={accordId}
          surTermine={(p) => {
            definirInformation(t("profils.form.cree_ok"));
            void queryClient.invalidateQueries({ queryKey: ["profils-decaissement", projetId, accordId] });
            aller({ projet: projetId, accord: accordId, profil: p.id });
          }}
          surAnnulation={() => aller({ projet: projetId, accord: accordId })}
        />
      )}
      {projetId && accordId && profilId && mode === "edition" && (
        <EditionProfil
          key={profilId}
          projetId={projetId}
          accordId={accordId}
          profilId={profilId}
          surTermine={(p) => {
            definirInformation(t("profils.form.modifie_ok"));
            queryClient.setQueryData(["profil-decaissement", projetId, accordId, p.id], p);
            void queryClient.invalidateQueries({ queryKey: ["profils-decaissement", projetId, accordId] });
            aller({ projet: projetId, accord: accordId, profil: p.id });
          }}
          surAnnulation={() => aller({ projet: projetId, accord: accordId, profil: profilId })}
        />
      )}
      {projetId && accordId && profilId && !mode && (
        <DetailProfil
          key={profilId}
          projetId={projetId}
          accordId={accordId}
          profilId={profilId}
          projet={projet}
          surSucces={definirInformation}
          surSuppression={() => aller({ projet: projetId, accord: accordId })}
          surModification={() => aller({ projet: projetId, accord: accordId, profil: profilId, mode: "edition" })}
        />
      )}
    </>
  );
}

function DetailProfil({
  projetId,
  accordId,
  profilId,
  projet,
  surSucces,
  surSuppression,
  surModification,
}: {
  projetId: string;
  accordId: string;
  profilId: string;
  projet: ProjetAccessible | undefined;
  surSucces: (texte: string | null) => void;
  surSuppression: () => void;
  surModification: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const cle = ["profil-decaissement", projetId, accordId, profilId];
  const detail = useQuery({ queryKey: cle, queryFn: () => lireProfil(projetId, accordId, profilId) });
  const [erreur, definirErreur] = useState<string | null>(null);
  const [mode, definirMode] = useState<"repos" | "rejet" | "suppression">("repos");
  const [motif, definirMotif] = useState("");
  const [motifManquant, definirMotifManquant] = useState(false);
  const enVol = useRef(false);

  const rafraichirListe = () => queryClient.invalidateQueries({ queryKey: ["profils-decaissement", projetId, accordId] });
  const decision = useMutation({
    mutationFn: (appel: AppelDecision) => appel(),
    onSuccess: (profil) => {
      queryClient.setQueryData(cle, profil);
      void rafraichirListe();
      definirMode("repos");
    },
    onError: (e) => definirErreur(texteErreur(e, t("erreur.inconnue"))),
    onSettled: () => {
      enVol.current = false;
    },
  });
  const suppression = useMutation({
    mutationFn: () => supprimerBrouillon(projetId, accordId, profilId),
    onSuccess: () => {
      void rafraichirListe();
      surSucces(t("profils.supprime_ok"));
      surSuppression();
    },
    onError: (e) => definirErreur(texteErreur(e, t("erreur.inconnue"))),
    onSettled: () => {
      enVol.current = false;
    },
  });
  const occupe = decision.isPending || suppression.isPending;

  function decider(appel: AppelDecision, succes: string) {
    if (enVol.current) return; // un double clic n'envoie qu'une demande
    enVol.current = true;
    definirErreur(null);
    decision.mutate(appel, { onSuccess: () => surSucces(succes) });
  }

  if (detail.isPending) return <Chargement />;
  if (detail.error) return <Message variante="danger">{texteErreur(detail.error, t("profils.erreur_lecture"))}</Message>;
  const p = detail.data;
  const peutValider = peut(projet, "valider");
  const peutParametrer = peut(projet, "parametrer");
  const proposeActions =
    (p.status === "draft" && (peutValider || peutParametrer)) || (p.status === "validated" && (peutValider || peutParametrer));

  function rejeter(evenement: FormEvent) {
    evenement.preventDefault();
    if (!motif.trim()) {
      definirMotifManquant(true);
      return;
    }
    definirMotifManquant(false);
    decider(() => rejeterProfil(projetId, accordId, profilId, motif.trim()), t("profils.rejete_ok"));
  }

  return (
    <Carte>
      <h2 className="carte__titre">{t("profils.detail", { version: p.version, accord: p.accord })}</h2>
      <p className="profils__ligne">
        <Pastille variante={VARIANTE[p.status]}>{t(`profils.etat.${p.status}`)}</Pastille>
        <span>{t(`profils.regime.${p.regime}`)}</span>
      </p>
      {p.status === "rejected" && p.rejection_reason && <Message variante="attention">{t("profils.rejet_motif_affiche", { motif: p.rejection_reason })}</Message>}
      {erreur && <Message variante="danger">{erreur}</Message>}

      <h3>{t("profils.jalons")}</h3>
      <dl className="profils__jalons">
        {JALONS.map((j) => (
          <div key={j}>
            <dt>{t(`profils.jalon.${j}`)}</dt>
            <dd>{p[j] ?? t("profils.non_renseigne")}</dd>
          </div>
        ))}
      </dl>

      <h3>{t("profils.methodes")}</h3>
      {p.methodes.length === 0 ? (
        <p>{t("profils.methodes_vide")}</p>
      ) : (
        <ul className="profils__liste">
          {p.methodes.map((m) => (
            <li key={m.method}>
              <strong>{t(`profils.methode.${m.method}`)}</strong>{" "}
              <Pastille variante={m.is_enabled ? "succes" : "neutre"}>{t(m.is_enabled ? "profils.methode_active" : "profils.methode_inactive")}</Pastille>{" "}
              <span>{m.supporting_docs.length ? t("profils.pieces", { pieces: m.supporting_docs.join(", ") }) : t("profils.aucune_piece")}</span>
            </li>
          ))}
        </ul>
      )}

      <h3>{t("profils.regles")}</h3>
      {p.regles.length === 0 ? (
        <p>{t("profils.regles_vide")}</p>
      ) : (
        <div className="profils__defilement">
          <table className="profils__tableau">
            <caption className="visuellement-cache">{t("profils.regles")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("profils.col_categorie")}</th>
                <th scope="col">{t("profils.col_allocation")}</th>
                <th scope="col">{t("profils.col_taux")}</th>
                <th scope="col">{t("profils.col_assiette")}</th>
                <th scope="col">{t("profils.col_eligibilite")}</th>
              </tr>
            </thead>
            <tbody>
              {p.regles.map((r) => (
                <tr key={r.category}>
                  <th scope="row" className="technique">{r.category}</th>
                  <td className="profils__montant">{r.allocation}</td>
                  <td className="profils__montant">{r.funding_rate}</td>
                  <td>{t(`profils.assiette.${r.tax_basis}`)}</td>
                  <td>
                    {[r.eligibility_from, r.eligibility_to].filter(Boolean).join(" → ") || "—"}
                    {r.fin_propre_a_la_categorie && <Pastille variante="attention">{t("profils.fin_propre")}</Pastille>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>{t("profils.comptes")}</h3>
      {p.comptes.length === 0 ? (
        <p>{t("profils.comptes_vide")}</p>
      ) : (
        <div className="profils__defilement">
          <table className="profils__tableau">
            <caption className="visuellement-cache">{t("profils.comptes")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("profils.col_compte")}</th>
                <th scope="col">{t("profils.col_plafond")}</th>
                <th scope="col">{t("profils.col_seuil")}</th>
              </tr>
            </thead>
            <tbody>
              {p.comptes.map((c) => (
                <tr key={c.compte}>
                  <th scope="row" className="technique">{c.compte}</th>
                  <td>
                    {t(`profils.plafond.${c.ceiling_kind}`)}
                    {c.ceiling_amount && <span className="profils__montant"> {c.ceiling_amount} {c.devise}</span>}
                  </td>
                  <td className="profils__montant">{c.replenishment_threshold_pct ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {p.completude && (
        <section aria-labelledby="completude">
          <h3 id="completude">{t("profils.completude")}</h3>
          <Message variante={p.completude.complet ? "succes" : "attention"}>{t(p.completude.complet ? "profils.complet" : "profils.incomplet")}</Message>
          {p.completude.bloquantes.length > 0 && (
            <>
              <h4>{t("profils.bloquantes")}</h4>
              <ul className="profils__liste profils__liste--bloquante">
                {p.completude.bloquantes.map((a) => (
                  <li key={a.code}>{a.message}</li>
                ))}
              </ul>
            </>
          )}
          {p.completude.avertissements.length > 0 && (
            <>
              <h4>{t("profils.avertissements")}</h4>
              <ul className="profils__liste profils__liste--avertissement">
                {p.completude.avertissements.map((a) => (
                  <li key={a.code}>{a.message}</li>
                ))}
              </ul>
            </>
          )}
        </section>
      )}

      {!proposeActions && (p.status === "draft" || p.status === "validated") && <p>{t("profils.lecture_seule")}</p>}
      {proposeActions && mode === "repos" && (
        <div className="profils__actions">
          {p.status === "draft" && peutValider && (
            <Bouton chargement={occupe} disabled={!p.completude?.complet} onClick={() => decider(() => validerProfil(projetId, accordId, profilId), t("profils.valide_ok"))}>
              {t("profils.valider")}
            </Bouton>
          )}
          {p.status === "draft" && peutParametrer && (
            <Bouton variante="secondaire" disabled={occupe} onClick={surModification}>
              {t("profils.form.modifier")}
            </Bouton>
          )}
          {p.status === "draft" && peutParametrer && (
            <Bouton variante="danger" disabled={occupe} onClick={() => definirMode("suppression")}>
              {t("profils.supprimer")}
            </Bouton>
          )}
          {p.status === "validated" && peutParametrer && (
            <Bouton chargement={occupe} onClick={() => decider(() => activerProfil(projetId, accordId, profilId), t("profils.active_ok"))}>
              {t("profils.activer")}
            </Bouton>
          )}
          {p.status === "validated" && peutValider && (
            <Bouton variante="secondaire" disabled={occupe} onClick={() => definirMode("rejet")}>
              {t("profils.rejeter")}
            </Bouton>
          )}
        </div>
      )}
      {mode === "suppression" && (
        <div className="profils__confirmation" role="group" aria-label={t("profils.supprimer")}>
          <p>{t("profils.supprimer_confirmer")}</p>
          <Bouton
            variante="danger"
            chargement={suppression.isPending}
            onClick={() => {
              if (enVol.current) return;
              enVol.current = true;
              definirErreur(null);
              suppression.mutate();
            }}
          >
            {t("profils.supprimer_oui")}
          </Bouton>
          <Bouton variante="secondaire" disabled={occupe} onClick={() => definirMode("repos")}>
            {t("profils.annuler")}
          </Bouton>
        </div>
      )}
      {mode === "rejet" && (
        <form className="profils__confirmation" onSubmit={rejeter} noValidate>
          <Champ
            etiquette={t("profils.motif")}
            value={motif}
            onChange={(e) => definirMotif(e.target.value)}
            {...(motifManquant ? { erreur: t("profils.motif_requis") } : {})}
          />
          <Bouton type="submit" variante="danger" chargement={occupe}>
            {t("profils.rejeter_confirmer")}
          </Bouton>
          <Bouton variante="secondaire" disabled={occupe} onClick={() => definirMode("repos")}>
            {t("profils.annuler")}
          </Bouton>
        </form>
      )}
    </Carte>
  );
}

/** L'édition d'un brouillon : on lit d'abord le profil, puis le formulaire part de ses valeurs. */
function EditionProfil({ projetId, accordId, profilId, surTermine, surAnnulation }: { projetId: string; accordId: string; profilId: string; surTermine: (p: ProfilDetail) => void; surAnnulation: () => void }) {
  const { t } = useTranslation();
  const detail = useQuery({ queryKey: ["profil-decaissement", projetId, accordId, profilId], queryFn: () => lireProfil(projetId, accordId, profilId) });
  if (detail.isPending) return <Chargement />;
  if (detail.error) return <Message variante="danger">{texteErreur(detail.error, t("profils.erreur_lecture"))}</Message>;
  if (detail.data.status !== "draft") return <Message variante="attention">{t("profils.form.seulement_brouillon")}</Message>;
  return <FormulaireProfil projetId={projetId} accordId={accordId} profil={detail.data} surTermine={surTermine} surAnnulation={surAnnulation} />;
}
