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
import { aujourdhui } from "../tableau/api";
import { libelleProjet } from "../projets/libelle";
import { FormulaireJustification } from "./FormulaireJustification";
import { annulerJustification, lireComptes, lireJustifications, lireSituation, publierRapport } from "./api";
import { NOTE_MAX } from "./types";
import type { JustificationBanque, RapportPublie } from "./types";
import "./compte-special.css";

function texteErreur(erreur: unknown, secours: string): string {
  return erreur instanceof ErreurApi && erreur.message ? erreur.message : secours;
}

/**
 * Le compte spécial d'un projet (annexe 9 du manuel BAD) : sa situation à une date, les justifications soumises à la
 * Banque (annulables, avec motif) et la publication du rapport de réconciliation scellé. Tous les montants arrivent
 * et restent des chaînes ; l'écart n'est jamais recalculé ici : c'est celui du serveur.
 */
export function CompteSpecial() {
  const { t, i18n } = useTranslation();
  const { data: moi } = useMoi();
  const { projet: projetId, compte: compteId, date: dateDemandee } = useSearch({ from: "/protege/compte-special" });
  const navigate = useNavigate();
  const projet = projetId ? projetParId(moi, projetId) : undefined;
  const date = dateDemandee ?? aujourdhui();
  const [demande, definirDemande] = useState("");
  const aller = (search: { projet?: string; compte?: string; date?: string }) => void navigate({ to: "/compte-special", search, replace: true });
  const comptes = useQuery({ queryKey: ["comptes-bancaires", projetId], queryFn: () => lireComptes(projetId!), enabled: Boolean(projetId) });
  const speciaux = (comptes.data ?? []).filter((c) => c.type === "special");

  return (
    <>
      <div className="page__entete">
        <h1>{t("special.titre")}</h1>
        <p>{t("special.intro")}</p>
      </div>
      <Carte>
        <div className="special__choix">
          <Selecteur
            etiquette={t("special.projet")}
            valeur={projetId ?? ""}
            options={[
              { valeur: "", libelle: t("special.choisir_projet") },
              ...(moi?.projets ?? []).map((p) => ({ valeur: p.id, libelle: `${p.code} · ${libelleProjet(p, i18n.language)}` })),
            ]}
            onChange={(v) => aller(v ? { projet: v } : {})}
          />
          {projetId && comptes.data && (
            <Selecteur
              etiquette={t("special.compte")}
              valeur={compteId ?? ""}
              options={[
                { valeur: "", libelle: t("special.choisir_compte") },
                ...speciaux.map((c) => ({ valeur: c.id, libelle: `${c.code} · ${c.devise} · ${c.numero_masque}` })),
              ]}
              onChange={(v) => aller(v ? { projet: projetId, compte: v, date } : { projet: projetId })}
            />
          )}
        </div>
        {projetId && comptes.isPending && <Chargement />}
        {projetId && comptes.error && <Message variante="danger">{texteErreur(comptes.error, t("special.erreur_lecture"))}</Message>}
        {projetId && comptes.data && speciaux.length === 0 && <p>{t("special.aucun_compte")}</p>}
      </Carte>

      {projetId && compteId && (
        <>
          <Situation
            compteId={compteId}
            date={date}
            demande={demande}
            surDate={(d) => aller({ projet: projetId, compte: compteId, ...(d ? { date: d } : {}) })}
            surDemande={definirDemande}
          />
          <Justifications projetId={projetId} compteId={compteId} peutSaisir={peut(projet, "saisir")} />
          <Publication compteId={compteId} date={date} demande={demande} peutPublier={peut(projet, "publier")} />
        </>
      )}
    </>
  );
}

