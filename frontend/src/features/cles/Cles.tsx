import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ErreurApi } from "../../shared/api/client";
import { additionner, lire } from "../../shared/money/montant";
import { peut, projetParId } from "../../shared/session/droits";
import { useMoi } from "../../shared/session/moi";
import { Bouton } from "../../shared/ui/Bouton";
import { Carte } from "../../shared/ui/Carte";
import { Champ } from "../../shared/ui/Champ";
import { Chargement } from "../../shared/ui/Chargement";
import { Message } from "../../shared/ui/Message";
import { Selecteur } from "../../shared/ui/Selecteur";
import { libelleProjet } from "../projets/libelle";
import { creerCle, creerVersion, lireAccordsDuProjet, lireCle, lireCles } from "./api";
import type { PartCle } from "./types";
import "./cles.css";

function texteErreur(erreur: unknown, secours: string): string {
  return erreur instanceof ErreurApi && erreur.message ? erreur.message : secours;
}

/** Une part saisie : une chaîne décimale strictement positive (virgule acceptée), sinon `null`. Jamais un `number`. */
function partExacte(brut: string): string | null {
  const valeur = brut.trim().replace(",", ".");
  return /^\d+(\.\d+)?$/.test(valeur) && /[1-9]/.test(valeur) ? valeur : null;
}

/** Une part rendue par le serveur (0.6) en pourcentage exact (60), sans zéros inutiles. */
function enPourcent(part: string): string {
  return lire(part).times(100).toDecimalPlaces(4).toFixed();
}

function unePart(p: PartCle, pourcent: (n: string) => string): string {
  return `${p.accord} ${pourcent(enPourcent(p.part))}`;
}

/**
 * Les clés de cofinancement d'un projet : consulter leurs versions et en créer. Les parts sont saisies en
 * pourcentage et leur total doit valoir exactement 100 % (vérifié ici, avec des décimaux exacts, ET par le
 * serveur, qui normalise les poids et refuse accords clos ou dates incohérentes).
 */
