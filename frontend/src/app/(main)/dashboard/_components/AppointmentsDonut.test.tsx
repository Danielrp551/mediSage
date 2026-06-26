import { expect, it } from "vitest";

import { screen } from "@testing-library/react";

import { makeDistributionSummary } from "@/test/fixtures";
import { renderWithFluent } from "@/test/render";
import { describeRF } from "@/test/traceability";

import { AppointmentsDonut } from "./AppointmentsDonut";

describeRF("RF-E07-26", "Distribucion de citas (donut, componente)", () => {
  it("renderiza el total y la leyenda por estado", () => {
    renderWithFluent(<AppointmentsDonut data={makeDistributionSummary()} />);

    expect(
      screen.getByRole("img", { name: "Distribución de citas por estado" }),
    ).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument(); // total en el centro del donut
    expect(screen.getByText("citas")).toBeInTheDocument();
    expect(screen.getByText("Confirmadas")).toBeInTheDocument();
    expect(screen.getByText("Canceladas")).toBeInTheDocument();
  });

  it("usa el singular cuando hay una sola cita", () => {
    renderWithFluent(
      <AppointmentsDonut
        data={{
          buckets: [{ code: "confirmed", label: "Confirmadas", color: null, count: 1 }],
          total: 1,
        }}
      />,
    );

    expect(screen.getByText("cita")).toBeInTheDocument();
  });

  it("no renderiza el donut cuando no hay citas", () => {
    renderWithFluent(<AppointmentsDonut data={{ buckets: [], total: 0 }} />);

    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.queryByText("citas")).toBeNull();
  });
});