function Situation({ compteId, date, demande, surDate, surDemande }: { compteId: string; date: string; demande: string; surDate: (d: string) => void; surDemande: (d: string) => void }) {
  const { t } = useTranslation();
  // La saisie de la date est locale : un champ date incomplet rend « » ; seule une date complète change la situation.
  const [saisie, definirSaisie] = useState(date);
  const situation = useQuery({ queryKey: ["situation-special", compteId, date, demande], queryFn: () => lireSituation(compteId, date, demande.trim() || undefined) });
  const s = situation.data;
  return (
    <Carte titre={t("special.situation")}>
      <div className="special__choix">
        <Champ
          etiquette={t("special.date")}
          type="date"
          value={saisie}
          onChange={(e) => {
            definirSaisie(e.target.value);
            if (/^\d{4}-\d{2}-\d{2}$/.test(e.target.value)) surDate(e.target.value);
          }}
        />
        <Champ etiquette={t("special.demande")} value={demande} onChange={(e) => surDemande(e.target.value)} autoComplete="off" />
      </div>
      {situation.isPending && <Chargement />}
      {situation.error && <Message variante="danger">{texteErreur(situation.error, t("special.erreur_lecture"))}</Message>}
      {s && (
        <>
          {!s.complet && (
            <Message variante="attention">
              {t("special.incomplete")}
              <ul className="special__liste">
                {s.manques.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            </Message>
          )}
          <h3>{t("special.avances")}</h3>
          {s.avances.length === 0 ? (
            <p>{t("special.avances_vide")}</p>
          ) : (
            <table className="special__tableau">
              <caption className="visuellement-cache">{t("special.avances")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("special.col_demande")}</th>
                  <th scope="col">{t("special.col_montant", { devise: s.devise })}</th>
                </tr>
              </thead>
              <tbody>
                {s.avances.map((a) => (
                  <tr key={a.demande}>
                    <th scope="row" className="technique">{a.demande}</th>
                    <td className="special__montant">{a.montant}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <h3>{t("special.justifications_soumises")}</h3>
          {s.justifications.length === 0 ? (
            <p>{t("special.justifications_vide")}</p>
          ) : (
            <table className="special__tableau">
              <caption className="visuellement-cache">{t("special.justifications_soumises")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("special.col_demande")}</th>
                  <th scope="col">{t("special.col_montant", { devise: s.devise })}</th>
                  <th scope="col">{t("special.col_date")}</th>
                  <th scope="col">{t("special.col_etat")}</th>
                </tr>
              </thead>
              <tbody>
                {s.justifications.map((j) => (
                  <tr key={`${j.demande}-${j.date_soumission}`}>
                    <th scope="row" className="technique">{j.demande}</th>
                    <td className="special__montant">{j.montant}</td>
                    <td>{j.date_soumission}</td>
                    <td>
                      {j.en_cours && <Pastille variante="accent">{t("special.en_cours")}</Pastille>}
                      {!j.comptee && <Pastille variante="neutre">{t("special.non_comptee")}</Pastille>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="special__totaux">
            <p>{t("special.total_avances", { montant: s.total_avances, devise: s.devise })}</p>
            {s.solde_cloture !== null && <p>{t("special.solde_cloture", { montant: s.solde_cloture, devise: s.devise })}</p>}
            <p>{t("special.justifie_cette_demande", { montant: s.justifie_cette_demande, devise: s.devise })}</p>
            <p>{t("special.justifie_precedemment", { montant: s.justifie_precedemment, devise: s.devise })}</p>
            {s.total_justifie !== null && <p>{t("special.total_justifie", { montant: s.total_justifie, devise: s.devise })}</p>}
            {s.ecart !== null && (
              <p>
                <strong>{t("special.ecart", { montant: s.ecart, devise: s.devise })}</strong>
              </p>
            )}
          </div>
        </>
      )}
    </Carte>
  );
}

function Justifications({ projetId, compteId, peutSaisir }: { projetId: string; compteId: string; peutSaisir: boolean }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const liste = useQuery({ queryKey: ["justifications-banque", compteId], queryFn: () => lireJustifications(compteId) });
  const [annulation, definirAnnulation] = useState<JustificationBanque | null>(null);
  const [motif, definirMotif] = useState("");
  const [motifManquant, definirMotifManquant] = useState(false);
  const [echec, definirEchec] = useState<string | null>(null);
  const [succes, definirSucces] = useState(false);
  const enVol = useRef(false);
  const ecriture = useMutation({
    mutationFn: (j: JustificationBanque) => annulerJustification(j.id, motif.trim()),
    onSuccess: () => {
      definirSucces(true);
      definirAnnulation(null);
      definirMotif("");
      void queryClient.invalidateQueries({ queryKey: ["justifications-banque", compteId] });
      void queryClient.invalidateQueries({ queryKey: ["situation-special", compteId] });
    },
    onError: (e) => definirEchec(texteErreur(e, t("erreur.inconnue"))),
    onSettled: () => {
      enVol.current = false;
    },
  });
  function confirmer(evenement: FormEvent) {
    evenement.preventDefault();
    definirEchec(null);
    definirSucces(false);
    if (!motif.trim()) {
      definirMotifManquant(true);
      return;
    }
    definirMotifManquant(false);
    if (enVol.current || !annulation) return;
    enVol.current = true;
    ecriture.mutate(annulation);
  }
  return (
    <Carte titre={t("special.justifications_banque")}>
      {succes && <Message variante="succes">{t("special.annulee_ok")}</Message>}
      {echec && <Message variante="danger">{echec}</Message>}
      {liste.isPending && <Chargement />}
      {liste.error && <Message variante="danger">{texteErreur(liste.error, t("special.erreur_lecture"))}</Message>}
      {liste.data && liste.data.length === 0 && <p>{t("special.justifications_banque_vide")}</p>}
      {liste.data && liste.data.length > 0 && (
        <table className="special__tableau">
          <caption className="visuellement-cache">{t("special.justifications_banque")}</caption>
          <thead>
            <tr>
              <th scope="col">{t("special.col_demande")}</th>
              <th scope="col">{t("special.col_montant_court")}</th>
              <th scope="col">{t("special.col_date")}</th>
              <th scope="col">{t("special.col_action")}</th>
            </tr>
          </thead>
          <tbody>
            {liste.data.map((j) => (
              <tr key={j.id}>
                <th scope="row" className="technique">{j.demande}</th>
                <td className="special__montant">{j.montant}</td>
                <td>{j.date_soumission}</td>
                <td>
                  {j.annulee ? (
                    <Pastille variante="alerte">{t("special.annulee_motif", { motif: j.motif_annulation })}</Pastille>
                  ) : (
                    peutSaisir && (
                      <Bouton variante="secondaire" aria-label={t("special.annuler", { demande: j.demande })} onClick={() => { definirAnnulation(j); definirEchec(null); definirSucces(false); }}>
                        {t("special.annuler_court")}
                      </Bouton>
                    )
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {peutSaisir && <FormulaireJustification projetId={projetId} compteId={compteId} />}
      {annulation && (
        <form className="special__formulaire" onSubmit={confirmer} noValidate aria-label={t("special.annuler", { demande: annulation.demande })}>
          <Champ etiquette={t("special.motif_annulation")} value={motif} onChange={(e) => definirMotif(e.target.value)} {...(motifManquant ? { erreur: t("special.motif_requis") } : {})} />
          <div className="special__actions">
            <Bouton type="submit" variante="danger" chargement={ecriture.isPending}>
              {t("special.confirmer_annulation")}
            </Bouton>
            <Bouton variante="secondaire" disabled={ecriture.isPending} onClick={() => definirAnnulation(null)}>
              {t("special.renoncer")}
            </Bouton>
          </div>
        </form>
      )}
    </Carte>
  );
}

function Publication({ compteId, date, demande, peutPublier }: { compteId: string; date: string; demande: string; peutPublier: boolean }) {
  const { t } = useTranslation();
  const [note, definirNote] = useState("");
  const [erreurNote, definirErreurNote] = useState(false);
  const [echec, definirEchec] = useState<string | null>(null);
  const [publie, definirPublie] = useState<RapportPublie | null>(null);
  const enVol = useRef(false);
  const ecriture = useMutation({
    mutationFn: () => publierRapport(compteId, { date_fin: date, ...(demande.trim() ? { demande: demande.trim() } : {}), ...(note.trim() ? { note_ecart: note.trim() } : {}) }),
    onSuccess: (r) => definirPublie(r),
    onError: (e) => definirEchec(texteErreur(e, t("erreur.inconnue"))),
    onSettled: () => {
      enVol.current = false;
    },
  });
  function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    definirEchec(null);
    definirPublie(null);
    if (note.length > NOTE_MAX) {
      definirErreurNote(true);
      return;
    }
    definirErreurNote(false);
    if (enVol.current) return;
    enVol.current = true;
    ecriture.mutate();
  }
  return (
    <Carte titre={t("special.publier_titre")}>
      {!peutPublier ? (
        <p>{t("special.lecture_seule_publier")}</p>
      ) : (
        <form className="special__formulaire" onSubmit={soumettre} noValidate>
          <p>{t("special.publier_aide", { date })}</p>
          {publie && (
            <Message variante="succes">
              <span>{t("special.publie_ok")}</span> <span className="technique">{t("special.sceau", { sceau: publie.scelle.slice(0, 16) })}</span>
            </Message>
          )}
          {echec && <Message variante="danger">{echec}</Message>}
          <label className="champ__etiquette" htmlFor="note-ecart">
            {t("special.note")}
          </label>
          <textarea id="note-ecart" className="champ__saisie special__note" rows={4} value={note} onChange={(e) => definirNote(e.target.value)} aria-invalid={erreurNote || undefined} />
          {erreurNote && <p className="champ__erreur" role="alert">{t("special.note_trop_longue", { max: NOTE_MAX })}</p>}
          <Bouton type="submit" chargement={ecriture.isPending}>
            {t("special.publier")}
          </Bouton>
        </form>
      )}
    </Carte>
  );
}
