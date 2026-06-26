import { expect, it } from "vitest";

import { screen } from "@testing-library/react";

import { makeTimeSeries } from "@/test/fixtures";
import { renderWithFluent } from "@/test/render";
import { describeRF } from "@/test/traceability";

import { LeadsLineChart } from "./LeadsLineChart";

describeRF("RF-E07-26", "Evolucion de leads (linea, componente)", () => {
  it("renderiza la grafica con su leyenda y los rotulos de los ejes", () => {
    renderWithFluent(<LeadsLineChart data={makeTimeSeries()} />);

    expect(screen.getByRole("img", { name: "Evolución de leads por día" })).toBeInTheDocument();
    // Cada serie aparece en la leyenda y en el title del trazo del SVG.
    expect(screen.getAllByText("Nuevos").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Ganados").length).toBeGreaterThan(0);
    // Eje X (fechas puras) y eje Y (maximo de la serie).
    expect(screen.getByText("01 jun")).toBeInTheDocument();
    expect(screen.getByText("03 jun")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
  });

  it("no renderiza nada cuando no hay puntos", () => {
    renderWithFluent(<LeadsLineChart data={{ series: [], points: [] }} />);

    expect(screen.queryByRole("img")).toBeNull();
  });
});
