import {
  MontantInvalide,
  enPourcentage,
  largeurJauge,
  additionner,
  comparer,
  estNul,
  formater,
  lireSaisie,
  soustraire,
} from "./montant";

const espaces = (texte: string) => texte.replace(/\s/g, " ");

describe("arithmétique exacte", () => {
  it("0,1 + 0,2 vaut exactement 0,3 (un nombre JavaScript donnerait 0,30000000000000004)", () => {
    expect(additionner("0.1", "0.2")).toBe("0.3");
  });

  it("garde tous les chiffres d'un grand montant à quatre décimales", () => {
    expect(additionner("12345678901234567890.1234", "0.0001")).toBe("12345678901234567890.1235");
  });

  it("soustrait, compare et reconnaît le zéro", () => {
    expect(soustraire("1000.00", "1000.00")).toBe("0");
    expect(estNul(soustraire("1000.00", "1000"))).toBe(true);
    expect(comparer("2.50", "2.5")).toBe(0);
    expect(comparer("1", "2")).toBeLessThan(0);
    expect(comparer("-1", "-2")).toBeGreaterThan(0);
  });

  it("additionne une liste vide à zéro", () => {
    expect(additionner()).toBe("0");
  });

  it("refuse tout ce qui n'est pas un décimal écrit en toutes lettres de chiffres", () => {
    for (const mauvais of ["", " ", "abc", "1e3", "NaN", "Infinity", "1,5", "--1", "1.", ".5x"]) {
      expect(() => additionner(mauvais, "1"), mauvais).toThrow(MontantInvalide);
    }
  });
});

describe("affichage", () => {
  it("groupe les milliers et pose la virgule selon la langue", () => {
    expect(espaces(formater("1250.5", "fr", 2))).toBe("1 250,50");
    expect(formater("1250.5", "en", 2)).toBe("1,250.50");
    expect(espaces(formater("1250", "fr", 0))).toBe("1 250");
  });

  it("arrondit comme le serveur : à la moitié, en s'éloignant de zéro", () => {
    expect(formater("2.345", "en", 2)).toBe("2.35");
    expect(formater("-2.345", "en", 2)).toBe("-2.35");
    expect(formater("2.344", "en", 2)).toBe("2.34");
  });

  it("n'affiche jamais un zéro négatif", () => {
    expect(formater("-0.004", "en", 2)).toBe("0.00");
  });

  it("garde la précision d'un très grand montant (pas de passage par Number)", () => {
    expect(formater("12345678901234567890.1234", "en", 4)).toBe("12,345,678,901,234,567,890.1234");
  });

  it("refuse une valeur qui n'est pas un décimal", () => {
    expect(() => formater("abc", "fr", 2)).toThrow(MontantInvalide);
  });
});

describe("saisie de l'utilisateur", () => {
  it("lit la virgule en français et le point en anglais, espaces ignorés", () => {
    expect(lireSaisie("1 250,50", "fr")).toBe("1250.50");
    expect(lireSaisie("1 250,50", "fr")).toBe("1250.50"); // espace insécable
    expect(lireSaisie("1,250.50", "en")).toBe("1250.50");
    expect(lireSaisie("-12,5", "fr")).toBe("-12.5");
    expect(lireSaisie("1250", "fr")).toBe("1250");
  });

  it("renvoie null au lieu de deviner quand le texte est ambigu ou invalide", () => {
    for (const mauvais of ["", "abc", "1,2,3", "12,5,", "1e3", "--5", "1.250,5.0"]) {
      expect(lireSaisie(mauvais, "fr"), mauvais).toBeNull();
    }
    expect(lireSaisie("12.5", "fr")).toBeNull(); // le point n'est pas la virgule française
  });
});

describe("taux en pourcentage", () => {
  it("écrit un rapport décimal exact en pourcentage, selon la langue", () => {
    expect(espaces(enPourcentage("0.6834", "fr", 1))).toBe("68,3 %");
    expect(enPourcentage("0.6834", "en", 1)).toBe("68.3%");
    expect(espaces(enPourcentage("1", "fr", 0))).toBe("100 %");
    expect(enPourcentage("0", "en", 1)).toBe("0.0%");
  });

  it("arrondit à la moitié en s'éloignant de zéro, sans l'erreur des flottants", () => {
    expect(enPourcentage("0.0005", "en", 0)).toBe("0%"); // 0,05 % → 0 %
    expect(enPourcentage("0.005", "en", 0)).toBe("1%"); // 0,5 % → 1 %
    expect(enPourcentage("1.005", "en", 1)).toBe("100.5%"); // un nombre flottant donnerait 100.49999
  });

  it("garde les dépassements : un taux au-dessus de 100 % se lit tel quel", () => {
    expect(enPourcentage("1.25", "en", 1)).toBe("125.0%");
  });

  it("refuse une valeur qui n'est pas un décimal", () => {
    expect(() => enPourcentage("abc", "fr", 1)).toThrow(MontantInvalide);
  });
});

describe("largeur d'une jauge", () => {
  it("donne la part remplie en pourcentage, bornée entre 0 et 100", () => {
    expect(largeurJauge("0.6834")).toBe("68.3");
    expect(largeurJauge("0")).toBe("0");
    expect(largeurJauge("1")).toBe("100");
  });

  it("un dépassement ou un taux négatif ne sort jamais de la jauge", () => {
    expect(largeurJauge("12.5")).toBe("100"); // 1 250 %
    expect(largeurJauge("-0.2")).toBe("0");
  });

  it("refuse une valeur qui n'est pas un décimal", () => {
    expect(() => largeurJauge("abc")).toThrow(MontantInvalide);
  });
});
