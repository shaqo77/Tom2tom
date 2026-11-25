import { appeler } from "../../shared/api/client";
import type { DocumentReference, DocumentRemplace, Integrite } from "./types";

const base = (projetId: string) => `/projets/${projetId}/documents/`;

export const lireDocuments = (projetId: string) => appeler<DocumentReference[]>(base(projetId));

export const deposerDocument = (projetId: string, formulaire: FormData) =>
  appeler<DocumentReference>(base(projetId), { methode: "POST", formulaire });

export const remplacerDocument = (projetId: string, documentId: string, formulaire: FormData) =>
  appeler<DocumentRemplace>(`${base(projetId)}${documentId}/remplacement/`, { methode: "POST", formulaire });

export const verifierIntegrite = (projetId: string, documentId: string) =>
  appeler<Integrite>(`${base(projetId)}${documentId}/integrite/`);

/** L'adresse du fichier, ouverte telle quelle : le serveur impose `attachment` et vérifie l'empreinte avant de servir. */
export const adresseContenu = (projetId: string, documentId: string) => `/api/v1${base(projetId)}${documentId}/contenu/`;
