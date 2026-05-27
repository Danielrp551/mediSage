# Architecture Decision Records (ADRs)

Registro de **decisiones técnicas significativas** del proyecto. Cada ADR captura el *por qué*, no el *qué* — el código ya muestra el qué.

## Cuándo escribir un ADR

Escribe un ADR cuando tomes una decisión que:

- Es **costosa de revertir** (elección de framework, BD, esquema de auth, arquitectura de capas).
- Afecta **APIs públicas** o contratos entre servicios.
- Es **no-obvia**: alguien podría llegar y preguntar "¿por qué no usamos X?".
- Vas a tener que **explicarla más de una vez**.

No escribas ADR para:

- Decisiones triviales (nombre de variable, formato de log).
- Prototipos desechables.
- Cambios que el git log + commit message ya documentan bien.

## Cómo escribir uno

1. Copia [`_template.md`](_template.md) con el siguiente número correlativo:
   ```bash
   cp docs/decisions/_template.md docs/decisions/ADR-NNN-titulo-corto.md
   ```
2. Rellena: **Status, Date, Context, Decision, Alternatives Considered, Consequences**.
3. Si el ADR **reemplaza** uno anterior, marca el viejo como `Superseded by ADR-XXXX` y referéncialo desde el nuevo.
4. Mantén actualizado el índice abajo.

## Ciclo de vida

```
PROPOSED → ACCEPTED → (SUPERSEDED | DEPRECATED)
```

- **PROPOSED**: en discusión, aún no implementado.
- **ACCEPTED**: vigente y aplicado en el código.
- **SUPERSEDED**: reemplazado por otro ADR. **No borrar** — la historia importa.
- **DEPRECATED**: ya no aplica pero no fue reemplazado (el problema desapareció).

## Índice

> Ordenado por número. Mantener al día.

| #    | Título                                       | Status | Fecha |
|------|----------------------------------------------|--------|-------|
| [ADR-001](ADR-001-multi-env-branching.md) | Multi-environment deployment via branch-driven workflows | Accepted | 2026-05-27 |
| _(pendiente)_ 002 | JWT en cookie httpOnly (no localStorage)     | —      | —     |
| _(pendiente)_ 003 | Permisos viajan en el access token           | —      | —     |
| _(pendiente)_ 004 | Arquitectura backend en 5 capas              | —      | —     |
| _(pendiente)_ 005 | Refresh token con rotación por familia       | —      | —     |
| _(pendiente)_ 006 | RBAC dual: permisos directos + por rol       | —      | —     |
| _(pendiente)_ 007 | Server Actions vs cliente HTTP en frontend   | —      | —     |
| _(pendiente)_ 008 | URL state con nuqs para listados             | —      | —     |

## Referencias

- [Documenting Architecture Decisions — Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [ADR GitHub Organization](https://adr.github.io/)
