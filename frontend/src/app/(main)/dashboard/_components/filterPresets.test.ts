import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { describeRF } from "@/test/traceability";
import {
  getDefaultDashboardFilter,
  isoDateLocal,
  rangeDays,
  resolveRange,
} from "./filterPresets";

describeRF("RF-E07-26", "Presets de rango de fechas del panel (HU26, filtros)", () => {
  describe("isoDateLocal", () => {
    it("formatea una fecha a YYYY-MM-DD con componentes locales", () => {
      // Mes 5 es junio (Date usa meses indexados en cero).
      expect(isoDateLocal(new Date(2026, 5, 1))).toBe("2026-06-01");
      expect(isoDateLocal(new Date(2026, 0, 9))).toBe("2026-01-09");
    });
  });

  describe("rangeDays (dias inclusive)", () => {
    it("cuenta de forma inclusiva entre dos fechas puras", () => {
      expect(rangeDays("2026-06-01", "2026-06-01")).toBe(1);
      expect(rangeDays("2026-06-01", "2026-06-30")).toBe(30);
      expect(rangeDays("2026-01-01", "2026-12-31")).toBe(365);
    });
  });

  describe("resolveRange y filtro por defecto (con reloj fijo)", () => {
    beforeEach(() => {
      vi.useFakeTimers();
      // 26 de junio de 2026, mediodia hora local.
      vi.setSystemTime(new Date(2026, 5, 26, 12, 0, 0));
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it("today devuelve el mismo dia en ambos extremos", () => {
      expect(resolveRange("today")).toEqual({ date_from: "2026-06-26", date_to: "2026-06-26" });
    });

    it("last7 abarca hoy y los seis dias previos", () => {
      expect(resolveRange("last7")).toEqual({ date_from: "2026-06-20", date_to: "2026-06-26" });
    });

    it("last30 abarca hoy y los veintinueve dias previos", () => {
      expect(resolveRange("last30")).toEqual({ date_from: "2026-05-28", date_to: "2026-06-26" });
    });

    it("thisMonth empieza el dia uno del mes", () => {
      expect(resolveRange("thisMonth")).toEqual({ date_from: "2026-06-01", date_to: "2026-06-26" });
    });

    it("getDefaultDashboardFilter usa los ultimos 30 dias y sin filtros adicionales", () => {
      expect(getDefaultDashboardFilter()).toEqual({
        date_from: "2026-05-28",
        date_to: "2026-06-26",
        branch_id: null,
        source: null,
        campaign_id: null,
      });
    });
  });
});
