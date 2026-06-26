import { expect, it } from "vitest";

import { screen } from "@testing-library/react";

import { makeKpiSummary } from "@/test/fixtures";
import { renderWithFluent } from "@/test/render";
import { describeRF } from "@/test/traceability";

import { BotMiniPanel } from "./BotMiniPanel";

describeRF("RF-E07-26", "Mini panel del chatbot (componente)", () => {
  it("muestra las cifras del aporte del bot", () => {
    renderWithFluent(
      <BotMiniPanel summary={makeKpiSummary()} isLoading={false} isError={false} />,
    );

    expect(screen.getByText("Atención del bot")).toBeInTheDocument();
    expect(screen.getByText("Conversaciones")).toBeInTheDocument();
    expect(screen.getByText("Turnos")).toBeInTheDocument();
    expect(screen.getByText("Costo estimado")).toBeInTheDocument();
    expect(screen.getByText("140")).toBeInTheDocument(); // conversaciones del bot
    expect(screen.getByText("540")).toBeInTheDocument(); // turnos del bot
    expect(screen.getByText("$ 4.12")).toBeInTheDocument(); // costo estimado
    expect(screen.getByText("70 %")).toBeInTheDocument(); // aporte del bot (140/200)
  });

  it("muestra un aviso cuando la informacion del bot no esta disponible", () => {
    renderWithFluent(<BotMiniPanel summary={undefined} isLoading={false} isError={true} />);

    expect(
      screen.getByText("Información del bot no disponible por ahora."),
    ).toBeInTheDocument();
  });
});
