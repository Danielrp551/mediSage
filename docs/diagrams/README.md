# Diagramas

Diagramas vivos del sistema en **PlantUML** (`.puml`). Source de verdad de la arquitectura.

## Por qué PlantUML

- **Estándar UML real** — class, sequence, activity, state, use case, deployment, component. No es un DSL ad-hoc.
- **Text-based** → versionable en git, diffeable en PR, editable sin licencias.
- **Render universal** — extensión VS Code, IntelliJ, servidor público, CLI, GitHub action.
- **Generación automática para Python** vía `pyreverse` (pylint) — el class diagram del backend se regenera desde el código, no se mantiene a mano.

## Estructura

```
docs/diagrams/
├── README.md                   ← este archivo
├── _template-class.puml        ← copia para nuevos class diagrams
├── _template-sequence.puml     ← copia para nuevos sequence diagrams
├── _template-er.puml           ← copia para nuevos ER diagrams
├── class-backend-admin.puml    ← class diagram módulo admin (User/Role/Permission)
├── ...                         ← un .puml por diagrama
└── out/                        ← (gitignored) PNG/SVG generados
```

## Convención de nombres

`<tipo>-<area>[-<subarea>].puml`

| Tipo | Para qué |
|---|---|
| `class-<modulo>` | Class diagram UML del módulo |
| `er-<modulo>` | Entity-relationship del esquema |
| `sequence-<flujo>` | Interacción entre actores en el tiempo |
| `activity-<proceso>` | Flujo con decisiones (ramas, loops) |
| `state-<entidad>` | Estados y transiciones |
| `component-<area>` | Componentes desplegables y conexiones |
| `usecase-<actor>` | Casos de uso |
| `deployment-<entorno>` | Topología de infraestructura |

## Índice

### Template (`admin` y cross-cutting)

| Archivo | Cubre | Estado |
|---|---|---|
| [`class-backend-admin.puml`](class-backend-admin.puml) | `User/Role/Permission` + mixins + `BaseRepository` + services | ✅ |
| [`er-admin.puml`](er-admin.puml) | Tablas `user`, `role`, `permission` + 3 tablas de asociación | ✅ |
| `class-frontend-state.puml` | AuthProvider, hooks, providers | _pendiente_ |
| `sequence-auth-login.puml` | Login → JWT + cookie | _pendiente_ |
| `sequence-auth-refresh.puml` | Rotación de refresh + revocación por `family` | _pendiente_ |
| `activity-permission-check.puml` | `RequirePermission()` → claims → 403 | _pendiente_ |
| `component-system.puml` | Browser ↔ Next.js ↔ FastAPI ↔ Postgres | _pendiente_ |

### Medisage — módulos de dominio

Cada módulo tiene su ER (relacional) y su Class (modelos + repos + services). Las fichas markdown viven en [`docs/modules/`](../modules/) y los ADRs en [`docs/decisions/`](../decisions/).

| Módulo | ER | Class | Ficha | ADR |
|---|---|---|---|---|
| `catalog` (Vertical → Service → Product) | [er-catalog.puml](er-catalog.puml) ✅ | [class-backend-catalog.puml](class-backend-catalog.puml) ✅ | [catalog/](../modules/catalog/README.md) (overview + [backend](../modules/catalog/backend.md) + [ui](../modules/catalog/ui.md) + [frontend](../modules/catalog/frontend.md)) | — |
| `clinic` (Branch / Office / horarios) | [er-clinic.puml](er-clinic.puml) ✅ | [class-backend-clinic.puml](class-backend-clinic.puml) ✅ | [clinic/](../modules/clinic/README.md) (overview + [backend](../modules/clinic/backend.md) + [ui](../modules/clinic/ui.md) + [frontend](../modules/clinic/frontend.md)) | — |
| `staff` (Doctor 1:1 User + disponibilidad) | [er-staff.puml](er-staff.puml) ✅ | [class-backend-staff.puml](class-backend-staff.puml) ✅ | [staff/](../modules/staff/README.md) (overview + [backend](../modules/staff/backend.md) + [ui](../modules/staff/ui.md) + [frontend](../modules/staff/frontend.md)) | [ADR-002](../decisions/ADR-002-doctor-entity-extends-user.md), [ADR-007](../decisions/ADR-007-doctor-availability-concrete-blocks.md) |
| `crm` (Person + estados separados) | [er-crm.puml](er-crm.puml) ✅ | [class-backend-crm.puml](class-backend-crm.puml) ✅ | [crm/](../modules/crm/README.md) (overview + [backend](../modules/crm/backend.md) + [ui](../modules/crm/ui.md) + [frontend](../modules/crm/frontend.md)) | [ADR-003](../decisions/ADR-003-person-with-separated-lifecycle-statuses.md), [ADR-008](../decisions/ADR-008-configurable-status-transition-matrix.md), [ADR-009](../decisions/ADR-009-forward-fk-deferred-cross-module.md) |
| `conversations` (ChannelAccount + multicanal) | [er-conversations.puml](er-conversations.puml) ✅ | [class-backend-conversations.puml](class-backend-conversations.puml) ✅ | [conversations/](../modules/conversations/README.md) (overview + [backend](../modules/conversations/backend.md) + [ui](../modules/conversations/ui.md) + [frontend](../modules/conversations/frontend.md)) | [ADR-004](../decisions/ADR-004-conversation-channel-account.md), [ADR-010](../decisions/ADR-010-runtime-secret-resolution.md) |
| `bots` (motor agnóstico) | [er-bots.puml](er-bots.puml) ✅ | [class-backend-bots.puml](class-backend-bots.puml) ✅ | [bots.md](../modules/bots.md) | [ADR-005](../decisions/ADR-005-agnostic-bot-engine.md) |
| `scheduling` (Appointment + slots híbridos) | [er-scheduling.puml](er-scheduling.puml) ✅ | [class-backend-scheduling.puml](class-backend-scheduling.puml) ✅ | [scheduling.md](../modules/scheduling.md) | [ADR-006](../decisions/ADR-006-hybrid-calendar-slots.md) |
| `marketing` (Campaign + Promotion + Usage) | [er-marketing.puml](er-marketing.puml) ✅ | [class-backend-marketing.puml](class-backend-marketing.puml) ✅ | [marketing.md](../modules/marketing.md) | — |

