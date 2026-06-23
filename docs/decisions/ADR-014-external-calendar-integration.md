# ADR-014: Integración de calendario externo — adaptador agnóstico, proveedores nativos, Fase 1 = lectura informativa a nivel clínica

> **Status**: Proposed
> **Date**: 2026-06-22
> **Deciders**: @daniel, @marco

## Context

El backlog tiene **HU43 (Google Calendar) PENDIENTE** y la tesis (§5.2.2 / §5.3) afirma —por error— que el agendamiento "está integrado y validado con Google Calendar". Hoy `scheduling` calcula la disponibilidad **on-the-fly** ([ADR-006](ADR-006-hybrid-calendar-slots.md) / [ADR-007](ADR-007-doctor-availability-concrete-blocks.md)) **sin ningún calendario externo**. Se quiere una integración **agnóstica al proveedor** (Google + dos más conocidos), **configurable desde una vista de configuración de la clínica**, que cierre esa brecha. **Hay que decidir ahora** el patrón de arquitectura antes de escribir una línea de código, porque la elección (nativo vs API unificada; una vía vs dos; por doctor vs por clínica) condiciona el modelo de datos, el costo recurrente, la postura de privacidad y la superficie de mantenimiento.

### Investigación (no se asumió nada)

Se corrió una investigación multi-agente con fuentes oficiales (8 dimensiones + 6 verificaciones adversarias, todas con citas). Hallazgos que dirigen la decisión:

