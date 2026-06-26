import { expect, it, vi } from "vitest";

import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { makeKpiSummary } from "@/test/fixtures";
import { renderWithFluent } from "@/test/render";
import { describeRF } from "@/test/traceability";

import { KpiCards } from "./KpiCards";

describeRF("RF-E07-26", "Tarjetas de indicadores KPI (componente)", () => {
  it("renderiza los seis indicadores con sus etiquetas y valores", () => {
    renderWithFluent(
      <KpiCards
        summary={makeKpiSummary()}
        isLoading={false}
        isRefetching={false}
        isError={false}
        onRetry={() => {}}
      />,
    );

    for (const label of [
      "Tasa de conversión",
      "Leads",
      "Citas",
      "Confirmadas",
      "Clientes",
      "Aporte bot",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }

    expect(screen.getByText("42.0 %")).toBeInTheDocument(); // conversion_rate 0.42
    expect(screen.getByText("70 %")).toBeInTheDocument(); // aporte bot: 140/200 = 0.7
    expect(screen.getByText("120")).toBeInTheDocument(); // leads
  });

  it("muestra el estado de error y permite reintentar", async () => {
    const onRetry = vi.fn();
    renderWithFluent(
      <KpiCards
        summary={undefined}
        isLoading={false}
        isRefetching={false}
        isError={true}
        onRetry={onRetry}
      />,
    );

    expect(screen.getByText("No se pudieron cargar los indicadores.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("no muestra valores mientras carga", () => {
    renderWithFluent(
      <KpiCards
        summary={undefined}
        isLoading={true}
        isRefetching={false}
        isError={false}
        onRetry={() => {}}
      />,
    );

    // Las etiquetas siguen presentes, pero no hay valores calculados todavia.
    expect(screen.getByText("Tasa de conversión")).toBeInTheDocument();
    expect(screen.queryByText("42.0 %")).toBeNull();
  });
});
