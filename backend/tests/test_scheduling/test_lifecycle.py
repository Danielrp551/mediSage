"""
Tests de integración del lifecycle de citas (service `transition`): transición
genérica (valida la matriz seedeada), shortcuts (confirm/check-in/start/attend/
no-show), cancel (invariante CANCEL_TOO_LATE) y reschedule (crea cita nueva).

Matriz seedeada (relevante): SCHEDULED→{CONFIRMED, CHECKED_IN, NO_SHOW, CANCELLED,
RESCHEDULED}; CONFIRMED→{CHECKED_IN, ...}; CHECKED_IN→{IN_PROGRESS, CANCELLED};
IN_PROGRESS→{ATTENDED, CANCELLED}. Los finales no tienen salida.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.test_scheduling.helpers import (
    appointment_payload,
    auth_headers,
    build_bookable_scenario,
)

PREFIX = "/api/v1/scheduling/appointments"


async def _book(client: AsyncClient, headers: dict, s, **overrides) -> str:
    r = await client.post(PREFIX, json=appointment_payload(s, **overrides), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


async def test_confirm_shortcut(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    appt_id = await _book(client, headers, s)
    r = await client.post(f"{PREFIX}/{appt_id}/confirm", headers=headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"]["code"] == "CONFIRMED"
    assert data["confirmed_at"] is not None


async def test_full_attended_flow_promotes_customer(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """SCHEDULED → CHECKED_IN → IN_PROGRESS → ATTENDED. Attend promueve a cliente."""
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    appt_id = await _book(client, headers, s)

    r1 = await client.post(f"{PREFIX}/{appt_id}/check-in", headers=headers)
    assert r1.status_code == 200, r1.text
    assert r1.json()["data"]["status"]["code"] == "CHECKED_IN"

    r2 = await client.post(f"{PREFIX}/{appt_id}/start", headers=headers)
    assert r2.status_code == 200, r2.text
    assert r2.json()["data"]["status"]["code"] == "IN_PROGRESS"

    r3 = await client.post(f"{PREFIX}/{appt_id}/attend", headers=headers)
    assert r3.status_code == 200, r3.text
    data = r3.json()["data"]
    assert data["status"]["code"] == "ATTENDED"
    assert data["attended_at"] is not None
    # 4 aristas en el history: None→SCHEDULED, →CHECKED_IN, →IN_PROGRESS, →ATTENDED.
    assert len(data["status_history"]) == 4


async def test_no_show_shortcut(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    appt_id = await _book(client, headers, s)
    r = await client.post(f"{PREFIX}/{appt_id}/no-show", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"]["code"] == "NO_SHOW"


async def test_transition_not_allowed_400(client: AsyncClient, admin_credentials: dict) -> None:
    """SCHEDULED → IN_PROGRESS no es arista válida (hay que pasar por CHECKED_IN)."""
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    appt_id = await _book(client, headers, s)
    # Resolver el id de IN_PROGRESS desde /active.
    active = await client.get(
        "/api/v1/scheduling/appointment-statuses/active", headers=headers
    )
    in_progress_id = next(x["id"] for x in active.json() if x["code"] == "IN_PROGRESS")
    r = await client.post(
        f"{PREFIX}/{appt_id}/transition",
        json={"to_status_id": in_progress_id},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "APPOINTMENT_TRANSITION_NOT_ALLOWED"


async def test_transition_generic_allowed(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    appt_id = await _book(client, headers, s)
    active = await client.get(
        "/api/v1/scheduling/appointment-statuses/active", headers=headers
    )
    confirmed_id = next(x["id"] for x in active.json() if x["code"] == "CONFIRMED")
    r = await client.post(
        f"{PREFIX}/{appt_id}/transition",
        json={"to_status_id": confirmed_id, "reason": "cliente confirmó"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"]["code"] == "CONFIRMED"


async def test_transition_appointment_not_found_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    active = await client.get(
        "/api/v1/scheduling/appointment-statuses/active", headers=headers
    )
    some_id = active.json()[0]["id"]
    r = await client.post(
        f"{PREFIX}/ghost/transition", json={"to_status_id": some_id}, headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "APPOINTMENT_NOT_FOUND"


async def test_transition_unknown_status_404(
    client: AsyncClient, admin_credentials: dict
) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    appt_id = await _book(client, headers, s)
    r = await client.post(
        f"{PREFIX}/{appt_id}/transition", json={"to_status_id": "ghost"}, headers=headers
    )
    assert r.status_code == 404, r.text
    assert r.json()["code"] == "APPOINTMENT_STATUS_NOT_FOUND"


async def test_cancel_appointment(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    appt_id = await _book(client, headers, s)
    r = await client.post(
        f"{PREFIX}/{appt_id}/cancel",
        json={"cancellation_reason": "el cliente pidió cancelar"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["status"]["code"] == "CANCELLED"
    assert data["cancelled_at"] is not None
    assert data["cancellation_reason"] == "el cliente pidió cancelar"


async def test_cancel_too_late_override_admin(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Cita pronto (~24h) + producto que exige 48h de anticipación → dentro de la
    ventana de bloqueo. El admin TIENE APPOINTMENTS_CANCEL_OVERRIDE → la cancelación
    procede igual (ejercita la rama del override del invariante #9)."""
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(
        client, headers, min_hours_to_cancel=48, days_ahead=1
    )
    appt_id = await _book(client, headers, s)
    r = await client.post(
        f"{PREFIX}/{appt_id}/cancel",
        json={"cancellation_reason": "override admin"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"]["code"] == "CANCELLED"


async def test_cancel_too_late_blocked_400_without_override(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Mismo escenario tardío, pero el actor NO tiene APPOINTMENTS_CANCEL_OVERRIDE →
    el guard #9 dispara CANCEL_TOO_LATE (400)."""
    from tests.test_scheduling.helpers import token_for_limited_user

    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(
        client, headers, min_hours_to_cancel=48, days_ahead=1
    )
    appt_id = await _book(client, headers, s)
    # Token de un usuario con CANCEL pero SIN override.
    limited = await token_for_limited_user(
        client, headers, ["APPOINTMENTS_CANCEL", "APPOINTMENTS_READ"]
    )
    r = await client.post(
        f"{PREFIX}/{appt_id}/cancel",
        json={"cancellation_reason": "demasiado tarde"},
        headers={"Authorization": f"Bearer {limited}"},
    )
    assert r.status_code == 400, r.text
    assert r.json()["code"] == "CANCEL_TOO_LATE"


async def test_cancel_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/ghost/cancel", json={"cancellation_reason": "x"}, headers=headers
    )
    assert r.status_code == 404, r.text


async def test_reschedule_creates_new_appointment(
    client: AsyncClient, admin_credentials: dict
) -> None:
    """Reschedule marca la vieja RESCHEDULED y crea una NUEVA apuntando a la vieja."""
    headers = await auth_headers(client, admin_credentials)
    s = await build_bookable_scenario(client, headers)
    old_id = await _book(client, headers, s)
    # Nuevo horario el mismo día dentro del bloque (08:00-18:00): 14:00.
    new_when = s.scheduled_for.replace("T10:00", "T14:00")
    r = await client.post(
        f"{PREFIX}/{old_id}/reschedule",
        json={"scheduled_for": new_when, "reason": "reprogramada"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    new = r.json()["data"]
    assert new["id"] != old_id
    assert new["previous_appointment_id"] == old_id
    assert new["status"]["code"] == "SCHEDULED"

    # La vieja quedó RESCHEDULED.
    old = await client.get(f"{PREFIX}/{old_id}", headers=headers)
    assert old.json()["data"]["status"]["code"] == "RESCHEDULED"


async def test_reschedule_not_found_404(client: AsyncClient, admin_credentials: dict) -> None:
    headers = await auth_headers(client, admin_credentials)
    r = await client.post(
        f"{PREFIX}/ghost/reschedule",
        json={"scheduled_for": "2030-01-07T14:00:00+00:00"},
        headers=headers,
    )
    assert r.status_code == 404, r.text
