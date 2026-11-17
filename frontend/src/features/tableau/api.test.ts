import { aujourdhui, dateIsoValide } from "./api";

describe("dates du tableau de bord", () => {
  it("accepte une vraie date, bissextile comprise", () => {
    expect(dateIsoValide("2026-06-30")).toBe(true);
    expect(dateIsoValide("2028-02-29")).toBe(true);
  });

  it("refuse ce qui n'est pas une date, même au bon format", () => {
    for (const mauvais of ["2026-02-31", "2027-02-29", "2026-13-01", "2026-00-10", "pas-une-date", "2026-6-30", "", "2026-06-30T00:00", undefined, 42, null]) {
      expect(dateIsoValide(mauvais), String(mauvais)).toBe(false);
    }
  });

  it("écrit la date du jour dans le fuseau local, pas en UTC", () => {
    expect(aujourdhui(new Date(2026, 10, 17, 23, 59))).toBe("2026-11-17");
    expect(aujourdhui(new Date(2026, 0, 1, 0, 1))).toBe("2026-01-01");
  });

  it("reste juste dans un fuseau en avance sur UTC (Djibouti, Tokyo) : 1 h du matin n'est pas la veille", () => {
    const avant = process.env.TZ;
    try {
      process.env.TZ = "Asia/Tokyo"; // UTC+9 : à 1 h locale, il est encore la veille en UTC
      expect(aujourdhui(new Date(2026, 10, 17, 1, 0))).toBe("2026-11-17");
      expect(new Date(2026, 10, 17, 1, 0).toISOString().slice(0, 10)).toBe("2026-11-16"); // le piège
    } finally {
      if (avant === undefined) delete process.env.TZ;
      else process.env.TZ = avant;
    }
  });
});
