# Módulo `catalog`

> **Última actualización**: 2026-05-28
> **Propósito**: catálogo comercial de la clínica — qué ofrece, cómo se organiza y cómo se identifica para venta y agendamiento.
> **Path del código**: `backend/app/modules/catalog/` (backend) · `frontend/src/app/(main)/catalog/` (frontend).

> **Este documento es el overview**. Para el deep-dive ver:
> - 🔧 [`backend.md`](backend.md) — schemas Pydantic, API contracts, lógica.
> - 🎨 [`ui.md`](ui.md) — mockups, estados, componentes Fluent UI.
> - ⚛️ [`frontend.md`](frontend.md) — archivos Next.js, server actions, Zod, navegación.

## Resumen

La clínica de Medisage es **multi-vertical**: combina áreas como dermatología, estética, dental, médica general, etc. Este módulo modela ese catálogo en una jerarquía de tres niveles diseñada para soportar cualquier combinación sin tocar código.

```
Vertical (área de negocio)
   └─ Service (tipo de prestación)
         └─ Product (lo que efectivamente se vende y agenda)
```

Es la base sobre la que se asientan los módulos `scheduling` (las citas se agendan a un `Product`), `marketing` (las promociones aplican a `Product`) y `staff` (los doctores se asignan a `Vertical`).

## Entidades

| Entidad | Tabla | Propósito |
|---|---|---|
| `Vertical` | `vertical` | Área de negocio macro (Dermatología, Estética facial, Dental, Pediatría, ...) |
| `Service` | `service` | Tipo de prestación dentro de una vertical (Consulta, Limpieza profunda, Brackets, ...) |
| `Product` | `product` | Unidad vendible y agendable (HydraFacial 60 min, Plan brackets 18m, Consulta + medicamento) |

### `Vertical`

Área de negocio macro. Es el primer nivel de la jerarquía y la unidad sobre la que se reportan ventas, se asignan doctores y se segmentan campañas.

- `code: varchar(40)` `<<unique>>` — slug estable (`dermatologia`, `estetica_facial`). Lo usan los bots para clasificar leads.
- `name: varchar(120)` — nombre comercial (lo que ve el cliente).
- `description: varchar(500)` `<<nullable>>`.
- `color: varchar(20)` `<<nullable>>` — hex para badges en UI (`#FF6B6B`).
- `icon: varchar(60)` `<<nullable>>` — id de ícono de Fluent UI (`Sparkle24Regular`).
- `display_order: int` `default 0` — orden en menús / dashboards.
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

### `Service`

Tipo de prestación dentro de una vertical. Es la categoría intermedia que permite agrupar productos similares para reporting y UX.

- `vertical_id: varchar(36)` `<<FK→vertical>>`.
- `code: varchar(60)` — único por vertical (`(vertical_id, code)`). Ej: `consulta`, `limpieza_profunda`.
- `name: varchar(120)`.
- `description: varchar(500)` `<<nullable>>`.
- `display_order: int` `default 0`.
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

### `Product`

Lo que efectivamente se vende y se agenda. Es el grano del catálogo: una cita se reserva contra un `Product`, una promoción aplica a uno o varios `Product`, un reporte de ingresos suma por `Product`.