Doc consolidado: [`docs/modules/_seed-and-roles.md`](../modules/_seed-and-roles.md) — 117 permisos + 4 roles seed + patches a `seed.py`.

## Cómo renderizar

### Opción A — VS Code (recomendado para edición)

1. Instala la extensión **PlantUML** de jebbs (`jebbs.plantuml`).
2. Configura `plantuml.server` o usa el servidor público:
   ```json
   "plantuml.render": "PlantUMLServer",
   "plantuml.server": "https://www.plantuml.com/plantuml"
   ```
3. Abre el `.puml` y presiona `Alt+D` para preview en vivo.

> ⚠️ El servidor público envía el contenido del diagrama a `plantuml.com`. Para diagramas con info sensible, usa la opción C (PlantUML local).

### Opción B — Servidor público (cero instalación)

Copia el contenido del `.puml` en [planttext.com](https://www.planttext.com/) o [plantuml.com/plantuml](https://www.plantuml.com/plantuml/uml/).

### Opción C — PlantUML JAR local (CI, builds reproducibles)

1. Descarga `plantuml.jar` desde [plantuml.com/download](https://plantuml.com/download).
2. Coloca el JAR en `tools/plantuml.jar` (gitignored).
3. Genera PNG/SVG:
   ```bash
   java -jar tools/plantuml.jar -tsvg docs/diagrams/class-backend-admin.puml -o out/
   ```

Requiere Java (ya disponible en el entorno) y opcionalmente Graphviz (`dot`) para layouts complejos.

## Generación automática desde código (backend)

El class diagram del backend Python se puede regenerar desde el código con `pyreverse` (parte de `pylint`). **No agregamos `pylint` a las dependencias por defecto** — se ejecuta on-demand:

```bash
cd backend
uvx --from pylint pyreverse \
    -o puml \
    -p admin \
    --output-directory ../docs/diagrams/ \
    app/modules/admin
```

Esto genera `classes_admin.puml` y `packages_admin.puml`. Revísalos, renombra al estilo `class-backend-admin-generated.puml` y compara con la versión manual.

**Cuándo usar el generado vs manual**:

| Caso | Recomendación |
|---|---|
| Solo quieres "snapshot" de cómo se ve el módulo hoy | Usa `pyreverse` directo |
| Necesitas mostrar relaciones de dominio (M:N, agregados, decisiones de diseño) | Edita un `.puml` manual basado en el generado |

## Reglas

1. **Un diagrama, un concepto.** Si no entra en una pantalla, divide.
2. **Encabezado obligatorio** en cada `.puml`:
   ```plantuml
   @startuml class-backend-admin
   ' Propósito: <una línea>
   ' Última actualización: YYYY-MM-DD
   ' Código de referencia: backend/app/modules/admin/
   ```
3. **Sincroniza con el código** en el mismo PR. Si tocas modelos, actualiza el diagrama.
4. **Sin info sensible.** Nada de credenciales, IPs internas, nombres de clientes.
5. **Salidas a `out/`** (gitignored) — solo `.puml` se versiona.

## Linter mental para PRs

- [ ] ¿El `.puml` empieza con `@startuml <nombre>` y termina con `@enduml`?
- [ ] ¿Comentario con propósito + fecha + ruta del código?
- [ ] ¿Las clases del diagrama existen efectivamente en el código?
- [ ] ¿Aparece en el índice de este README?
