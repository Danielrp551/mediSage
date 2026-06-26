import { beforeEach, expect, it, vi } from "vitest";

import { screen, waitFor } from "@testing-library/react";

import {
  getAppointmentsDistribution,
  getFunnel,
  getLeadsEvolution,
  getMeta,
  getSummary,
} from "@/actions/dashboards.actions";
import {
  makeDistributionSummary,
  makeFunnelSummary,
  makeKpiSummary,
  makeTimeSeries,
} from "@/test/fixtures";
import { renderWithProviders } from "@/test/render";
import { describeRF } from "@/test/traceability";
import type { DashboardFilter, DashboardMeta } from "@/types/dashboards.types";

import { DashboardClient } from "./DashboardClient";

// Las cinco lecturas del panel son Server Actions (importan "server-only"); se mockean para
// ejercitar el orquestador con TanStack Query sin backend real.
vi.mock("@/actions/dashboards.actions", () => ({
  getSummary: vi.fn(),
  getFunnel: vi.fn(),
  getAppointmentsDistribution: vi.fn(),
  getLeadsEvolution: vi.fn(),
  getMeta: vi.fn(),
}));

const filter: DashboardFilter = {
  date_from: "2026-06-01",
  date_to: "2026-06-30",
  branch_id: null,
  source: null,
  campaign_id: null,
};

const meta: DashboardMeta = {
  last_refreshed_at: null,
  lead_statuses: [],
  appointment_statuses: [],
  branches: [],
  sources: [],
};

describeRF("RF-E07-26", "Panel de conversion (orquestador, integracion)", () => {
  beforeEach(() => {
    vi.mocked(getSummary).mockResolvedValue(makeKpiSummary());
    vi.mocked(getFunnel).mockResolvedValue(makeFunnelSummary());
    vi.mocked(getAppointmentsDistribution).mockResolvedValue(makeDistributionSummary());
    vi.mocked(getLeadsEvolution).mockResolvedValue(makeTimeSeries());
    vi.mocked(getMeta).mockResolvedValue(meta);
  });

  it("renderiza el panel, sus widgets y carga los datos por las actions", async () => {
    renderWithProviders(<DashboardClient initialData={null} initialFilter={filter} />, {
      permissions: ["DASHBOARD_VIEW"],
    });

    expect(screen.getByRole("heading", { name: "Panel de conversión" })).toBeInTheDocument();
    expect(screen.getByText("Embudo de conversión")).toBeInTheDocument();
    expect(screen.getByText("Evolución de leads")).toBeInTheDocument();
    expect(screen.getByText("Distribución de citas")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Actualizar panel" })).toBeInTheDocument();

    // El dato llega por las actions mockeadas → el embudo renderiza su etapa.
    await waitFor(() => {
      expect(screen.getByText("Citas agendadas")).toBeInTheDocument();
    });
    expect(getSummary).toHaveBeenCalled();
    expect(getFunnel).toHaveBeenCalled();
    expect(getMeta).toHaveBeenCalled();
  });

  it("gatea el enlace a Reportes por el permiso REPORTS_EXPORT", async () => {
    const view = renderWithProviders(
      <DashboardClient initialData={null} initialFilter={filter} />,
      { permissions: ["DASHBOARD_VIEW"] },
    );
    expect(screen.queryByRole("link", { name: /reportes/i })).toBeNull();
    view.unmount();

    renderWithProviders(<DashboardClient initialData={null} initialFilter={filter} />, {
      permissions: ["DASHBOARD_VIEW", "REPORTS_EXPORT"],
    });
    expect(await screen.findByRole("link", { name: /reportes/i })).toBeInTheDocument();
  });
});
