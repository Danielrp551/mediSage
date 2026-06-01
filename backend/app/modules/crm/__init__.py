"""Módulo `crm`: contactos (`Person`) y su ciclo de vida comercial (hilos lead y
customer en tablas hijas separadas, ADR-003), identificadores multicanal,
catálogos de estado configurables con matriz de transiciones (ADR-008),
asignación de owner con round-robin, historiales inmutables y timeline
polimórfico de actividad.

Es el módulo más grande del proyecto (12 entidades). Skeleton creado en F0 (Prep);
el contenido real entra por fases (ver `docs/modules/crm/`):
- F1: `Person` + `PersonContactIdentifier`.
- F2: catálogos `LeadStatus`/`CustomerStatus` + matriz de transiciones.
- F3: ciclo de vida del lead (estado + historial + asignación + actividad).
- F4: ciclo de vida del cliente + `promote_to_customer`.
- F5: timeline rico + `find_by_identifier_or_create`.

Las columnas que apuntan a módulos futuros (`source_campaign_id`, `related_*`)
son `varchar(36)` SIN FK hasta que ese módulo exista (ADR-009). Este paquete NO
se registra en `app/modules/__init__.py` ni en `app/main.py` hasta F1.
"""