- **Google Calendar API**: los scopes de calendario son **"sensitive", NO "restricted"** (verificado contra la [lista oficial de restricted scopes](https://support.google.com/cloud/answer/13464325)). ⇒ una app en producción necesita la **verificación OAuth** de Google (brand verification + video + privacy policy) pero **NO el assessment anual CASA de terceros** (cientos–miles de USD/año). El API es **gratis**. `freebusy.query` (scope no-sensitive) da ocupación opaca; `events.list` (scope sensitive `calendar.events.readonly`) da el detalle.
- **Microsoft Graph** es el único camino soportado para Outlook/M365 (CalDAV **no** existe en Microsoft; EWS se apaga 2026-2027). `getSchedule` (free/busy) + `events` (detalle, `Calendars.Read`). API gratis. Outlook.com personal es de segunda (sin `getSchedule`).
- **CalDAV NO sirve como capa agnóstica única**: no cubre Microsoft, Google-CalDAV no responde free/busy, iCloud no tiene push y usa app-passwords frágiles (y no es elegible para datos sensibles). Sirve sólo como **un adaptador más** (Apple/Fastmail/Nextcloud).
- **APIs unificadas (Cronofy / Nylas)**: abstraen los 3 proveedores y firman BAA, **pero** son **pagas** (Cronofy ~US$819/mes piso; Nylas ~US$10/mes + ~US$1.5/cuenta/mes), **cachean los datos de calendario en sus servidores** (procesador externo) y generan **lock-in** (verificado).
- **Patrón de la industria** (Cal.com, Calendly, Healthie — verificado): granularidad **por practicante**, separación **calendario "destino" (escritura)** vs **calendarios "seleccionados" (lectura de conflictos)**, modelo single-tenant = **un cliente OAuth a nivel app + N tokens por-cuenta**. La interfaz `Calendar` de Cal.com (`createEvent/updateEvent/deleteEvent/getAvailability/listCalendars`) es **el mismo molde del adaptador de proveedores LLM de bots** ([ADR-005](ADR-005-agnostic-bot-engine.md)).

### Decisiones de alcance del usuario (AskUserQuestion, 2026-06-22) — NO re-litigar

1. **Enfoque = adaptadores NATIVOS** (Google Calendar API + Microsoft Graph). La interfaz se diseña agnóstica para admitir un 3ro (CalDAV) después.
2. **Dirección = solo PULL** (leer ocupación externa). Sin push por ahora.
3. **Semántica = informativa**: el evento externo **se muestra (overlay), NO bloquea** la disponibilidad todavía. La Fase 1 **no toca `compute_available_slots`**.
4. **Lectura = detalle del evento** (título + horario), no free/busy opaco. ⇒ scope sensitive ⇒ verificación OAuth de Google requerida antes de GA.
5. **Granularidad = nivel clínica** (no por doctor todavía). El end-state per-doctor + push queda documentado como evolución. Modelo: **una (o pocas) conexión(es) OAuth de la clínica**, con **N calendarios mapeados a sedes** ("global, pero con un calendario por sede adentro / un grupo de calendarios").
6. **3er proveedor = diferido**: implementar Google + Microsoft primero.

## Decision

Construir un módulo nuevo **`calendar`** con un **adaptador `CalendarProvider` agnóstico** (molde [ADR-005](ADR-005-agnostic-bot-engine.md): `Protocol` común + dict `_CALENDAR_ADAPTERS` por proveedor + import lazy del SDK), implementado con **proveedores nativos** (`GoogleCalendarAdapter` sobre Google Calendar API, `MicrosoftGraphAdapter` sobre Microsoft Graph). Las credenciales OAuth **por conexión** se guardan en **Secret Manager** ([ADR-010](ADR-010-runtime-secret-resolution.md)); el cliente OAuth (client_id/secret) por proveedor es global por entorno (Settings + `--set-secrets`).

**La Fase 1 es lectura informativa a nivel clínica:**

- Una o varias **`CalendarConnection`** (cuenta OAuth de la clínica, p. ej. la cuenta de Google de la clínica) → cada una expone N calendarios.
- Cada calendario se mapea a una **sede** (`clinic.Branch`) vía **`CalendarSource`** (o a "todas las sedes" si `branch_id` es null). El conjunto de `CalendarSource` habilitados ES "el grupo de calendarios de la clínica".
- Se **leen los eventos** (detalle: título + horario) de los calendarios habilitados y se **muestran como una capa informativa no-bloqueante** sobre la grilla de calendario de `scheduling` (`CalendarGrid`, F4) y como un aviso suave en el wizard de reserva. **NO** se modifica `compute_available_slots` ni los invariantes de booking: el agendamiento es idéntico al de hoy. Una caída del proveedor externo no puede romper nada porque **la integración no toca el camino de reserva** (capa puramente aditiva).
- Lectura **on-demand** (live, con refresh de token al vuelo): sin tabla espejo de eventos ni webhooks en la Fase 1.

**Se rechaza** la API unificada (Cronofy/Nylas) y **se difiere** todo lo siguiente, documentado como evolución: modo bloqueante (alimentar el busy externo a `compute_available_slots` como un MINUS extra, extensión de [ADR-006](ADR-006-hybrid-calendar-slots.md)); conexiones **por doctor** + **push** de las citas medisage al calendario del doctor; **sync por webhooks** (Google watch / Graph subscriptions + syncToken/delta + renovación vía Cloud Tasks, [ADR-012](ADR-012-cloud-tasks-bot-dispatch.md) + tabla espejo `ExternalEvent`); **3er proveedor CalDAV** (Apple iCloud + servidores estándar).

## Alternatives Considered

### Opción A — API unificada de terceros (Cronofy / Nylas)
- **Pros**: una sola integración cubre Google + Microsoft + Apple; el proveedor maneja tokens/refresh y firma BAA; webhooks normalizados; time-to-market mínimo.
- **Cons**: **paga** (Cronofy ~US$819/mes piso; Nylas ~US$10/mes + ~US$1.5/cuenta); **cachea los datos de calendario en su servidor** (un procesador externo en la ruta de datos personales); **lock-in** (modelo de grants/objetos propietario; cambiar de región o de proveedor obliga a re-autenticar a todos).
- **Rechazada porque**: el costo recurrente es injustificable para un sistema single-tenant / la tesis, y meter un procesador externo de datos contradice la postura de privacidad (Ley 29733) sin necesidad — los APIs nativos son gratis y los datos quedan en medisage.

### Opción B — CalDAV como única capa "agnóstica"
- **Pros**: un estándar abierto (RFC 4791), sin SDK por proveedor, sin lock-in; encaja conceptualmente con el patrón adaptador.
- **Cons**: **no cubre Microsoft** (M365 no expone CalDAV); **Google-CalDAV no responde free/busy** (hay que ir igual a la API JSON); **iCloud no tiene push** (polling) y usa app-passwords que se revocan solos; "ningún servidor implementa CalDAV perfecto".
- **Rechazada como capa única**; se conserva como **un adaptador más** del `CalendarProvider` (Apple/self-hosted), diferido.

### Opción C — Modo bloqueante desde el día 1 (feed a `compute_available_slots`)
- **Pros**: previene ofrecer un horario donde la clínica/el doctor ya está ocupado; mayor valor para la disponibilidad.
- **Cons**: toca el corazón del módulo (`compute_available_slots` + invariantes de booking); acopla la correctitud del agendamiento a un sistema externo; mayor riesgo y superficie de test.
- **Rechazada para la Fase 1** (el usuario eligió informativo): empezar aditivo y aislado; el modo bloqueante es una **extensión documentada** de [ADR-006](ADR-006-hybrid-calendar-slots.md) cuando se quiera.

### Opción D — Por doctor + push desde el día 1
- **Pros**: es el patrón estándar de la industria (Cal.com/Calendly) y el end-state deseado; las citas medisage aparecen en el calendario del doctor.
- **Cons**: mayor superficie (consentimiento OAuth por doctor; scope de **escritura** sensible; manejo de PHI en los títulos empujados; webhooks/renovación para mantener fresco); más lento de validar.
- **Diferida**: el usuario eligió **clínica-PULL primero**; el modelo de datos de la Fase 1 (`CalendarConnection` + `CalendarSource`) crece naturalmente al caso per-doctor (un `CalendarSource` puede mapear a un doctor en vez de a una sede) y al push (un `DestinationCalendar` para escritura), sin reescritura.

## Consequences

### Positivas
- **Reusa tres patrones ya en producción**: adaptador agnóstico ([ADR-005](ADR-005-agnostic-bot-engine.md)), secreto por-cuenta en Secret Manager ([ADR-010](ADR-010-runtime-secret-resolution.md)) y —en la fase de sync futura— Cloud Tasks ([ADR-012](ADR-012-cloud-tasks-bot-dispatch.md)). No hay que inventar infraestructura.
- **Aditivo y aislado**: la Fase 1 **no toca el camino de reserva** → es imposible que rompa el booking; degrada con gracia (si el proveedor falla, la capa externa se ve vacía + un aviso de salud, nunca un 5xx).
- **Barato y privado**: las APIs nativas son gratis; los datos quedan en medisage (mejor para la **Ley 29733**, sin procesador externo); sin lock-in.
- **Cierra la incoherencia de la tesis + HU43** en su espíritu (el agendamiento "conversa" con Google/Outlook) con la mínima superficie.
- **Interfaz lista para crecer**: el `CalendarProvider` + el modelo `Connection`/`Source` escalan a bloqueante, per-doctor, push, sync y 3er proveedor sin reescritura.

### Negativas / Trade-offs
- **Mantenemos 2-3 integraciones nativas** (Google + Microsoft ahora; CalDAV después) en vez de una sola API. Es trabajo de ingeniería que un proveedor unificado nos ahorraría — a cambio del costo/privacidad/lock-in que rechazamos.
- **Verificación OAuth de Google requerida antes de GA** (por leer detalle = scope sensitive `calendar.events.readonly`). Es un gate de días-semanas; **arrancarlo temprano**. (Es verificación, NO el assessment CASA.)
- **Refresh de tokens + manejo de revocación**: hay que refrescar el access token y manejar `invalid_grant` (re-consentir desde la UI). **Gotcha**: la app OAuth de Google en estado "Testing" emite refresh tokens de **7 días** → hay que publicarla "In production" antes de confiar en el almacenamiento durable.
- **Lectura on-demand** depende de la disponibilidad del proveedor y consume cuota/latencia por carga de grilla. Mitigado: best-effort + aislado; la **sync con cache (Fase futura)** lo optimiza.

### Lo que esto nos obliga a hacer
- Nuevas Settings (`GOOGLE_OAUTH_CLIENT_ID/SECRET`, `MICROSOFT_OAUTH_CLIENT_ID/SECRET`, `MICROSOFT_OAUTH_TENANT`, `CALENDAR_OAUTH_REDIRECT_BASE`) en **AMBOS** workflows de deploy (`--set-env-vars`/`--set-secrets`, lección §9/§11) + un **boot-validator** que falle ruidoso si un proveedor queda medio-configurado (client_id sin secret), espejo de `_enforce_bot_dispatch_secret`.
- Un **secret por conexión** en Secret Manager (`medisage-calendar-{connection_id}-{env}`, JSON `{access_token, refresh_token, expiry, scopes}`), reusando `app.core.secrets` (con escritura/rotación, que hoy es read-only → se extiende).
- **Publicar la app OAuth de Google "In production"** (verificación) y registrar la app en **Entra ID** (Microsoft) antes de GA.
- Definir permisos RBAC del módulo (`CALENDAR_*`), nav, endpoints, types espejo — todo en una F0 inerte (molde scheduling F0).
- Diseñar el detalle por ficha (`docs/modules/calendar/{README,backend,ui,frontend}.md`) en la fase de documentación previa a F0.

## Referencias

- **Documento de diseño**: [`docs/modules/calendar/design.md`](../modules/calendar/design.md) (arquitectura, modelo de datos, flujos OAuth, UI, fases, diagramas mermaid).
- **ADRs reutilizados**: [ADR-005](ADR-005-agnostic-bot-engine.md) (adaptador agnóstico — molde), [ADR-006](ADR-006-hybrid-calendar-slots.md) (disponibilidad on-the-fly — el modo bloqueante futuro la extiende), [ADR-010](ADR-010-runtime-secret-resolution.md) (secreto por-cuenta), [ADR-012](ADR-012-cloud-tasks-bot-dispatch.md) (Cloud Tasks — sync futura).
- **Código relevante (puntos de enganche)**: `backend/app/modules/scheduling/services/availability.py:240` (el `busy` donde engancharía el modo bloqueante futuro), `backend/app/modules/bots/services/engine/embedded.py:69` (`_PROVIDER_ADAPTERS`, el molde del adaptador), `backend/app/core/secrets.py` (resolver de secretos), `backend/app/core/cloud_tasks.py` (despacho async), `frontend/src/app/(main)/scheduling/.../CalendarGrid.tsx` (la grilla donde va el overlay).
- **Docs externos**: [Google Calendar API](https://developers.google.com/workspace/calendar/api/v3/reference), [scopes sensitive vs restricted](https://support.google.com/cloud/answer/13464325), [Microsoft Graph calendars](https://learn.microsoft.com/en-us/graph/api/resources/calendar), [Cal.com `Calendar` interface](https://github.com/calcom/cal.com/blob/main/packages/types/Calendar.d.ts) (blueprint).
- **Cumplimiento**: el régimen real de medisage es la **Ley N.º 29733 (Protección de Datos Personales, Perú)**, no HIPAA. Principio que sí aplica universalmente: **minimización de datos** (no exportar datos del paciente a calendarios de terceros). En la Fase 1 no se exporta nada (solo se lee el calendario propio de la clínica).
