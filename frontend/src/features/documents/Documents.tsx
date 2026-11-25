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
import { adresseContenu, deposerDocument, lireDocuments, remplacerDocument, verifierIntegrite } from "./api";
import { TAILLE_MAX, TYPES_DOCUMENT } from "./types";
import type { DocumentReference, DocumentRemplace, Integrite, TypeDocument } from "./types";
import "./documents.css";

function texteErreur(erreur: unknown, secours: string): string {
  return erreur instanceof ErreurApi && erreur.message ? erreur.message : secours;
}

/**
 * Les documents contractuels d'un projet : consulter, télécharger (l'adresse du contenu telle quelle : le
 * serveur impose `attachment` et vérifie l'empreinte), vérifier l'intégrité, déposer et remplacer. Un
 * document déposé reste une donnée non fiable : l'écran ne l'affiche jamais, il le propose en téléchargement.
 */
export function Documents() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const { data: moi } = useMoi();
  const { projet: projetId } = useSearch({ from: "/protege/documents" });
  const navigate = useNavigate();
  const projet = projetId ? projetParId(moi, projetId) : undefined;
  const peutParametrer = peut(projet, "parametrer");
  const liste = useQuery({ queryKey: ["documents", projetId], queryFn: () => lireDocuments(projetId!), enabled: Boolean(projetId) });
  const [remplace, definirRemplace] = useState<DocumentReference | null>(null);
  const [integrites, definirIntegrites] = useState<Record<string, Integrite | "erreur" | undefined>>({});
  const rafraichir = () => void queryClient.invalidateQueries({ queryKey: ["documents", projetId] });

  async function verifier(d: DocumentReference) {
    try {
      const resultat = await verifierIntegrite(projetId!, d.id);
      definirIntegrites((i) => ({ ...i, [d.id]: resultat }));
    } catch (e) {
      definirIntegrites((i) => ({ ...i, [d.id]: { integre: false, probleme: texteErreur(e, t("erreur.inconnue")) } }));
    }
  }

  return (
    <>
      <div className="page__entete">
        <h1>{t("documents.titre")}</h1>
        <p>{t("documents.intro")}</p>
      </div>
      <Carte>
        <Selecteur
          etiquette={t("documents.projet")}
          valeur={projetId ?? ""}
          options={[
            { valeur: "", libelle: t("documents.choisir_projet") },
            ...(moi?.projets ?? []).map((p) => ({ valeur: p.id, libelle: `${p.code} · ${libelleProjet(p, i18n.language)}` })),
          ]}
          onChange={(v) => void navigate({ to: "/documents", search: v ? { projet: v } : {}, replace: true })}
        />
      </Carte>

      {projetId && (
        <Carte titre={t("documents.liste")}>
          {liste.isPending && <Chargement />}
          {liste.error && <Message variante="danger">{texteErreur(liste.error, t("documents.erreur_lecture"))}</Message>}
          {liste.data && liste.data.length === 0 && <p>{t("documents.vide")}</p>}
          {liste.data && liste.data.length > 0 && (
            <div className="documents__defilement">
              <table className="documents__tableau">
                <caption className="visuellement-cache">{t("documents.liste")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("documents.col_titre")}</th>
                    <th scope="col">{t("documents.col_genre")}</th>
                    <th scope="col">{t("documents.col_version")}</th>
                    <th scope="col">{t("documents.col_emission")}</th>
                    <th scope="col">{t("documents.col_empreinte")}</th>
                    <th scope="col">{t("documents.col_etat")}</th>
                    <th scope="col">{t("documents.col_actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {liste.data.map((d) => {
                    const integrite = integrites[d.id];
                    return (
                      <tr key={d.id}>
                        <th scope="row">{d.title}</th>
                        <td>{t(`documents.genre.${d.kind}`)}</td>
                        <td>{d.version || "—"}</td>
                        <td>{d.issued_on ?? "—"}</td>
                        <td className="technique" title={d.sha256}>{d.sha256.slice(0, 12)}…</td>
                        <td>{d.remplace_par ? <Pastille variante="neutre">{t("documents.remplace")}</Pastille> : <Pastille variante="succes">{t("documents.courant")}</Pastille>}</td>
                        <td>
                          <div className="documents__actions">
                            <a className="documents__lien" href={adresseContenu(projetId, d.id)} aria-label={t("documents.telecharger", { titre: d.title })}>
                              {t("documents.telecharger_court")}
                            </a>
                            <Bouton variante="secondaire" aria-label={t("documents.verifier", { titre: d.title })} onClick={() => void verifier(d)}>
                              {t("documents.verifier_court")}
                            </Bouton>
                            {peutParametrer && !d.remplace_par && (
                              <Bouton variante="secondaire" aria-label={t("documents.remplacer", { titre: d.title })} onClick={() => definirRemplace(d)}>
                                {t("documents.remplacer_court")}
                              </Bouton>
                            )}
                          </div>
                          {integrite && integrite !== "erreur" && (
                            <Message variante={integrite.integre ? "succes" : "danger"}>{integrite.integre ? t("documents.integre") : (integrite.probleme ?? t("documents.altere"))}</Message>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Carte>
      )}

      {projetId && remplace && <FormulaireRemplacement key={remplace.id} projetId={projetId} document={remplace} surSucces={rafraichir} />}

      {projetId && (
        <Carte titre={t("documents.deposer_titre")}>
          {peutParametrer ? <FormulaireDepot projetId={projetId} surSucces={rafraichir} /> : <p>{t("documents.lecture_seule")}</p>}
        </Carte>
      )}
    </>
  );
}

function controleFichier(fichier: File | null, t: (cle: string) => string): string | undefined {
  if (!fichier) return t("documents.fichier_requis");
  if (fichier.size > TAILLE_MAX) return t("documents.fichier_trop_gros");
  return undefined;
}

function FormulaireDepot({ projetId, surSucces }: { projetId: string; surSucces: () => void }) {
  const { t } = useTranslation();
  const [genre, definirGenre] = useState<TypeDocument>("financing_agreement");
  const [titre, definirTitre] = useState("");
  const [version, definirVersion] = useState("");
  const [emission, definirEmission] = useState("");
  const [fichier, definirFichier] = useState<File | null>(null);
  const [erreurs, definirErreurs] = useState<{ titre?: string | undefined; fichier?: string | undefined }>({});
  const [echec, definirEchec] = useState<string | null>(null);
  const [succes, definirSucces] = useState(false);
  const enVol = useRef(false);
  const ecriture = useMutation({
    mutationFn: (formulaire: FormData) => deposerDocument(projetId, formulaire),
    onSuccess: () => {
      definirSucces(true);
      definirTitre("");
      definirVersion("");
      definirEmission("");
      definirFichier(null);
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
    const manques = { ...(titre.trim() ? {} : { titre: t("documents.titre_requis") }), fichier: controleFichier(fichier, t) };
    definirErreurs(manques);
    if (manques.titre || manques.fichier || !fichier || enVol.current) return;
    enVol.current = true;
    const formulaire = new FormData();
    formulaire.set("kind", genre);
    formulaire.set("title", titre.trim());
    if (version.trim()) formulaire.set("version", version.trim());
    if (emission) formulaire.set("issued_on", emission);
    formulaire.set("fichier", fichier);
    ecriture.mutate(formulaire);
  }
  return (
    <form className="documents__formulaire" onSubmit={soumettre} noValidate>
      {succes && <Message variante="succes">{t("documents.depose")}</Message>}
      {echec && <Message variante="danger">{echec}</Message>}
      <Selecteur etiquette={t("documents.genre_champ")} valeur={genre} options={TYPES_DOCUMENT.map((g) => ({ valeur: g, libelle: t(`documents.genre.${g}`) }))} onChange={(v) => definirGenre(v as TypeDocument)} />
      <Champ etiquette={t("documents.titre_champ")} value={titre} onChange={(e) => definirTitre(e.target.value)} {...(erreurs.titre ? { erreur: erreurs.titre } : {})} />
      <Champ etiquette={t("documents.version_champ")} value={version} onChange={(e) => definirVersion(e.target.value)} />
      <Champ etiquette={t("documents.emission_champ")} type="date" value={emission} onChange={(e) => definirEmission(e.target.value)} />
      <Champ
        etiquette={t("documents.fichier_champ")}
        type="file"
        aide={t("documents.fichier_aide")}
        onChange={(e) => definirFichier(e.target.files?.[0] ?? null)}
        {...(erreurs.fichier ? { erreur: erreurs.fichier } : {})}
      />
      {ecriture.isPending && <progress aria-label={t("documents.envoi_en_cours")} className="documents__progression" />}
      <Bouton type="submit" chargement={ecriture.isPending}>
        {t("documents.deposer")}
      </Bouton>
    </form>
  );
}

function FormulaireRemplacement({ projetId, document, surSucces }: { projetId: string; document: DocumentReference; surSucces: () => void }) {
  const { t } = useTranslation();
  const [version, definirVersion] = useState("");
  const [emission, definirEmission] = useState("");
  const [fichier, definirFichier] = useState<File | null>(null);
  const [erreur, definirErreur] = useState<string | undefined>();
  const [echec, definirEchec] = useState<string | null>(null);
  const [resultat, definirResultat] = useState<DocumentRemplace | null>(null);
  const enVol = useRef(false);
  const ecriture = useMutation({
    mutationFn: (formulaire: FormData) => remplacerDocument(projetId, document.id, formulaire),
    onSuccess: (r) => {
      definirResultat(r);
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
    definirResultat(null);
    const probleme = controleFichier(fichier, t);
    definirErreur(probleme);
    if (probleme || !fichier || enVol.current) return;
    enVol.current = true;
    const formulaire = new FormData();
    if (version.trim()) formulaire.set("version", version.trim());
    if (emission) formulaire.set("issued_on", emission);
    formulaire.set("fichier", fichier);
    ecriture.mutate(formulaire);
  }
  return (
    <Carte titre={t("documents.remplacer_titre", { titre: document.title })}>
      <form className="documents__formulaire" onSubmit={soumettre} noValidate>
        {resultat && (
          <Message variante="succes">
            {resultat.exigences_a_reverifier.length > 0
              ? `${t("documents.remplace_ok")} ${t("documents.a_reverifier", { codes: resultat.exigences_a_reverifier.join(", ") })}`
              : t("documents.remplace_ok")}
          </Message>
        )}
        {echec && <Message variante="danger">{echec}</Message>}
        <Champ etiquette={t("documents.nouveau_fichier")} type="file" aide={t("documents.fichier_aide")} onChange={(e) => definirFichier(e.target.files?.[0] ?? null)} {...(erreur ? { erreur } : {})} />
        <Champ etiquette={t("documents.version_remplacant")} value={version} onChange={(e) => definirVersion(e.target.value)} />
        <Champ etiquette={t("documents.emission_champ")} type="date" value={emission} onChange={(e) => definirEmission(e.target.value)} />
        {ecriture.isPending && <progress aria-label={t("documents.envoi_en_cours")} className="documents__progression" />}
        <Bouton type="submit" chargement={ecriture.isPending}>
          {t("documents.remplacer_bouton")}
        </Bouton>
      </form>
    </Carte>
  );
}