- `service_id: varchar(36)` `<<FK→service>>`.
- `vertical_id: varchar(36)` `<<FK→vertical>>` — denormalizado: se copia de la vertical del servicio padre al crear el producto y es inmutable (tanto `service_id` como el `vertical_id` del servicio lo son). Existe para que la UI del catálogo pueda filtrar/contar productos por vertical vía `ALLOWED_FIELDS` sin un join; `vertical_name` se sigue derivando. Tiene índice `ix_product_vertical_id`.
- `code: varchar(60)` — único por servicio (`(service_id, code)`).
- `name: varchar(160)`.
- `description: varchar(1000)` `<<nullable>>`.
- `base_price: numeric(10,2)` — precio de lista en moneda local. Promotions aplican descuento sobre éste.
- `currency: varchar(3)` `default 'PEN'` — ISO 4217; se centraliza por la clínica pero queda en la fila por si en el futuro se multinaliza.
- `duration_min: int` `<<nullable>>` — duración estimada de la atención. Usado por `scheduling` para reservar el slot correcto. `NULL` = no tiene duración fija (ej. plan de tratamiento).
- `requires_appointment: bool` `default true` — si es agendable. Hay productos que se venden sin cita (ej. paquetes de cremas).
- `is_package: bool` `default false` — paquete o tratamiento multi-sesión. (Decisión: por ahora no modelamos las sesiones de un paquete — se trackea con `LeadActivity`/`CustomerStatusHistory` en `crm`. Si crece, agregar `ProductSession` después.)
- `min_hours_to_cancel: int` `<<nullable>>` — horas mínimas de antelación para cancelar una cita de este producto. `NULL` = sin límite. Si está set, `scheduling.appointment.cancel` valida `(scheduled_for - now()) >= min_hours_to_cancel * 60 min` salvo permiso `APPOINTMENTS_CANCEL_OVERRIDE`. Agregado a raíz de la decisión del módulo `scheduling` ([ver](../scheduling/README.md)).
- Mixins: `PrimaryKey`, `Active`, `SoftDelete`, `Timestamp`.

## Endpoints (resumen)

