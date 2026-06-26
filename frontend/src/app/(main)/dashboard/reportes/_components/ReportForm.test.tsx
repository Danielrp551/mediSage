import { beforeEach, expect, it, vi } from "vitest";

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { generateReport } from "@/actions/dashboards.actions";
import { renderWithFluent } from "@/test/render";
import { describeRF } from "@/test/traceability";

import { ReportForm } from "./ReportForm";

// La action es un Server Action (importa "server-only"); se reemplaza por un mock para
// probar el componente sin backend. Espejo de mockear el cliente HTTP en el backend.
vi.mock("@/actions/dashboards.actions", () => ({
  generateReport: vi.fn(),
}));

const branches = [{ id: "b1", name: "Sede Centro" }];

describeRF("RF-E07-27", "Formulario de generacion de reportes (HU27)", () => {
  beforeEach(() => {
    vi.mocked(generateReport).mockReset();
  });

  it("renderiza el formulario con secciones, formatos y la accion de descarga", () => {
    renderWithFluent(<ReportForm branches={branches} />);

    expect(screen.getByRole("heading", { name: "Reportes" })).toBeInTheDocument();
    for (const label of [
      "KPIs",
      "Embudo de conversión",
      "Distribución de citas",
      "Evolución de leads",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByRole("radio", { name: "PDF" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Excel" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generar y descargar/i })).toBeInTheDocument();
  });

  it("genera el reporte y confirma el exito", async () => {
    vi.mocked(generateReport).mockResolvedValue({
      ok: true,
      data: { filename: "reporte.pdf", mime: "application/pdf", base64: "AAAA" },
    });
    renderWithFluent(<ReportForm branches={branches} />);

    const button = screen.getByRole("button", { name: /generar y descargar/i });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);

    expect(generateReport).toHaveBeenCalledTimes(1);
    expect(generateReport).toHaveBeenCalledWith(
      expect.objectContaining({
        format: "pdf",
        branch_id: null,
        sections: ["kpis", "funnel", "distribution", "evolution"],
      }),
    );
    expect(await screen.findByText("Reporte generado.")).toBeInTheDocument();
  });

  it("muestra el error cuando la generacion falla", async () => {
    vi.mocked(generateReport).mockResolvedValue({
      ok: false,
      error: "No se pudo generar el reporte.",
    });
    renderWithFluent(<ReportForm branches={branches} />);

    const button = screen.getByRole("button", { name: /generar y descargar/i });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);

    expect(await screen.findByText("No se pudo generar el reporte.")).toBeInTheDocument();
  });
});
