import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ErreurApi } from "../../shared/api/client";
import { comparer, lire } from "../../shared/money/montant";
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
import { FormulaireControle } from "./FormulaireControle";
import { activerControle, installerBibliotheque, lireBibliotheque, lireControle, lireControles, rejeterControle, validerControle } from "./api";
import { SEUILS, STATUTS } from "./types";
import type { AppelDecision, CodeSeuil, DemandeInstallation, Libelle, Severite, StatutControle } from "./types";
import "./controles.css";

const VARIANTE_STATUT: Record<StatutControle, "attention" | "accent" | "succes" | "neutre" | "alerte"> = {
  draft: "attention",
  validated: "accent",
  active: "succes",
  superseded: "neutre",
  rejected: "alerte",
};
const VARIANTE_SEVERITE: Record<Severite, "alerte" | "attention" | "neutre"> = { bloquant: "alerte", avertissement: "attention", information: "neutre" };

function texteErreur(erreur: unknown, secours: string): string {
  return erreur instanceof ErreurApi && erreur.message ? erreur.message : secours;
}
const estCodeSeuil = (code: string): code is CodeSeuil => code in SEUILS;

/** Un seuil saisi, exact : `null` = vide (le serveur applique son défaut), `"invalide"` = refusé, sinon la valeur à envoyer. */
function seuil(code: CodeSeuil, brut: string): string | number | null | "invalide" {
  const valeur = brut.trim().replace(",", ".");
  if (!valeur) return null;
  const nature = SEUILS[code].nature;
  if (nature === "pourcentage") {
    if (!/^\d+(\.\d+)?$/.test(valeur) || comparer(valeur, "100") > 0) return "invalide";
    return lire(valeur).toFixed();
  }
  if (nature === "jours") return /^[1-9]\d*$/.test(valeur) ? Number(valeur) : "invalide";
  return /^\d+$/.test(valeur) ? Number(valeur) : "invalide";
}

/**
 * Les contrôles d'un projet : consulter leurs versions, décider d'un brouillon (valider, activer, rejeter) et installer
 * des contrôles de la bibliothèque livrée (toujours en BROUILLON : jamais validés ni activés automatiquement). Le serveur
 * reste l'autorité ; la règle d'un contrôle s'affiche en lecture seule.
 */
