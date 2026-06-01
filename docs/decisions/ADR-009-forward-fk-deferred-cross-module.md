# ADR-009: FKs forward a módulos futuros diferidas ("columna ahora, constraint después")

> **Status**: Accepted
> **Date**: 2026-05-31
> **Deciders**: @daniel, @marco
> **Relacionado**: aplica primero en `crm` (ADR-003); patrón reusable por cualquier módulo que referencie a otro construido más tarde.

## Context

Los módulos de dominio de medisage se construyen en un **orden de dependencias** (catalog → clinic → staff → **crm** → conversations → bots → scheduling → marketing). Inevitablemente, un módulo temprano necesita **referenciar entidades de módulos que aún no existen**.

El caso concreto que fuerza la decisión es `crm` (#4), que se construye **antes** que `marketing`, `scheduling` y `conversations`, pero cuyo modelo (confirmado por el usuario como "completo, con todas las entidades y FKs que necesitamos, para no tener problemas") incluye tres referencias hacia adelante:

| Columna | Tabla(s) | Apunta a | Módulo dueño (futuro) |
|---|---|---|---|
| `source_campaign_id` | `person_lead_status`, `lead_status_history` | `campaign` | `marketing` |
| `related_appointment_id` | `lead_activity` | `appointment` | `scheduling` |
| `related_conversation_id` | `lead_activity` | `conversation` | `conversations` |

El problema es **físico**, no de diseño: la tabla destino **no existe** cuando corre la migración de `crm`. Por lo tanto:
- Una **FK constraint** real (`REFERENCES campaign(id)`) en la migración `0011+` **falla al arrancar el contenedor** (la tabla `campaign` no existe) → el deploy de qa muere.
- Un **`ForeignKey(...)` / `relationship()`** en el ORM hacia una clase no mapeada **rompe la configuración del mapper** de SQLAlchemy al importar.

Necesitamos modelar la referencia (el usuario quiere el modelo completo hoy) sin romper el deploy ni acoplar el orden de construcción.

## Decision

**La columna referenciante existe desde ya como `varchar(36)` nullable + índice, SIN FK constraint en BD y SIN `ForeignKey`/`relationship()` en el ORM. La FK constraint real (y el `relationship` ORM, si se quiere) los agrega de forma ADITIVA la migración del módulo DUEÑO cuando crea su tabla.**

- En el ORM: solo `mapped_column(String(36), nullable=True, index=True)`. **Nunca** `ForeignKey("campaign.id")` ni `relationship(Campaign)` mientras `Campaign` no esté mapeada.
- En la migración del módulo consumidor (`crm`): la columna se crea como `VARCHAR(36)` + índice, **sin `REFERENCES`**.
- En la migración del módulo dueño (cuando se construya `marketing`/`scheduling`/`conversations`): un `ALTER TABLE <tabla_consumidora> ADD CONSTRAINT <fk> FOREIGN KEY (<col>) REFERENCES <tabla_nueva>(id)` — cambio **aditivo**, dejado como **TODO documentado** tanto en la ficha del consumidor como en el overview del módulo dueño.
- La "referencia" es real conceptualmente (la columna guarda el id correcto y se documenta como FK lógica); lo único que se difiere es **cuándo** se materializa la constraint. No se inventan ids ni semántica.

Este es el **patrón canónico** para cualquier referencia forward en el repo; cuando vuelva a aparecer (p.ej. `conversations` referenciando algo de `bots`), se aplica igual.

## Alternatives Considered

### Opción A — Columna ahora, FK constraint aditiva después (Aceptada)
- Ver Decision. Modelo completo y desplegable hoy; la FK se vuelve real sin migrar datos.

### Opción B — Crear tablas stub (`campaign`/`appointment`/`conversation`) dentro de `crm`
- **Pros**: permite poner la FK real ya.
- **Cons**: **rompe la propiedad de módulo** (cada tabla es dueña de su módulo). Cuando se construya el módulo real, su migración haría `CREATE TABLE campaign` y **chocaría** con la tabla stub existente → conflicto de ownership y de migración, obligando a una migración de datos y a reconciliar el esquema stub vs el real.
- **Rechazada porque**: introduce exactamente los problemas que el usuario quería evitar ("para no tener problemas"), solo que más tarde y peores.

### Opción C — Omitir las columnas hasta que exista el módulo dueño
- **Pros**: sin columnas "huérfanas"; el módulo dueño agrega columna + FK juntas.
- **Cons**: el modelo de `crm` no quedaría completo hoy (el timeline no podría referenciar cita/conversación, el lead no guardaría su campaña de origen) — contra el deseo explícito del usuario de tener el modelo completo. Y de todos modos requeriría una migración por consumidor más adelante.
- **Rechazada porque**: el usuario pidió el modelo completo ya; diferir solo la constraint (Opción A) lo logra sin el costo.

## Consequences

### Positivas
- **Modelo completo y desplegable hoy**: `crm` arranca con todas sus columnas; nada se posterga salvo la constraint física.
- **Se vuelve FK real de forma aditiva**: sin migración de datos, sin reescribir el esquema del consumidor.
- **Desacopla el orden de construcción**: un módulo temprano referencia a uno tardío sin esperar a que exista.
- **Patrón reusable y documentado**: la próxima referencia forward sigue la misma receta.

### Negativas / Trade-offs
- **Ventana sin integridad referencial a nivel BD** en esas 3 columnas hasta que se agregue la constraint. Mitigación: son **nullable** y las escriben **solo rutas controladas** (los services de `crm` hoy; los módulos dueños mañana, que además agregan la constraint en el mismo cambio). El riesgo de un id colgante es bajo y acotado al periodo intermódulo.
- **Hay que acordarse de agregar la constraint** al construir cada módulo dueño. Mitigación: **TODO explícito** en `crm/README.md` (sección "FKs forward") y un recordatorio en el overview de cada módulo dueño (`marketing`/`scheduling`/`conversations`).
- **El índice ya existe** (la columna se indexa desde el inicio), así que agregar la FK luego es barato.

### Lo que esto nos obliga a hacer
- `crm` crea `source_campaign_id` / `related_appointment_id` / `related_conversation_id` como `VARCHAR(36)` indexado sin `REFERENCES` (migraciones `0011`–`0013`), y en el ORM como `mapped_column(String(36), nullable=True, index=True)` sin `ForeignKey`/`relationship`.
- Al diseñar `marketing`, `scheduling` y `conversations`, su overview debe llevar el TODO "agregar `ALTER TABLE … ADD CONSTRAINT … FOREIGN KEY` a `<tabla>.<col>` de crm" (+ la FK simétrica `conversation.person_id` / `appointment.person_id` → `person`).

## Referencias

- [ADR-003](ADR-003-person-with-separated-lifecycle-statuses.md) — modelo de `crm` donde aplica primero.
- Fichas del módulo: [`crm/README.md`](../modules/crm/README.md) (sección "FKs forward a módulos futuros"), [`crm/backend.md`](../modules/crm/backend.md) (modelos y migraciones con las columnas sin `REFERENCES`).
- [ADR-008](ADR-008-configurable-status-transition-matrix.md) — la otra decisión nueva de `crm` (matriz de transiciones configurable).
