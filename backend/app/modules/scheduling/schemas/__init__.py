"""
Schemas Pydantic v2 del módulo `scheduling` (F1+). Variantes por entidad
(Create/Update/Item/Detail/Option) + requests/responses específicos: `TransitionTargets`
(matriz from→to), `AvailabilityRequest`/`AvailabilitySlot`/`AvailabilityResponse`,
`CheckSlotRequest`, `AppointmentTransitionRequest`, `RescheduleRequest`, `CancelRequest`,
`CalendarResponse {appointments, free_slots, from_date, to_date}`, y la
`BotInvocationContext` de la facade SYSTEM (from-bot/cancel-from-bot). Espejan
`frontend/src/types/scheduling.types.ts`.

`AppointmentStatus.code` = MAYÚSCULAS sin pattern slug restrictivo (espeja crm.LeadStatus; solo
min/max length). `source` es enum código. Los numeric (si los hubiera) se serializan como string.
INERTE en F0.
"""
