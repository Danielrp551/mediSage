/**
 * Trazabilidad prueba a requisito (Anexo G.8.3), espejo de los markers `rf`/`rnf`
 * del backend (backend/pyproject.toml). Cada caso de prueba del front-end se asocia
 * de forma explicita a su Requerimiento Funcional o No Funcional mediante estos
 * envoltorios de `describe`. El identificador queda en el nombre del bloque, de modo
 * que la matriz de trazabilidad RF/RNF a prueba se puede extraer del reporte.
 *
 * El catalogo es cerrado: el tipo de union obliga a usar un identificador valido.
 * Un id fuera del catalogo no compila, lo que cumple en TypeScript el mismo rol que
 * `--strict-markers` cumple en pytest (un marcador no declarado rompe el build).
 */
import { describe } from "vitest";

/** Requerimientos Funcionales cubiertos por las pruebas del front-end. */
export type RequisitoFuncional =
  // Epica E07 - Dashboard y Reportes
  | "RF-E07-26" // HU26: visualizacion de graficos de conversiones y conversaciones con filtros
  | "RF-E07-27"; // HU27: generacion de reportes de conversiones y conversaciones (PDF y Excel)

/** Requerimientos No Funcionales cubiertos por las pruebas del front-end. */
export type RequisitoNoFuncional =
  | "RNF-04" // Cobertura de pruebas automatizadas
  | "RNF-05"; // Rendimiento del panel de resultados

/**
 * Agrupa pruebas trazadas a un Requerimiento Funcional.
 * Equivalente a `pytestmark = pytest.mark.rf("RF-...")` del backend.
 */
export function describeRF(id: RequisitoFuncional, titulo: string, fn: () => void): void {
  describe(`[${id}] ${titulo}`, fn);
}

/**
 * Agrupa pruebas trazadas a un Requerimiento No Funcional.
 * Equivalente a `pytest.mark.rnf("RNF-...")` del backend (declarado y aqui estrenado).
 */
export function describeRNF(id: RequisitoNoFuncional, titulo: string, fn: () => void): void {
  describe(`[${id}] ${titulo}`, fn);
}
