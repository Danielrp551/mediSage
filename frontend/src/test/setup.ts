/**
 * Setup global de las pruebas del front-end (Vitest + React Testing Library).
 * Espejo del `conftest.py` raiz del backend: prepara el entorno comun de pruebas.
 *  - Carga los matchers de jest-dom (toBeInTheDocument, etc.).
 *  - Limpia el DOM despues de cada prueba.
 *  - Provee stubs de APIs del navegador que jsdom no implementa y que usan Fluent UI 9
 *    y el formulario de reportes (matchMedia, URL.createObjectURL).
 */
import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

// Red de seguridad: un import accidental de "server-only" en el grafo no debe romper la prueba.
vi.mock("server-only", () => ({}));

// jsdom no implementa matchMedia; Fluent UI lo consulta para responsive/portales.
if (typeof window.matchMedia !== "function") {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }) as unknown as MediaQueryList,
  });
}

// jsdom no implementa createObjectURL/revokeObjectURL; el formulario de reportes descarga un blob.
if (typeof URL.createObjectURL !== "function") {
  URL.createObjectURL = vi.fn(() => "blob:mock") as unknown as typeof URL.createObjectURL;
}
if (typeof URL.revokeObjectURL !== "function") {
  URL.revokeObjectURL = vi.fn() as unknown as typeof URL.revokeObjectURL;
}

// jsdom no implementa ResizeObserver; Fluent UI (MessageBar, entre otros) lo usa para el reflow.
if (typeof globalThis.ResizeObserver === "undefined") {
  class ResizeObserverStub {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}
