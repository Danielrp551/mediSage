"""
Routers del módulo `scheduling` (F1+). Aggregator bajo `/scheduling`: appointment-statuses CRUD +
/active + transitions (GET/PUT matriz); availability (compute/check-slot); appointments CRUD +
calendar + transition + shortcuts (confirm/check-in/start/attend/no-show/cancel/reschedule);
`/me/appointments/list` + `/me/calendar` (self-service del doctor, scoping anti-IDOR); y la facade
SYSTEM `/appointments/from-bot` + `/appointments/{id}/cancel-from-bot` (sin RBAC, BotInvocationContext).

PUT (no PATCH); `/active` lista cruda sin envelope. `/availability/*`→`AVAILABILITY_READ`;
`/appointments/calendar`→`APPOINTMENTS_READ` (+`AVAILABILITY_READ` para los slots libres);
`/me/*`→`MY_APPOINTMENTS_READ`.

⚠ F0: NADA montado. El aggregator NO se incluye en `app/main.py` hasta F1 (skeleton inerte).
"""
