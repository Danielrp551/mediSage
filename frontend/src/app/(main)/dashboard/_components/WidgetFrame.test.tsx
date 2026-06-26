import { expect, it, vi } from "vitest";

import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderWithFluent } from "@/test/render";
import { describeRF } from "@/test/traceability";

import { WidgetFrame } from "./WidgetFrame";

const base = {
  title: "Embudo de conversión",
  isLoading: false,
  isRefetching: false,
  isError: false,
  isEmpty: false,
  emptyLabel: "Sin datos en el rango.",
  onRetry: () => {},
  minHeight: 200,
};

describeRF("RF-E07-26", "Contenedor de widget del panel (estados aislados)", () => {
  it("muestra el titulo y el contenido en estado normal", () => {
    renderWithFluent(
      <WidgetFrame {...base}>
        <div>contenido del widget</div>
      </WidgetFrame>,
    );

    expect(screen.getByRole("heading", { name: "Embudo de conversión" })).toBeInTheDocument();
    expect(screen.getByText("contenido del widget")).toBeInTheDocument();
  });

  it("muestra el error con el titulo en minuscula y permite reintentar", async () => {
    const onRetry = vi.fn();
    renderWithFluent(
      <WidgetFrame {...base} isError={true} onRetry={onRetry}>
        <div>contenido del widget</div>
      </WidgetFrame>,
    );

    expect(screen.getByText("No se pudo cargar embudo de conversión.")).toBeInTheDocument();
    expect(screen.queryByText("contenido del widget")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("muestra el estado sin datos sin renderizar el contenido", () => {
    renderWithFluent(
      <WidgetFrame {...base} isEmpty={true}>
        <div>contenido del widget</div>
      </WidgetFrame>,
    );

    expect(screen.getByText("Sin datos en el rango.")).toBeInTheDocument();
    expect(screen.queryByText("contenido del widget")).toBeNull();
  });
});
