import { describe, expect, it } from "vitest";

import { describeRF } from "@/test/traceability";
import {
  chatbotShare,
  formatDayMonth,
  formatInt,
  formatPct,
  formatPctInt,
  formatPctUncapped,
  formatUsd,
  sourceLabel,
} from "./format";

describeRF("RF-E07-26", "Formateadores del panel de conversion (HU26)", () => {
  describe("formatInt", () => {
    it("formatea enteros pequenos sin agrupacion", () => {
      expect(formatInt(0)).toBe("0");
      expect(formatInt(5)).toBe("5");
      expect(formatInt(204)).toBe("204");
    });

    it("agrupa miles con el motor de localizacion es-PE", () => {
      const esPE = new Intl.NumberFormat("es-PE", { maximumFractionDigits: 0 });
      expect(formatInt(1204)).toBe(esPE.format(1204));
      expect(formatInt(1_000_000)).toBe(esPE.format(1_000_000));
    });
  });

  describe("formatPct (acota a [0,1], un decimal)", () => {
    it("formatea una fraccion como porcentaje con un decimal", () => {
      expect(formatPct(0.5)).toBe("50.0 %");
      expect(formatPct(0.123)).toBe("12.3 %");
      expect(formatPct(0)).toBe("0.0 %");
      expect(formatPct(1)).toBe("100.0 %");
    });

    it("acota por arriba y por abajo ante ruido del backend", () => {
      expect(formatPct(1.5)).toBe("100.0 %");
      expect(formatPct(-0.1)).toBe("0.0 %");
    });
  });

  describe("formatPctInt (acota a [0,1], entero)", () => {
    it("redondea a entero", () => {
      expect(formatPctInt(0.5)).toBe("50 %");
      expect(formatPctInt(0.126)).toBe("13 %");
      expect(formatPctInt(0)).toBe("0 %");
    });

    it("acota a 100 por ciento", () => {
      expect(formatPctInt(1.4)).toBe("100 %");
      expect(formatPctInt(-1)).toBe("0 %");
    });
  });

  describe("formatPctUncapped (sin cota superior; embudo HU26)", () => {
    it("permite superar el 100 por ciento de forma legitima", () => {
      expect(formatPctUncapped(1.5)).toBe("150 %");
      expect(formatPctUncapped(2)).toBe("200 %");
    });

    it("acota por abajo y protege NaN e Infinity", () => {
      expect(formatPctUncapped(-0.1)).toBe("0 %");
      expect(formatPctUncapped(Number.NaN)).toBe("0 %");
      expect(formatPctUncapped(Number.POSITIVE_INFINITY)).toBe("0 %");
    });
  });

  describe("formatUsd (monto que viaja como string)", () => {
    it("formatea un monto valido con dos decimales", () => {
      expect(formatUsd("4.12")).toBe("$ 4.12");
      expect(formatUsd("4")).toBe("$ 4.00");
      expect(formatUsd("0")).toBe("$ 0.00");
    });

    it("usa cero ante un valor no numerico", () => {
      expect(formatUsd("abc")).toBe("$ 0.00");
      expect(formatUsd("")).toBe("$ 0.00");
    });
  });

  describe("chatbotShare (aporte del bot)", () => {
    it("calcula la fraccion de conversaciones del bot sobre el total", () => {
      expect(chatbotShare({ conversations_bot: 5, total_conversations: 10 })).toBe(0.5);
      expect(chatbotShare({ conversations_bot: 3, total_conversations: 4 })).toBe(0.75);
    });

    it("devuelve cero cuando no hay conversaciones (sin division por cero)", () => {
      expect(chatbotShare({ conversations_bot: 0, total_conversations: 0 })).toBe(0);
    });
  });

  describe("formatDayMonth (fecha pura, determinista entre husos)", () => {
    it("formatea YYYY-MM-DD a dia y mes en espanol", () => {
      expect(formatDayMonth("2026-06-01")).toBe("01 jun");
      expect(formatDayMonth("2026-01-15")).toBe("15 ene");
      expect(formatDayMonth("2026-12-31")).toBe("31 dic");
    });

    it("cae al numero de mes si esta fuera de rango", () => {
      expect(formatDayMonth("2026-13-09")).toBe("09 13");
    });
  });

  describe("sourceLabel (etiqueta comercial del origen)", () => {
    it("traduce los origenes conocidos", () => {
      expect(sourceLabel("bot")).toBe("Chatbot");
      expect(sourceLabel("advisor")).toBe("Asesor");
      expect(sourceLabel("admin")).toBe("Administrador");
    });

    it("devuelve el valor original si el origen es desconocido", () => {
      expect(sourceLabel("whatsapp")).toBe("whatsapp");
    });
  });
});