export function Controles() {
  const { t, i18n } = useTranslation();
  const { data: moi } = useMoi();
  const { projet: projetId, controle: controleId } = useSearch({ from: "/protege/controles" });
  const navigate = useNavigate();
  const projet = projetId ? projetParId(moi, projetId) : undefined;
  const [filtre, definirFiltre] = useState<"" | StatutControle>("");
  const [information, definirInformation] = useState<string | null>(null);
  const [creation, definirCreation] = useState(false);
  const queryClient = useQueryClient();
  const aller = (search: { projet?: string; controle?: string }) => void navigate({ to: "/controles", search, replace: true });
  const liste = useQuery({ queryKey: ["controles", projetId, filtre], queryFn: () => lireControles(projetId!, filtre || undefined), enabled: Boolean(projetId) });
  const nom = (l: Libelle, code: string) => l[i18n.language === "en" ? "en" : "fr"] ?? l.fr ?? code;

  return (
    <>
      <div className="page__entete">
        <h1>{t("controles.titre")}</h1>
        <p>{t("controles.intro")}</p>
      </div>
      <Carte>
        <Selecteur
          etiquette={t("controles.projet")}
          valeur={projetId ?? ""}
          options={[
            { valeur: "", libelle: t("controles.choisir_projet") },
            ...(moi?.projets ?? []).map((p) => ({ valeur: p.id, libelle: `${p.code} · ${libelleProjet(p, i18n.language)}` })),
          ]}
          onChange={(v) => aller(v ? { projet: v } : {})}
        />
      </Carte>

      {information && <Message variante="succes">{information}</Message>}

      {projetId && peut(projet, "parametrer") && !creation && (
        <div className="controles__actions">
          <Bouton onClick={() => { definirInformation(null); definirCreation(true); }}>{t("controles.form.nouveau")}</Bouton>
        </div>
      )}
      {projetId && creation && (
        <FormulaireControle
          projetId={projetId}
          surAnnulation={() => definirCreation(false)}
          surTermine={(c) => {
            definirCreation(false);
            definirInformation(t("controles.form.cree", { code: c.code }));
            void queryClient.invalidateQueries({ queryKey: ["controles", projetId] });
            aller({ projet: projetId, controle: c.id });
          }}
        />
      )}

      {projetId && (
        <Carte titre={t("controles.liste")}>
          <Selecteur
            etiquette={t("controles.filtre_etat")}
            valeur={filtre}
            options={[{ valeur: "", libelle: t("controles.tous_etats") }, ...STATUTS.map((s) => ({ valeur: s, libelle: t(`controles.etat.${s}`) }))]}
            onChange={(v) => definirFiltre(v as "" | StatutControle)}
          />
          {liste.isPending && <Chargement />}
          {liste.error && <Message variante="danger">{texteErreur(liste.error, t("controles.erreur_lecture"))}</Message>}
          {liste.data && liste.data.length === 0 && <p>{t("controles.vide")}</p>}
          {liste.data && liste.data.length > 0 && (
            <div className="controles__defilement">
              <table className="controles__tableau">
                <caption className="visuellement-cache">{t("controles.liste")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("controles.col_code")}</th>
                    <th scope="col">{t("controles.col_version")}</th>
                    <th scope="col">{t("controles.col_etat")}</th>
                    <th scope="col">{t("controles.col_severite")}</th>
                    <th scope="col">{t("controles.col_libelle")}</th>
                    <th scope="col">{t("controles.col_effet")}</th>
                    <th scope="col">{t("controles.col_action")}</th>
                  </tr>
                </thead>
                <tbody>
                  {liste.data.map((c) => (
                    <tr key={c.id} aria-current={c.id === controleId ? "true" : undefined}>
                      <th scope="row" className="technique">{c.code}</th>
                      <td>{c.version}</td>
                      <td>
                        <Pastille variante={VARIANTE_STATUT[c.status]}>{t(`controles.etat.${c.status}`)}</Pastille>
                      </td>
                      <td>
                        <Pastille variante={VARIANTE_SEVERITE[c.severity]}>{t(`controles.severite.${c.severity}`)}</Pastille>
                      </td>
                      <td>{nom(c.label, c.code)}</td>
                      <td>{c.valid_from}</td>
                      <td>
                        <Bouton variante="secondaire" aria-label={t("controles.ouvrir", { code: c.code, version: c.version })} onClick={() => { definirInformation(null); aller({ projet: projetId, controle: c.id }); }}>
                          {t("controles.ouvrir_court")}
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

      {projetId && controleId && (
        <DetailControle key={controleId} projetId={projetId} controleId={controleId} peutValider={peut(projet, "valider")} peutParametrer={peut(projet, "parametrer")} surSucces={definirInformation} />
      )}

      {projetId && <Bibliotheque projetId={projetId} peutParametrer={peut(projet, "parametrer")} surSucces={definirInformation} />}
    </>
  );
}

function DetailControle({ projetId, controleId, peutValider, peutParametrer, surSucces }: { projetId: string; controleId: string; peutValider: boolean; peutParametrer: boolean; surSucces: (t: string | null) => void }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const cle = ["controle", projetId, controleId];
  const detail = useQuery({ queryKey: cle, queryFn: () => lireControle(projetId, controleId) });
  const [erreur, definirErreur] = useState<string | null>(null);
  const [rejet, definirRejet] = useState(false);
  const [motif, definirMotif] = useState("");
  const [motifManquant, definirMotifManquant] = useState(false);
  const enVol = useRef(false);
  const decision = useMutation({
    mutationFn: ({ appel }: { appel: AppelDecision; succes: string }) => appel(),
    onSuccess: (controle, { succes }) => {
      queryClient.setQueryData(cle, controle);
      void queryClient.invalidateQueries({ queryKey: ["controles", projetId] });
      surSucces(succes);
      definirRejet(false);
    },
    onError: (e) => definirErreur(texteErreur(e, t("erreur.inconnue"))),
    onSettled: () => {
      enVol.current = false;
    },
  });
  function decider(appel: AppelDecision, succes: string) {
    if (enVol.current) return;
    enVol.current = true;
    definirErreur(null);
    decision.mutate({ appel, succes });
  }
  if (detail.isPending) return <Chargement />;
  if (detail.error) return <Message variante="danger">{texteErreur(detail.error, t("controles.erreur_lecture"))}</Message>;
  const c = detail.data;
  const action = c.action_corrective?.[i18n.language === "en" ? "en" : "fr"] ?? c.action_corrective?.fr;
  const decidable = c.status === "draft" || c.status === "validated";
  const peutAgir = (c.status === "draft" && peutValider) || (c.status === "validated" && (peutValider || peutParametrer));

  function rejeter(evenement: FormEvent) {
    evenement.preventDefault();
    if (!motif.trim()) {
      definirMotifManquant(true);
      return;
    }
    definirMotifManquant(false);
    decider(() => rejeterControle(projetId, controleId, motif.trim()), t("controles.rejete_ok"));
  }

  return (
    <Carte>
      <h2 className="carte__titre">{t("controles.detail", { code: c.code, version: c.version })}</h2>
      <p className="controles__ligne">
        <Pastille variante={VARIANTE_STATUT[c.status]}>{t(`controles.etat.${c.status}`)}</Pastille>
        <Pastille variante={VARIANTE_SEVERITE[c.severity]}>{t(`controles.severite.${c.severity}`)}</Pastille>
        <span className="technique">{c.type_regle}</span>
      </p>
      {action && (
        <>
          <h3>{t("controles.action_corrective")}</h3>
          <p>{action}</p>
        </>
      )}
      <h3>{t("controles.regle")}</h3>
      <pre className="controles__regle" role="group" aria-label={t("controles.regle_lecture_seule")} tabIndex={0}>
        {JSON.stringify({ expression: c.expression, applicable_si: c.applicable_si, parametres: c.parametres }, null, 2)}
      </pre>
      {erreur && <Message variante="danger">{erreur}</Message>}
      {decidable && !peutAgir && <p>{t("controles.lecture_seule")}</p>}
      {c.status === "draft" && peutValider && !rejet && (
        <div className="controles__actions">
          <Bouton chargement={decision.isPending} onClick={() => decider(() => validerControle(projetId, controleId), t("controles.valide_ok"))}>
            {t("controles.valider")}
          </Bouton>
        </div>
      )}
      {c.status === "validated" && !rejet && (peutParametrer || peutValider) && (
        <div className="controles__actions">
          {peutParametrer && (
            <Bouton chargement={decision.isPending} onClick={() => decider(() => activerControle(projetId, controleId), t("controles.active_ok"))}>
              {t("controles.activer")}
            </Bouton>
          )}
          {peutValider && (
            <Bouton variante="secondaire" disabled={decision.isPending} onClick={() => definirRejet(true)}>
              {t("controles.rejeter")}
            </Bouton>
          )}
        </div>
      )}
      {rejet && (
        <form className="controles__actions" onSubmit={rejeter} noValidate>
          <Champ etiquette={t("controles.motif")} value={motif} onChange={(e) => definirMotif(e.target.value)} {...(motifManquant ? { erreur: t("controles.motif_requis") } : {})} />
          <Bouton type="submit" variante="danger" chargement={decision.isPending}>
            {t("controles.rejeter_confirmer")}
          </Bouton>
          <Bouton variante="secondaire" disabled={decision.isPending} onClick={() => definirRejet(false)}>
            {t("controles.annuler")}
          </Bouton>
        </form>
      )}
    </Carte>
  );
}

function Bibliotheque({ projetId, peutParametrer, surSucces }: { projetId: string; peutParametrer: boolean; surSucces: (t: string | null) => void }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const livres = useQuery({ queryKey: ["bibliotheque", projetId], queryFn: () => lireBibliotheque(projetId) });
  const [coches, definirCoches] = useState<string[]>([]);
  const [valeurs, definirValeurs] = useState<Record<string, string>>({});
  const [date, definirDate] = useState("");
  const [erreurs, definirErreurs] = useState<{ choix?: string; date?: string; seuils: Record<string, string> }>({ seuils: {} });
  const [echec, definirEchec] = useState<string | null>(null);
  const enVol = useRef(false);
  const ecriture = useMutation({
    mutationFn: (demande: DemandeInstallation) => installerBibliotheque(projetId, demande),
    onSuccess: (r) => {
      surSucces(t("controles.installe_ok", { count: r.crees.length, codes: r.crees.join(", ") }));
      definirCoches([]);
      void queryClient.invalidateQueries({ queryKey: ["bibliotheque", projetId] });
      void queryClient.invalidateQueries({ queryKey: ["controles", projetId] });
    },
    onError: (e) => definirEchec(texteErreur(e, t("erreur.inconnue"))),
    onSettled: () => {
      enVol.current = false;
    },
  });
  const nom = (l: Libelle, code: string) => l[i18n.language === "en" ? "en" : "fr"] ?? l.fr ?? code;

  function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    definirEchec(null);
    surSucces(null);
    const codes = [...coches].sort();
    const seuils: Record<string, string | number> = {};
    const fautes: Record<string, string> = {};
    for (const code of codes.filter(estCodeSeuil)) {
      const v = seuil(code, valeurs[code] ?? "");
      if (v === "invalide") fautes[code] = t(`controles.seuil_invalide.${SEUILS[code].nature}`);
      else if (v !== null) seuils[code] = v;
    }
    const manques = { ...(codes.length ? {} : { choix: t("controles.choix_requis") }), ...(date ? {} : { date: t("controles.date_requise") }), seuils: fautes };
    definirErreurs(manques);
    if (manques.choix || manques.date || Object.keys(fautes).length || enVol.current) return;
    enVol.current = true;
    ecriture.mutate({ codes, valid_from: date, ...(Object.keys(seuils).length ? { seuils } : {}) });
  }

  return (
    <Carte titre={t("controles.bibliotheque")}>
      <p>{t("controles.bibliotheque_aide")}</p>
      {livres.isPending && <Chargement />}
      {livres.error && <Message variante="danger">{texteErreur(livres.error, t("controles.erreur_lecture"))}</Message>}
      {livres.data && (
        <form onSubmit={soumettre} noValidate className="controles__formulaire">
          {echec && <Message variante="danger">{echec}</Message>}
          {erreurs.choix && <Message variante="attention">{erreurs.choix}</Message>}
          <div className="controles__defilement">
            <table className="controles__tableau">
              <caption className="visuellement-cache">{t("controles.livres")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("controles.col_choix")}</th>
                  <th scope="col">{t("controles.col_famille")}</th>
                  <th scope="col">{t("controles.col_severite")}</th>
                  <th scope="col">{t("controles.col_seuil")}</th>
                </tr>
              </thead>
              <tbody>
                {livres.data.map((d) => {
                  const coche = coches.includes(d.code);
                  return (
                    <tr key={d.code}>
                      <td>
                        <label className="controles__case">
                          <input
                            type="checkbox"
                            checked={coche}
                            disabled={d.installe || !peutParametrer}
                            onChange={(e) => definirCoches((c) => (e.target.checked ? [...c, d.code] : c.filter((x) => x !== d.code)))}
                          />
                          {d.code} · {nom(d.label, d.code)}
                        </label>
                        {d.installe && <Pastille variante="succes">{t("controles.installe")}</Pastille>}
                      </td>
                      <td>{d.famille}</td>
                      <td>
                        <Pastille variante={VARIANTE_SEVERITE[d.severity]}>{t(`controles.severite.${d.severity}`)}</Pastille>
                      </td>
                      <td>
                        {coche && estCodeSeuil(d.code) && (
                          <Champ
                            etiquette={t(`controles.seuil.${SEUILS[d.code].nature}`, { code: d.code })}
                            inputMode="decimal"
                            autoComplete="off"
                            value={valeurs[d.code] ?? ""}
                            onChange={(e) => definirValeurs((v) => ({ ...v, [d.code]: e.target.value }))}
                            {...(erreurs.seuils[d.code] ? { erreur: erreurs.seuils[d.code] } : {})}
                          />
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {peutParametrer ? (
            <>
              <Champ etiquette={t("controles.date_effet")} type="date" value={date} onChange={(e) => definirDate(e.target.value)} {...(erreurs.date ? { erreur: erreurs.date } : {})} />
              <Bouton type="submit" chargement={ecriture.isPending}>
                {t("controles.installer")}
              </Bouton>
            </>
          ) : (
            <p>{t("controles.lecture_seule_installer")}</p>
          )}
        </form>
      )}
    </Carte>
  );
}
