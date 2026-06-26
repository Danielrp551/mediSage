import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const dir = fileURLToPath(new URL(".", import.meta.url));
const stub = resolve(dir, "src/test/stub-empty.ts");

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": resolve(dir, "src"),
      // En pruebas, los modulos server-only/client-only se reemplazan por un stub inerte.
      "server-only": stub,
      "client-only": stub,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    css: false,
    // Fluent UI 9 y griffel a veces necesitan transformarse (CJS a ESM) dentro de Vitest.
    server: { deps: { inline: [/@fluentui/, /griffel/] } },
    coverage: {
      provider: "v8",
      reporter: ["text", "text-summary", "html"],
      reportsDirectory: "coverage",
      // Alcance: el modulo de Dashboards del front-end (RE 3.3 / Anexo G.10.2).
      include: ["src/app/**/dashboard/**/*.{ts,tsx}"],
      exclude: [
        "**/*.test.{ts,tsx}",
        "**/*.d.ts",
        "src/test/**",
        // Las paginas son Server Components asincronos (no se prueban con RTL).
        "**/page.tsx",
        "**/layout.tsx",
      ],
      // Umbral duro de cobertura (RNF-04, equivalente a --cov-fail-under del backend):
      // el run falla si la cobertura del modulo de Dashboards cae por debajo.
      thresholds: {
        statements: 80,
        lines: 80,
        branches: 70,
        functions: 55,
      },
    },
  },
});
