import { expect, it } from "vitest";

import { screen } from "@testing-library/react";

import { makeFunnelSummary } from "@/test/fixtures";
import { renderWithFluent } from "@/test/render";
import { describeRF } from "@/test/traceability";

import { ConversionFunnel } from "./ConversionFunnel";

describeRF("RF-E07-26", "Embudo de conversion (componente)", () => {
  it("renderiza una barra por etapa con su etiqueta", () => {
    renderWithFluent(<ConversionFunnel data={makeFunnelSummary()} />);

    expect(screen.getByText("Conversaciones")).toBeInTheDocument();
    expect(screen.getByText("Leads")).toBeInTheDocument();
    expect(screen.getByText("Citas agendadas")).toBeInTheDocument();
    expect(screen.getAllByRole("img")).toHaveLength(3);
  });

  it("muestra el conteo de cada etapa y la tasa etapa a etapa", () => {
    renderWithFluent(<ConversionFunnel data={makeFunnelSummary()} />);

    expect(screen.getByText("200")).toBeInTheDocument(); // conteo de conversaciones
    expect(screen.getByText("60 %")).toBeInTheDocument(); // tasa leads vs etapa previa (0.6)
    expect(screen.getByText("25 %")).toBeInTheDocument(); // tasa citas vs etapa previa (0.25)
  });

  it("expone la descripcion accesible de la barra con la tasa", () => {
    renderWithFluent(<ConversionFunnel data={makeFunnelSummary()} />);

    const bars = screen.getAllByRole("img");
    expect(bars).toHaveLength(3);
    expect(bars[1]).toHaveAttribute("aria-label", "Leads: 120 (60 % vs etapa previa)");
  });
});
