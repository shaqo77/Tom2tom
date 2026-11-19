import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { appliquerLangue } from "../../i18n";
import { violations } from "../../test/accessibilite";
import { Bouton } from "./Bouton";
import { Carte } from "./Carte";
import { Champ } from "./Champ";
import { Chargement } from "./Chargement";
import { Message } from "./Message";
import { Montant } from "./Montant";
import { Pastille } from "./Pastille";

beforeEach(async () => {
  await appliquerLangue("fr");
});

describe("Bouton", () => {
  it("est un vrai bouton, de type « button » par défaut (il ne soumet pas un formulaire par accident)", () => {
    render(<Bouton>Valider</Bouton>);
    expect(screen.getByRole("button", { name: "Valider" })).toHaveAttribute("type", "button");
  });

  it("réagit au clic et au clavier", async () => {
    const clic = vi.fn();
    render(<Bouton onClick={clic}>Valider</Bouton>);
    await userEvent.click(screen.getByRole("button"));
    await userEvent.tab();
    screen.getByRole("button").focus();
    await userEvent.keyboard("{Enter}");
    expect(clic).toHaveBeenCalledTimes(2);
  });

  it("en chargement : désactivé, annoncé comme occupé, et ne se déclenche plus", async () => {
    const clic = vi.fn();
    render(
      <Bouton chargement onClick={clic}>
        Valider
      </Bouton>,
    );
    const bouton = screen.getByRole("button");
    expect(bouton).toBeDisabled();
    expect(bouton).toHaveAttribute("aria-busy", "true");
    await userEvent.click(bouton);
    expect(clic).not.toHaveBeenCalled();
  });

  it("n'a aucune violation d'accessibilité", async () => {
    const { container } = render(<Bouton variante="danger">Supprimer</Bouton>);
    expect(await violations(container)).toEqual([]);
  });
});

describe("Champ", () => {
  it("relie l'étiquette, l'aide et l'erreur au champ pour les lecteurs d'écran", () => {
    render(<Champ etiquette="Identifiant" aide="Donné par l'administrateur" erreur="Obligatoire" />);
    const champ = screen.getByLabelText("Identifiant");
    expect(champ).toHaveAttribute("aria-invalid", "true");
    expect(champ).toHaveAccessibleDescription("Donné par l'administrateur Obligatoire");
  });

  it("sans erreur, le champ n'est pas déclaré invalide", () => {
    render(<Champ etiquette="Identifiant" />);
    expect(screen.getByLabelText("Identifiant")).not.toHaveAttribute("aria-invalid", "true");
  });

  it("annonce l'erreur dès qu'elle apparaît", () => {
    render(<Champ etiquette="Identifiant" erreur="Obligatoire" />);
    expect(screen.getByText("Obligatoire")).toHaveAttribute("role", "alert");
  });

  it("transmet ce que l'utilisateur tape", async () => {
    const changement = vi.fn();
    render(<Champ etiquette="Identifiant" onChange={changement} />);
    await userEvent.type(screen.getByLabelText("Identifiant"), "amina");
    expect(changement).toHaveBeenCalledTimes(5);
  });

  it("deux champs n'ont jamais le même identifiant", () => {
    render(
      <>
        <Champ etiquette="A" />
        <Champ etiquette="B" />
      </>,
    );
    expect(screen.getByLabelText("A").id).not.toBe(screen.getByLabelText("B").id);
  });

  it("n'a aucune violation d'accessibilité", async () => {
    const { container } = render(<Champ etiquette="Identifiant" aide="Aide" erreur="Erreur" />);
    expect(await violations(container)).toEqual([]);
  });
});

describe("Message", () => {
  it("annonce immédiatement une erreur ou une attention (role=alert), poliment le reste (role=status)", () => {
    render(
      <>
        <Message variante="danger">Raté</Message>
        <Message variante="attention">Prudence</Message>
        <Message variante="succes">Fait</Message>
        <Message variante="info">Note</Message>
      </>,
    );
    expect(screen.getAllByRole("alert")).toHaveLength(2);
    expect(screen.getAllByRole("status")).toHaveLength(2);
  });

  it("dit son type en toutes lettres : la couleur ne porte jamais seule le sens", () => {
    render(<Message variante="danger">L'écriture est déséquilibrée</Message>);
    expect(screen.getByRole("alert")).toHaveTextContent("Erreur");
  });

  it("n'a aucune violation d'accessibilité", async () => {
    const { container } = render(<Message variante="info">Note</Message>);
    expect(await violations(container)).toEqual([]);
  });
});

describe("Pastille, Carte, Chargement", () => {
  it("la pastille porte son sens par le texte", () => {
    render(<Pastille variante="alerte">En retard</Pastille>);
    expect(screen.getByText("En retard")).toBeInTheDocument();
  });

  it("la carte titrée est une région nommée", () => {
    render(<Carte titre="Budget">contenu</Carte>);
    expect(screen.getByRole("region", { name: "Budget" })).toBeInTheDocument();
  });

  it("le chargement est annoncé par son libellé traduit", async () => {
    render(<Chargement />);
    expect(screen.getByRole("status", { name: "Chargement en cours" })).toBeInTheDocument();
    await appliquerLangue("en");
  });

  it("aucune violation d'accessibilité", async () => {
    const { container } = render(
      <Carte titre="Budget">
        <Pastille variante="succes">Actif</Pastille>
        <Chargement />
      </Carte>,
    );
    expect(await violations(container)).toEqual([]);
  });
});

describe("Montant", () => {
  it("affiche le montant exact dans la langue, sans jamais passer par un nombre", () => {
    render(<Montant valeur="1234567.8" decimales={2} devise="DJF" />);
    expect(screen.getByText(/1\s234\s567,80/)).toBeInTheDocument();
    expect(screen.getByText("DJF")).toBeInTheDocument();
  });

  it("garde le sens gauche-à-droite des chiffres même en écriture droite-à-gauche", async () => {
    await appliquerLangue("pseudo");
    render(<Montant valeur="10.5" decimales={2} />);
    expect(screen.getByText(/10,50/).closest("[dir]")).toHaveAttribute("dir", "ltr");
  });

  it("marque un solde négatif autrement que par la seule couleur", () => {
    render(<Montant valeur="-250" decimales={0} />);
    const element = screen.getByText(/250/);
    expect(element.textContent).toContain("-");
    expect(element.closest(".montant")).toHaveClass("montant--negatif");
  });

  it("refuse d'afficher une valeur qui n'est pas un décimal plutôt que d'inventer un chiffre", () => {
    const silence = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => render(<Montant valeur="abc" decimales={2} />)).toThrow();
    silence.mockRestore();
  });
});