export function Cles() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const { data: moi } = useMoi();
  const { projet: projetId, cle: cleId } = useSearch({ from: "/protege/cles-cofinancement" });
  const navigate = useNavigate();
  const projet = projetId ? projetParId(moi, projetId) : undefined;
  const peutParametrer = peut(projet, "parametrer");
  const aller = (search: { projet?: string; cle?: string }) => void navigate({ to: "/cles-cofinancement", search, replace: true });
  const pourcent = (n: string) => (i18n.language.startsWith("fr") ? `${n}\u00a0%` : `${n}%`);
  const nom = (label: { fr?: string; en?: string }, code: string) => label[i18n.language === "en" ? "en" : "fr"] ?? label.fr ?? code;
  const liste = useQuery({ queryKey: ["cles", projetId], queryFn: () => lireCles(projetId!), enabled: Boolean(projetId) });

  return (
    <>
      <div className="page__entete">
        <h1>{t("cles.titre")}</h1>
        <p>{t("cles.intro")}</p>
      </div>
      <Carte>
        <Selecteur
          etiquette={t("cles.projet")}
          valeur={projetId ?? ""}
          options={[
            { valeur: "", libelle: t("cles.choisir_projet") },
            ...(moi?.projets ?? []).map((p) => ({ valeur: p.id, libelle: `${p.code} · ${libelleProjet(p, i18n.language)}` })),
          ]}
          onChange={(v) => aller(v ? { projet: v } : {})}
        />
      </Carte>

      {projetId && (
        <Carte titre={t("cles.liste")}>
          {liste.isPending && <Chargement />}
          {liste.error && <Message variante="danger">{texteErreur(liste.error, t("cles.erreur_lecture"))}</Message>}
          {liste.data && liste.data.length === 0 && <p>{t("cles.vide")}</p>}
          {liste.data && liste.data.length > 0 && (
            <div className="cles__defilement">
              <table className="cles__tableau">
                <caption className="visuellement-cache">{t("cles.liste")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("cles.col_code")}</th>
                    <th scope="col">{t("cles.col_libelle")}</th>
                    <th scope="col">{t("cles.col_parts")}</th>
                    <th scope="col">{t("cles.col_action")}</th>
                  </tr>
                </thead>
                <tbody>
                  {liste.data.map((c) => (
                    <tr key={c.id} aria-current={c.id === cleId ? "true" : undefined}>
                      <th scope="row" className="technique">{c.code}</th>
                      <td>{nom(c.label, c.code)}</td>
                      <td>
                        {c.version_en_vigueur ? (
                          <ul className="cles__parts">
                            {c.version_en_vigueur.parts.map((p) => (
                              <li key={p.accord}>{unePart(p, pourcent)}</li>
                            ))}
                          </ul>
                        ) : (
                          t("cles.sans_version")
                        )}
                      </td>
                      <td>
                        <Bouton variante="secondaire" aria-label={t("cles.ouvrir", { code: c.code })} onClick={() => aller({ projet: projetId, cle: c.id })}>
                          {t("cles.ouvrir", { code: c.code })}
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

      {projetId && (
        <Carte titre={t("cles.nouvelle")}>
          {peutParametrer ? (
            <FormulaireCle
              projetId={projetId}
              surSucces={() => void queryClient.invalidateQueries({ queryKey: ["cles", projetId] })}
            />
          ) : (
            <p>{t("cles.lecture_seule")}</p>
          )}
        </Carte>
      )}

      {projetId && cleId && <DetailCle key={cleId} projetId={projetId} cleId={cleId} peutParametrer={peutParametrer} pourcent={pourcent} />}
    </>
  );
}

function FormulaireCle({ projetId, surSucces }: { projetId: string; surSucces: () => void }) {
  const { t } = useTranslation();
  const [code, definirCode] = useState("");
  const [fr, definirFr] = useState("");
  const [en, definirEn] = useState("");
  const [erreurs, definirErreurs] = useState<{ code?: string; label?: string }>({});
  const [echec, definirEchec] = useState<string | null>(null);
  const [succes, definirSucces] = useState(false);
  const enVol = useRef(false);
  const ecriture = useMutation({
    mutationFn: () => creerCle(projetId, { code: code.trim(), label: { ...(fr.trim() ? { fr: fr.trim() } : {}), ...(en.trim() ? { en: en.trim() } : {}) } }),
    onSuccess: () => {
      definirSucces(true);
      definirCode("");
      definirFr("");
      definirEn("");
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
    const manques = {
      ...(code.trim() ? {} : { code: t("cles.code_requis") }),
      ...(fr.trim() || en.trim() ? {} : { label: t("cles.libelle_requis") }),
    };
    definirErreurs(manques);
    if (manques.code || manques.label || enVol.current) return;
    enVol.current = true;
    ecriture.mutate();
  }
  return (
    <form className="cles__formulaire" onSubmit={soumettre} noValidate>
      {succes && <Message variante="succes">{t("cles.creee")}</Message>}
      {echec && <Message variante="danger">{echec}</Message>}
      <Champ etiquette={t("cles.code")} value={code} onChange={(e) => definirCode(e.target.value)} {...(erreurs.code ? { erreur: erreurs.code } : {})} />
      <Champ etiquette={t("cles.libelle_fr")} value={fr} onChange={(e) => definirFr(e.target.value)} {...(erreurs.label ? { erreur: erreurs.label } : {})} />
      <Champ etiquette={t("cles.libelle_en")} value={en} onChange={(e) => definirEn(e.target.value)} />
      <Bouton type="submit" chargement={ecriture.isPending}>
        {t("cles.creer")}
      </Bouton>
    </form>
  );
}

function DetailCle({ projetId, cleId, peutParametrer, pourcent }: { projetId: string; cleId: string; peutParametrer: boolean; pourcent: (n: string) => string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const detail = useQuery({ queryKey: ["cle", projetId, cleId], queryFn: () => lireCle(projetId, cleId) });
  if (detail.isPending) return <Chargement />;
  if (detail.error) return <Message variante="danger">{texteErreur(detail.error, t("cles.erreur_lecture"))}</Message>;
  const c = detail.data;
  return (
    <Carte>
      <h2 className="carte__titre">{t("cles.detail", { code: c.code })}</h2>
      {c.versions.length === 0 ? (
        <p>{t("cles.sans_version")}</p>
      ) : (
        <div className="cles__defilement">
          <table className="cles__tableau">
            <caption className="visuellement-cache">{t("cles.versions")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("cles.col_version")}</th>
                <th scope="col">{t("cles.col_du")}</th>
                <th scope="col">{t("cles.col_au")}</th>
                <th scope="col">{t("cles.col_parts")}</th>
                <th scope="col">{t("cles.col_motif")}</th>
              </tr>
            </thead>
            <tbody>
              {c.versions.map((v) => (
                <tr key={v.id}>
                  <td>{v.version}</td>
                  <td>{v.valid_from}</td>
                  <td>{v.valid_to ?? "—"}</td>
                  <td>
                    <ul className="cles__parts">
                      {v.parts.map((p) => (
                        <li key={p.accord}>{unePart(p, pourcent)}</li>
                      ))}
                    </ul>
                    <small>{t("cles.porteur", { accord: v.porteur })}</small>
                  </td>
                  <td>{v.motif || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <h3>{t("cles.nouvelle_version")}</h3>
      {peutParametrer ? (
        <FormulaireVersion
          projetId={projetId}
          cleId={cleId}
          pourcent={pourcent}
          surSucces={() => {
            void queryClient.invalidateQueries({ queryKey: ["cle", projetId, cleId] });
            void queryClient.invalidateQueries({ queryKey: ["cles", projetId] });
          }}
        />
      ) : (
        <p>{t("cles.lecture_seule")}</p>
      )}
    </Carte>
  );
}

function FormulaireVersion({ projetId, cleId, pourcent, surSucces }: { projetId: string; cleId: string; pourcent: (n: string) => string; surSucces: () => void }) {
  const { t } = useTranslation();
  const accords = useQuery({ queryKey: ["accords", projetId], queryFn: () => lireAccordsDuProjet(projetId) });
  const [parts, definirParts] = useState<Record<string, string | undefined>>({}); // numéro d'accord → saisie ; absent = non choisi
  const [porteurChoisi, definirPorteur] = useState("");
  const [date, definirDate] = useState("");
  const [motif, definirMotif] = useState("");
  const [erreur, definirErreur] = useState<string | null>(null);
  const [echec, definirEchec] = useState<string | null>(null);
  const [succes, definirSucces] = useState(false);
  const enVol = useRef(false);

  const choisis = Object.keys(parts).sort();
  const porteur = choisis.includes(porteurChoisi) ? porteurChoisi : (choisis[0] ?? "");
  const valides = choisis.map((n) => partExacte(parts[n] ?? ""));
  const total = additionner("0", ...valides.filter((v): v is string => v !== null));

  const ecriture = useMutation({
    mutationFn: () =>
      creerVersion(projetId, cleId, {
        parts: Object.fromEntries(choisis.map((n, i) => [n, valides[i]!])),
        porteur,
        valid_from: date,
        ...(motif.trim() ? { motif: motif.trim() } : {}),
      }),
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
    const probleme = (() => {
      if (choisis.length === 0) return t("cles.accord_requis");
      if (valides.some((v) => v === null)) return t("cles.part_invalide");
      if (lire(total).comparedTo(100) !== 0) return t("cles.total_invalide", { total: pourcent(total) });
      if (!date) return t("cles.date_requise");
      return null;
    })();
    definirErreur(probleme);
    if (probleme || enVol.current) return;
    enVol.current = true;
    ecriture.mutate();
  }

  if (accords.isPending) return <Chargement />;
  if (accords.error) return <Message variante="danger">{texteErreur(accords.error, t("cles.erreur_lecture"))}</Message>;
  return (
    <form className="cles__formulaire" onSubmit={soumettre} noValidate>
      {succes && <Message variante="succes">{t("cles.version_creee")}</Message>}
      {echec && <Message variante="danger">{echec}</Message>}
      {erreur && <Message variante="attention">{erreur}</Message>}
      <fieldset className="cles__accords">
        <legend>{t("cles.accords")}</legend>
        {accords.data.map((a) => {
          const coche = a.numero in parts;
          return (
            <div key={a.id} className="cles__accord">
              <label className="cles__case">
                <input
                  type="checkbox"
                  checked={coche}
                  onChange={(e) =>
                    definirParts((p) => {
                      const suite = { ...p };
                      if (e.target.checked) suite[a.numero] = "";
                      else delete suite[a.numero];
                      return suite;
                    })
                  }
                />
                {a.numero} · {a.bailleur}
              </label>
              {coche && (
                <Champ
                  etiquette={t("cles.part_de", { numero: a.numero })}
                  inputMode="decimal"
                  autoComplete="off"
                  value={parts[a.numero] ?? ""}
                  onChange={(e) => definirParts((p) => ({ ...p, [a.numero]: e.target.value }))}
                />
              )}
            </div>
          );
        })}
      </fieldset>
      <p aria-live="polite">{t("cles.total", { total: pourcent(total) })}</p>
      <Selecteur etiquette={t("cles.porteur_arrondi")} valeur={porteur} options={choisis.map((n) => ({ valeur: n, libelle: n }))} onChange={definirPorteur} />
      <Champ etiquette={t("cles.date_effet")} type="date" value={date} onChange={(e) => definirDate(e.target.value)} />
      <Champ etiquette={t("cles.motif")} value={motif} onChange={(e) => definirMotif(e.target.value)} />
      <Bouton type="submit" chargement={ecriture.isPending}>
        {t("cles.creer_version")}
      </Bouton>
    </form>
  );
}
