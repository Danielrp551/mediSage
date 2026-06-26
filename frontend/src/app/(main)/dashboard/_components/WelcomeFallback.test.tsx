import { describe, expect, it } from "vitest";

import { screen } from "@testing-library/react";

import { renderWithFluent } from "@/test/render";

import { WelcomeFallback } from "./WelcomeFallback";

// Componente de infraestructura del panel (fallback para usuarios sin DASHBOARD_VIEW). No
// corresponde a una HU de visualizacion, por lo que va sin marcador RF (igual que los tests
// de infraestructura del backend).
describe("WelcomeFallback (fallback sin acceso al panel)", () => {
  it("muestra el saludo y solo los atajos permitidos por los permisos del usuario", () => {
    renderWithFluent(<WelcomeFallback permissions={["MY_APPOINTMENTS_READ"]} />);

    expect(screen.getByRole("heading", { name: "Bienvenido a Medisage" })).toBeInTheDocument();
    expect(screen.getByText("Mi agenda")).toBeInTheDocument();
    expect(screen.queryByText("Mis leads")).toBeNull();
  });

  it("no muestra atajos cuando el usuario no tiene permisos operativos", () => {
    renderWithFluent(<WelcomeFallback permissions={[]} />);

    expect(screen.getByRole("heading", { name: "Bienvenido a Medisage" })).toBeInTheDocument();
    expect(screen.queryByText("Mi agenda")).toBeNull();
  });
});