Todos bajo `/api/v1/catalog/`. Detalle de request/response en [`backend.md`](backend.md#api-contracts).

| Método | Ruta | Permiso |
|---|---|---|
| `POST` | `/verticals/list` | `VERTICALS_READ` |
| `POST` | `/verticals` | `VERTICALS_CREATE` |
| `GET` | `/verticals/{id}` | `VERTICALS_READ` |
| `PUT` | `/verticals/{id}` | `VERTICALS_UPDATE` |
| `DELETE` | `/verticals/{id}` | `VERTICALS_DELETE` |
| `GET` | `/verticals/active` | `VERTICALS_READ` |
| `POST` | `/services/list` | `SERVICES_READ` |
| `POST` | `/services` | `SERVICES_CREATE` |
| `GET` | `/services/{id}` | `SERVICES_READ` |
| `PUT` | `/services/{id}` | `SERVICES_UPDATE` |
| `DELETE` | `/services/{id}` | `SERVICES_DELETE` |
| `GET` | `/services/active?vertical_id=` | `SERVICES_READ` |
| `POST` | `/products/list` | `PRODUCTS_READ` |
| `POST` | `/products` | `PRODUCTS_CREATE` |
| `GET` | `/products/{id}` | `PRODUCTS_READ` |
| `PUT` | `/products/{id}` | `PRODUCTS_UPDATE` |
| `DELETE` | `/products/{id}` | `PRODUCTS_DELETE` |
| `GET` | `/products/active?service_id=` | `PRODUCTS_READ` |

> Nota sobre `/active` vs `/options`: el template usa `/active` para "lista plana de activos para dropdowns" (ver `ENDPOINTS.ROLES.ACTIVE`, `ENDPOINTS.PERMISSIONS.ACTIVE`). Mantenemos esa convención.

## Permisos seed

13 permisos. Ya consolidados en [`docs/modules/_seed-and-roles.md`](../_seed-and-roles.md).

```python
# Module: catalog
("MENU-CATALOG", "Menu Catalog", "CATALOG"),
("VERTICALS_READ", "Read verticals", "CATALOG"),
("VERTICALS_CREATE", "Create verticals", "CATALOG"),
("VERTICALS_UPDATE", "Update verticals", "CATALOG"),
("VERTICALS_DELETE", "Delete verticals", "CATALOG"),
("SERVICES_READ", "Read services", "CATALOG"),
("SERVICES_CREATE", "Create services", "CATALOG"),
("SERVICES_UPDATE", "Update services", "CATALOG"),
("SERVICES_DELETE", "Delete services", "CATALOG"),
("PRODUCTS_READ", "Read products", "CATALOG"),
("PRODUCTS_CREATE", "Create products", "CATALOG"),
("PRODUCTS_UPDATE", "Update products", "CATALOG"),
("PRODUCTS_DELETE", "Delete products", "CATALOG"),
```

**Roles seed**:
- `ADMIN` — todos.
- `DOCTOR` — `VERTICALS_READ`, `SERVICES_READ`, `PRODUCTS_READ`.
- `ASESOR` — `MENU-CATALOG` + los `*_READ`.

## Decisiones de diseño (no obvias)

### 3 niveles fijos (Vertical → Service → Product) en lugar de árbol genérico

**Por qué**: la jerarquía siempre se ramifica en estos 3 niveles en el dominio clínico. Un árbol con `parent_id` flexible permite cualquier profundidad, pero implica recursividad en queries y reportes ambiguos ("¿es 'Brackets' un servicio o un sub-servicio?"). Tres niveles nominados son más estrictos y más fáciles de mostrar en UI.

**Costo si cambia**: convertir a árbol requiere migrar `service.vertical_id`/`product.service_id` a un `parent_id` polimórfico. Es factible pero hay que reescribir reportes y listados. Aceptable porque el dominio no apunta a esa necesidad.

### `Specialty` profesional del doctor **no** está en `catalog`

La "vertical" comercial (lo que la clínica vende) y la "specialty" profesional del doctor (su colegiatura) pueden divergir: un dermatólogo puede atender en la vertical "Estética facial" Y "Dermatología clínica". Para el MVP los unificamos — un doctor se asocia M:N a `Vertical` desde el módulo `staff`. Si en el futuro se necesita distinguir colegiatura, se agrega tabla `specialty` en `staff` sin tocar `catalog`.

### `currency` por producto en lugar de centralizar

Aunque la clínica es single-tenant y una sola moneda local, dejar la columna en `product` es trivial y abre la puerta a multi-moneda futuro sin migración. `default 'PEN'` mantiene la UX simple.

### `is_package` como flag, sin tabla `ProductSession`

Un paquete (ej. "12 sesiones de HydraFacial") es un solo `Product` que se vende una vez. La traza de "¿cuántas sesiones le quedan al cliente?" se lleva en `crm.CustomerStatusHistory` o `crm.LeadActivity` por ahora — no inflamos `catalog` con tabla de sesiones hasta que el negocio lo exija explícitamente.

## Dependencias entre módulos

| Módulo | Relación |
|---|---|
| `staff` | `doctor_vertical` (M:N): asignar doctores a verticales que atienden. |
| `scheduling` | `appointment.product_id` (FK): la cita es contra un producto agendable. |
| `marketing` | `promotion_product` (M:N): descuentos sobre productos. |
| `crm` | (vía `scheduling`) — el historial de productos consumidos por un `Person` se deriva de sus appointments. |

`catalog` no depende de ningún módulo de dominio — solo de `admin` (audit users via FK lógica a `user.id` en `created_by`/`updated_by`).

## Diagramas

- ER: [`docs/diagrams/er-catalog.puml`](../../diagrams/er-catalog.puml)
- Class diagram (modelos + repos + services): [`docs/diagrams/class-backend-catalog.puml`](../../diagrams/class-backend-catalog.puml)

## Próximos pasos / TODOs deliberados

- [ ] Cuando se diseñe `staff`, validar que `doctor_vertical` use FK con `ON DELETE RESTRICT` (no queremos perder asignaciones por borrar verticales).
- [ ] Si el negocio pide reportes de ingresos por categoría arbitraria (ej. "tratamientos faciales" cruzando verticales), evaluar agregar tabla `product_tag`.
- [ ] Considerar `ProductImage` si la UI futura del bot necesita enviar fotos (postergado al MVP del bot).
