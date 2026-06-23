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
| [ADR-002](ADR-002-doctor-entity-extends-user.md) | Doctor como entidad 1:1 con User, no columnas en User | Accepted | 2026-05-28 |
| [ADR-003](ADR-003-person-with-separated-lifecycle-statuses.md) | Person + estados lead/customer separados en tablas hijas | Accepted (act. 2026-05-31) | 2026-05-28 |
| [ADR-004](ADR-004-conversation-channel-account.md) | Conversation + ChannelAccount como par central de mensajería multicanal | Accepted (act. 2026-06-02, 2026-06-03) | 2026-05-28 |
| [ADR-005](ADR-005-agnostic-bot-engine.md) | Motor del bot agnóstico — entidades separadas de la implementación del engine | Accepted (act. 2026-06-04) | 2026-05-28 |
| [ADR-006](ADR-006-hybrid-calendar-slots.md) | Slots de calendario híbridos — solo Appointment persiste; disponibilidad on-the-fly | Accepted (act. 2026-05-29) | 2026-05-28 |
| [ADR-007](ADR-007-doctor-availability-concrete-blocks.md) | Disponibilidad del doctor como bloques concretos por fecha (no patrón recurrente) | Accepted | 2026-05-29 |
| [ADR-008](ADR-008-configurable-status-transition-matrix.md) | Matriz de transiciones de estado configurable (lead/customer) | Accepted | 2026-05-31 |
| [ADR-009](ADR-009-forward-fk-deferred-cross-module.md) | FKs forward a módulos futuros diferidas (columna ahora, constraint después) | Accepted (act. 2026-06-08: cerrado por marketing) | 2026-05-31 |
| [ADR-010](ADR-010-runtime-secret-resolution.md) | Resolución de secretos por-cuenta vía Secret Manager SDK en runtime (cacheado) | Accepted | 2026-06-02 |
| [ADR-011](ADR-011-firestore-message-stream-cqrs.md) | Stream de mensajes en Firestore (CQRS read-model) — control plane Postgres + outbox + Custom Tokens | Accepted | 2026-06-03 |
| [ADR-012](ADR-012-cloud-tasks-bot-dispatch.md) | Despacho del turno del bot vía Cloud Tasks (no síncrono, no BackgroundTasks) | Accepted | 2026-06-04 |
| [ADR-013](ADR-013-marketing-campaign-status-and-atomic-apply.md) | marketing — status de campaña enum fijo (no matriz ADR-008) + aplicación de promoción atómica cross-módulo | Accepted | 2026-06-08 |
| [ADR-014](ADR-014-external-calendar-integration.md) | Calendario externo — adaptador agnóstico + proveedores nativos (Google/Microsoft) + Fase 1 = lectura informativa a nivel clínica | Proposed | 2026-06-22 |
| _(pendiente)_ | JWT en cookie httpOnly (no localStorage)     | —      | —     |
| _(pendiente)_ | Permisos viajan en el access token           | —      | —     |
| _(pendiente)_ | Arquitectura backend en 5 capas              | —      | —     |
| _(pendiente)_ | Refresh token con rotación por familia       | —      | —     |
| _(pendiente)_ | RBAC dual: permisos directos + por rol       | —      | —     |
| _(pendiente)_ | Server Actions vs cliente HTTP en frontend   | —      | —     |
| _(pendiente)_ | URL state con nuqs para listados             | —      | —     |

## Referencias

- [Documenting Architecture Decisions — Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [ADR GitHub Organization](https://adr.github.io/)
