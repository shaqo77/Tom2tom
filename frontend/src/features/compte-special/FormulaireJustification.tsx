import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { ErreurApi } from "../../shared/api/client";
import { Bouton } from "../../shared/ui/Bouton";
import { Champ } from "../../shared/ui/Champ";
import { Message } from "../../shared/ui/Message";
import { Selecteur } from "../../shared/ui/Selecteur";
import { justifierDemande, lireDemandes } from "./api";
import { construireJustification } from "./justification";
import type { Faute } from "./justification";

function texteErreur(erreur: unknown, secours: string): string {
  return erreur instanceof ErreurApi && erreur.message ? erreur.message : secours;
}

/** Justifier à la Banque une demande de retrait : on la choisit dans la liste du projet, le serveur applique ses règles. */
export function FormulaireJustification({ projetId, compteId }: { projetId: string; compteId: string }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const demandes = useQuery({ queryKey: ["demandes-retrait", projetId], queryFn: () => lireDemandes(projetId) });
  const [demande, definirDemande] = useState("");
  const [montant, definirMontant] = useState("");
  const [date, definirDate] = useState("");
  const [fautes, definirFautes] = useState<Faute[]>([]);
  const [echec, definirEchec] = useState<string | null>(null);
  const [succes, definirSucces] = useState(false);
  const ecriture = useMutation({
    mutationFn: (corps: Record<string, unknown>) => justifierDemande(compteId, corps),
    onSuccess: () => {
      definirSucces(true);
      definirDemande("");
      definirMontant("");
      definirDate("");
      void queryClient.invalidateQueries({ queryKey: ["justifications-banque", compteId] });
      void queryClient.invalidateQueries({ queryKey: ["situation-special", compteId] });
    },
    onError: (e) => definirEchec(texteErreur(e, t("erreur.inconnue"))),
  });

  function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    definirEchec(null);
    definirSucces(false);
    if (ecriture.isPending) return;
    const r = construireJustification(demande, montant, date, i18n.language);
    if (!r.ok) return definirFautes(r.fautes);
    definirFautes([]);
    ecriture.mutate(r.corps);
  }

  return (
    <form className="special__formulaire" onSubmit={soumettre} noValidate aria-label={t("special.justifier.titre")}>
      <h3>{t("special.justifier.titre")}</h3>
      {succes && <Message variante="succes">{t("special.justifier.ok")}</Message>}
      {echec && <Message variante="danger">{echec}</Message>}
      {demandes.error && <Message variante="danger">{texteErreur(demandes.error, t("special.justifier.erreur_demandes"))}</Message>}
      {fautes.length > 0 && (
        <Message variante="attention">
          <ul>
            {fautes.map((f) => (
              <li key={f.cle}>{t(f.cle)}</li>
            ))}
          </ul>
        </Message>
      )}
      <Selecteur
        etiquette={t("special.justifier.demande")}
        valeur={demande}
        options={[{ valeur: "", libelle: t("special.justifier.choisir") }, ...(demandes.data ?? []).map((d) => ({ valeur: d.id, libelle: `${d.numero} · ${t(`special.justifier.statut.${d.statut}`)} · ${d.montant_total}` }))]}
        onChange={definirDemande}
      />
      <Champ etiquette={t("special.justifier.montant")} inputMode="decimal" autoComplete="off" value={montant} onChange={(e) => definirMontant(e.target.value)} />
      <Champ etiquette={t("special.justifier.date")} type="date" value={date} onChange={(e) => definirDate(e.target.value)} />
      <Bouton type="submit" chargement={ecriture.isPending}>
        {t("special.justifier.envoyer")}
      </Bouton>
    </form>
  );
}
