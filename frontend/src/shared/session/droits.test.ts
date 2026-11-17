import { projet } from "../../test/serveur";
import { OPERATIONS, peut, projetParId } from "./droits";
import type { Moi } from "./types";

describe("droits (affichage seulement)", () => {
  it("montre une action seulement si l'opération est accordée sur le projet", () => {
    const p = projet("P1", ["consulter", "saisir"]);
    expect(peut(p, "saisir")).toBe(true);
    expect(peut(p, "valider")).toBe(false);
    expect(peut(undefined, "consulter")).toBe(false);
  });

  it("une habilitation limitée à un site ne donne pas l'opération sur le projet", () => {
    const p = { ...projet("P1", []), operations_par_site: { DJI: ["exporter" as const] } };
    expect(peut(p, "exporter")).toBe(false);
  });

  it("retrouve un projet par son identifiant, sans planter sans session", () => {
    const moi = { projets: [projet("P1"), projet("P2")] } as unknown as Moi;
    expect(projetParId(moi, "id-P2")?.code).toBe("P2");
    expect(projetParId(moi, "inconnu")).toBeUndefined();
    expect(projetParId(null, "id-P2")).toBeUndefined();
  });

  it("présente les huit opérations dans un ordre fixe", () => {
    expect(OPERATIONS).toHaveLength(8);
    expect(new Set(OPERATIONS).size).toBe(8);
  });
});
