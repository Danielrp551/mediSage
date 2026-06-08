"""
Disponibilidad on-the-fly (ADR-006/007) + validación de invariantes de booking
(compartida por check_slot y create_appointment). NO persiste nada.

Algoritmo (compute_available_slots): por cada bloque concreto de DoctorAvailability
(ADR-007) en el rango, la ventana de slots = (bloque del doctor) ∩ (disponibilidad del
office), donde disponibilidad del office = OfficeOperatingHours del weekday − cierres
(OfficeClosure is_closed=true) + aperturas extra (is_closed=false). Se resta las citas
ocupadas del doctor, se generan slots de `slot` min alineados al inicio del bloque, y se
exige que N=ceil(duración/slot) granos quepan.

TZ (lección recurrente): las horas locales (Time naive de los bloques/horarios) se
combinan con la fecha EN `branch.timezone` (zoneinfo) y se pasan a UTC — DST-safe. El
weekday se deriva de la fecha LOCAL del bloque (date es local), nunca desde UTC.

Helpers de intervalos: funciones puras sobre listas de (start, end) de cualquier tipo
comparable (time locales o datetime UTC). Son el núcleo propenso a off-by-one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from datetime import date as date_type
from math import ceil
from typing import Any, Protocol, TypeVar
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.modules.catalog.models.product import Product
from app.modules.catalog.repositories.product import product_repository
from app.modules.clinic.models.branch import Branch
from app.modules.clinic.models.office import Office
from app.modules.clinic.models.office_closure import OfficeClosure
from app.modules.clinic.models.office_operating_hours import OfficeOperatingHours
from app.modules.clinic.repositories.branch import branch_repository
from app.modules.clinic.repositories.office import office_repository
from app.modules.clinic.repositories.office_closure import office_closure_repository
from app.modules.clinic.repositories.office_operating_hours import (
    office_operating_hours_repository,
)
from app.modules.scheduling.repositories.appointment import appointment_repository
from app.modules.scheduling.repositories.appointment_status import (
    appointment_status_repository,
)
from app.modules.scheduling.schemas.availability import (
    AvailabilityResponse,
    AvailabilitySlot,
    CheckSlotResponse,
)
from app.modules.staff.models.doctor import Doctor
from app.modules.staff.repositories.doctor import doctor_repository
from app.modules.staff.repositories.doctor_availability import (
    doctor_availability_repository,
)

# Codes de estado (MAYÚSCULAS) que NO ocupan tiempo del doctor/office (cita liberada).
_NON_BLOCKING_CODES = {"CANCELLED", "NO_SHOW", "RESCHEDULED"}


class _Comparable(Protocol):
    """Soporta los operadores de orden — para los helpers de intervalos genéricos
    sobre `time` (ventanas locales) o `datetime` (ventanas UTC)."""

    def __lt__(self, other: Any, /) -> bool: ...
    def __le__(self, other: Any, /) -> bool: ...
    def __gt__(self, other: Any, /) -> bool: ...
    def __ge__(self, other: Any, /) -> bool: ...


T = TypeVar("T", bound=_Comparable)


def _as_utc(dt: datetime) -> datetime:
    """Normaliza a UTC-aware. Las columnas son timestamptz (UTC en disco): en Postgres
    vuelven aware, pero en sqlite (smoke) vuelven NAIVE → se les adjunta UTC. También
    cubre un payload sin offset (se interpreta como UTC). Evita comparar naive vs aware."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


# ── Helpers de intervalos (puros) ─────────────────────────────────────


def _normalize(ranges: list[tuple[T, T]]) -> list[tuple[T, T]]:
    """Ordena, descarta vacíos (a>=b) y fusiona solapados/adyacentes."""
    cleaned = sorted((a, b) for (a, b) in ranges if a < b)
    if not cleaned:
        return []
    merged = [cleaned[0]]
    for a, b in cleaned[1:]:
        last_a, last_b = merged[-1]
        if a <= last_b:
            merged[-1] = (last_a, max(last_b, b))
        else:
            merged.append((a, b))
    return merged


def _intersect(a_ranges: list[tuple[T, T]], b_ranges: list[tuple[T, T]]) -> list[tuple[T, T]]:
    out: list[tuple[T, T]] = []
    for a0, a1 in a_ranges:
        for b0, b1 in b_ranges:
            lo = max(a0, b0)
            hi = min(a1, b1)
            if lo < hi:
                out.append((lo, hi))
    return _normalize(out)


def _subtract(base: list[tuple[T, T]], subs: list[tuple[T, T]]) -> list[tuple[T, T]]:
    result = list(base)
    for s0, s1 in subs:
        if s1 <= s0:
            continue
        nxt: list[tuple[T, T]] = []
        for b0, b1 in result:
            if s1 <= b0 or s0 >= b1:  # sin solape
                nxt.append((b0, b1))
                continue
            if b0 < s0:
                nxt.append((b0, s0))
            if s1 < b1:
                nxt.append((s1, b1))
        result = nxt
    return _normalize(result)


def _align_to_grid(window_start: datetime, origin: datetime, slot_min: int) -> datetime:
    """Primer punto de la grilla (origin + k*slot) >= window_start."""
    if window_start <= origin:
        return origin
    minutes = (window_start - origin).total_seconds() / 60.0
    k = ceil(minutes / slot_min)
    return origin + timedelta(minutes=slot_min * k)


def _doctor_name(doctor: Doctor) -> str:
    return doctor.user.full_name


def _office_windows(
    oh_rows: list[OfficeOperatingHours],
    closure_rows: list[OfficeClosure],
    day: date_type,
    tz: ZoneInfo,
) -> list[tuple[datetime, datetime]]:
    """Ventanas UTC en que el office está disponible ESE día: OperatingHours del weekday
    − cierres (is_closed=true) + aperturas extra (is_closed=false)."""
    weekday = day.weekday()  # 0=Lun..6=Dom (mismo convenio que clinic.day_of_week)
    windows = [
        (
            datetime.combine(day, h.opens_at, tzinfo=tz).astimezone(UTC),
            datetime.combine(day, h.closes_at, tzinfo=tz).astimezone(UTC),
        )
        for h in oh_rows
        if h.day_of_week == weekday
    ]
    windows = _normalize(windows)
    day_start = datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)
    day_end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    closed = [(_as_utc(c.starts_at), _as_utc(c.ends_at)) for c in closure_rows if c.is_closed]
    extra = _intersect(
        [(_as_utc(c.starts_at), _as_utc(c.ends_at)) for c in closure_rows if not c.is_closed],
        [(day_start, day_end)],
    )
    windows = _subtract(windows, closed)
    return _normalize(windows + extra)


async def _resolve_blocking_status_ids(db: AsyncSession) -> list[str]:
    """ids de los estados que OCUPAN tiempo (todos menos CANCELLED/NO_SHOW/RESCHEDULED)."""
    statuses = await appointment_status_repository.list_active(db)
    return [s.id for s in statuses if s.code not in _NON_BLOCKING_CODES]


# ── compute_available_slots (corazón) ─────────────────────────────────


async def compute_available_slots(
    db: AsyncSession,
    *,
    doctor_id: str,
    product_id: str,
    branch_id: str | None = None,
    office_id: str | None = None,
    from_date: date_type,
    to_date: date_type,
) -> AvailabilityResponse:
    product = await product_repository.get_by_id(db, product_id)
    if product is None:
        raise NotFoundException("Producto no encontrado", code="PRODUCT_NOT_FOUND")
    doctor = await doctor_repository.get_full(db, doctor_id)
    if doctor is None:
        raise NotFoundException("Doctor no encontrado", code="DOCTOR_NOT_FOUND")

    slot = doctor.slot_duration_min
    duration_min = product.duration_min or doctor.slot_duration_min
    empty = AvailabilityResponse(slots=[], duration_min=duration_min, doctor_slot_duration_min=slot)

    if not doctor.active:  # decisión #3: doctor inactivo no acepta reservas
        return empty
    vertical_id = product.vertical_id
    if vertical_id not in {v.id for v in doctor.verticals}:
        return empty
    doctor_branch_ids = {b.id for b in doctor.branches}

    # Offices candidatos: activos + vivos + aptos para el vertical, en una branch del doctor.
    offices = await office_repository.list_active(db, branch_id=branch_id, vertical_id=vertical_id)
    offices = [o for o in offices if o.branch_id in doctor_branch_ids]
    if office_id is not None:
        offices = [o for o in offices if o.id == office_id]
    if not offices:
        return empty
    office_by_id = {o.id: o for o in offices}

    branches = await branch_repository.get_by_ids(db, list({o.branch_id for o in offices}))
    branch_by_id = {b.id: b for b in branches}

    n_contig = ceil(duration_min / slot)
    range_start = datetime.combine(from_date, time.min, tzinfo=UTC)
    range_end = datetime.combine(to_date + timedelta(days=1), time.min, tzinfo=UTC)
    # Las ventanas se computan en la TZ LOCAL del branch: para offsets negativos (Lima
    # UTC-5) el último día local se extiende hasta D+1 05:00 UTC, MÁS ALLÁ de range_end;
    # para offsets positivos, el primer día empieza ANTES de range_start. El prefetch se
    # paddea ±1 día (cubre cualquier offset) y _office_windows/_subtract clipean per-día.
    prefetch_start = range_start - timedelta(days=1)
    prefetch_end = range_end + timedelta(days=1)

    blocking = await _resolve_blocking_status_ids(db)
    appts = await appointment_repository.list_in_range(
        db, doctor_id=doctor_id, start=prefetch_start, end=prefetch_end, status_ids=blocking
    )
    busy = [
        (_as_utc(a.scheduled_for), _as_utc(a.scheduled_for) + timedelta(minutes=a.duration_min))
        for a in appts
    ]

    av_blocks = await doctor_availability_repository.list_for_doctor(
        db, doctor_id, date_from=from_date, date_to=to_date
    )
    av_blocks = [b for b in av_blocks if b.office_id in office_by_id]

    # Prefetch (sin N+1): operating hours por office + cierres por office en el rango.
    oh_by_office: dict[str, list[OfficeOperatingHours]] = {}
    closures_by_office: dict[str, list[OfficeClosure]] = {}
    for oid in {b.office_id for b in av_blocks}:
        oh_by_office[oid] = await office_operating_hours_repository.list_for_office(db, oid)
        closures_by_office[oid] = await office_closure_repository.list_for_office(
            db, oid, date_from=prefetch_start, date_to=prefetch_end
        )

    slots: list[AvailabilitySlot] = []
    for av in av_blocks:
        office = office_by_id[av.office_id]
        branch = branch_by_id.get(office.branch_id)
        if branch is None:  # branch soft-deleted (get_by_ids la omite) → sin slots
            continue
        tz = ZoneInfo(branch.timezone)
        day = av.date

        block_start = datetime.combine(day, av.opens_at, tzinfo=tz).astimezone(UTC)
        block_end = datetime.combine(day, av.closes_at, tzinfo=tz).astimezone(UTC)
        office_avail = _office_windows(
            oh_by_office[av.office_id], closures_by_office[av.office_id], day, tz
        )
        windows = _intersect([(block_start, block_end)], office_avail)
        free = _subtract(windows, busy)

        for w0, w1 in free:
            cursor = _align_to_grid(w0, block_start, slot)
            while cursor + timedelta(minutes=slot * n_contig) <= w1:
                slots.append(
                    AvailabilitySlot(
                        starts_at=cursor,
                        ends_at=cursor + timedelta(minutes=duration_min),
                        doctor_id=doctor.id,
                        doctor_name=_doctor_name(doctor),
                        office_id=office.id,
                        office_name=office.name,
                        branch_id=branch.id,
                        branch_name=branch.name,
                    )
                )
                cursor += timedelta(minutes=slot)

    # Dedupe (doctor, office, start) + ordenar.
    seen: set[tuple[str, str, datetime]] = set()
    unique: list[AvailabilitySlot] = []
    for s in sorted(slots, key=lambda x: (x.starts_at, x.office_id)):
        key = (s.doctor_id, s.office_id, s.starts_at)
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)
    return AvailabilityResponse(
        slots=unique, duration_min=duration_min, doctor_slot_duration_min=slot
    )


# ── Invariantes de booking (compartidos check_slot / create) ──────────


@dataclass
class BookingContext:
    product: Product
    office: Office
    doctor: Doctor
    branch: Branch
    branch_id: str
    duration_min: int


async def _fits_in_availability_block(
    db: AsyncSession, doctor: Doctor, office: Office, branch: Branch, start: datetime, end: datetime
) -> bool:
    tz = ZoneInfo(branch.timezone)
    local_day = start.astimezone(tz).date()
    av_blocks = await doctor_availability_repository.list_for_doctor(
        db, doctor.id, date_from=local_day, date_to=local_day
    )
    for av in av_blocks:
        if av.office_id != office.id:
            continue
        b_start = datetime.combine(av.date, av.opens_at, tzinfo=tz).astimezone(UTC)
        b_end = datetime.combine(av.date, av.closes_at, tzinfo=tz).astimezone(UTC)
        if b_start <= start and end <= b_end:
            return True
    return False


async def _office_open(
    db: AsyncSession, office: Office, branch: Branch, start: datetime, end: datetime
) -> bool:
    tz = ZoneInfo(branch.timezone)
    local_day = start.astimezone(tz).date()
    oh = await office_operating_hours_repository.list_for_office(db, office.id)
    day_start = datetime.combine(local_day, time.min, tzinfo=tz).astimezone(UTC)
    day_end = datetime.combine(local_day + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    closures = await office_closure_repository.list_for_office(
        db, office.id, date_from=day_start, date_to=day_end
    )
    windows = _office_windows(oh, closures, local_day, tz)
    return any(w0 <= start and end <= w1 for (w0, w1) in windows)


async def _acquire_booking_locks(db: AsyncSession, doctor_id: str, office_id: str) -> None:
    """Serializa los creates concurrentes sobre el mismo doctor/office con advisory
    locks de transacción (Postgres). NECESARIO porque `SELECT … FOR UPDATE` solo bloquea
    filas EXISTENTES que matchean el WHERE → no cubre el primer booking de un slot VACÍO
    (dos tx ven 0 filas, no lockean nada, ambas insertan = doble reserva). El advisory
    lock se libera al fin de la tx. Orden fijo doctor→office (evita deadlock). No-op fuera
    de Postgres (sqlite smoke). Hardening futuro: EXCLUSION constraint GIST + btree_gist."""
    conn = await db.connection()
    if conn.dialect.name != "postgresql":
        return
    for key in (f"appt:doctor:{doctor_id}", f"appt:office:{office_id}"):
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": key})


async def _has_overlap(
    db: AsyncSession,
    kind: str,
    entity_id: str,
    start: datetime,
    end: datetime,
    blocking: list[str],
    exclude_id: str | None,
    for_update: bool,
) -> bool:
    if kind == "doctor":
        candidates = await appointment_repository.list_blocking_for_doctor(
            db,
            entity_id,
            start=start,
            end=end,
            blocking_status_ids=blocking,
            exclude_id=exclude_id,
            for_update=for_update,
        )
    else:
        candidates = await appointment_repository.list_blocking_for_office(
            db,
            entity_id,
            start=start,
            end=end,
            blocking_status_ids=blocking,
            exclude_id=exclude_id,
            for_update=for_update,
        )
    for a in candidates:
        a_start = _as_utc(a.scheduled_for)
        a_end = a_start + timedelta(minutes=a.duration_min)
        if a_start < end and a_end > start:
            return True
    return False


async def validate_booking_invariants(
    db: AsyncSession,
    *,
    doctor_id: str,
    office_id: str,
    product_id: str,
    scheduled_for: datetime,
    exclude_id: str | None,
    for_update: bool,
) -> BookingContext:
    """Valida los invariantes 0a + 2-8 (1 es tautológico al derivar branch del office).
    Orden: baratos (existencia/branch/vertical) antes que los caros (conflicto FOR UPDATE).
    Lanza la excepción de dominio del primer invariante que falla; check_slot la captura."""
    product = await product_repository.get_by_id(db, product_id)
    if product is None:
        raise NotFoundException("Producto no encontrado", code="PRODUCT_NOT_FOUND")
    office = await office_repository.get_full(db, office_id)
    if office is None:
        raise NotFoundException("Consultorio no encontrado", code="OFFICE_NOT_FOUND")
    doctor = await doctor_repository.get_full(db, doctor_id)
    if doctor is None:
        raise NotFoundException("Doctor no encontrado", code="DOCTOR_NOT_FOUND")
    branch_id = office.branch_id  # DENORM derivado del office
    branch = await branch_repository.get_by_id(db, branch_id)
    if branch is None:
        raise NotFoundException("Sede no encontrada", code="BRANCH_NOT_FOUND")

    if not doctor.active:  # 0a, decisión #3
        raise BadRequestException("El doctor está inactivo", code="DOCTOR_INACTIVE")
    if product.vertical_id not in {v.id for v in office.verticals}:  # 2
        raise BadRequestException(
            "El consultorio no atiende esta vertical", code="OFFICE_NOT_APT_FOR_VERTICAL"
        )
    if branch_id not in {b.id for b in doctor.branches}:  # 3
        raise BadRequestException("El doctor no atiende en esta sede", code="DOCTOR_NOT_IN_BRANCH")
    if product.vertical_id not in {v.id for v in doctor.verticals}:  # 4
        raise BadRequestException(
            "El doctor no atiende esta vertical", code="DOCTOR_NOT_APT_FOR_VERTICAL"
        )

    duration_min = product.duration_min or doctor.slot_duration_min
    start = _as_utc(scheduled_for)
    end = start + timedelta(minutes=duration_min)

    if not await _fits_in_availability_block(db, doctor, office, branch, start, end):  # 7
        raise BadRequestException("No hay bloque de disponibilidad", code="NO_AVAILABILITY_BLOCK")
    if not await _office_open(db, office, branch, start, end):  # 8
        raise BadRequestException("El consultorio está cerrado", code="OFFICE_CLOSED")

    # En el path de booking (for_update=True), serializar contra creates concurrentes del
    # mismo doctor/office ANTES de leer el solape (FOR UPDATE no cubre el slot vacío).
    if for_update:
        await _acquire_booking_locks(db, doctor_id, office_id)
    blocking = await _resolve_blocking_status_ids(db)
    if await _has_overlap(
        db, "doctor", doctor_id, start, end, blocking, exclude_id, for_update
    ):  # 5
        raise ConflictException("El horario ya está ocupado", code="SLOT_TAKEN")
    if await _has_overlap(
        db, "office", office_id, start, end, blocking, exclude_id, for_update
    ):  # 6
        raise ConflictException("El consultorio ya está ocupado", code="OFFICE_SLOT_TAKEN")

    return BookingContext(
        product=product,
        office=office,
        doctor=doctor,
        branch=branch,
        branch_id=branch_id,
        duration_min=duration_min,
    )


async def check_slot(
    db: AsyncSession, *, doctor_id: str, office_id: str, product_id: str, scheduled_for: datetime
) -> CheckSlotResponse:
    """Revalida UN slot puntual (dry-run de los invariantes, sin FOR UPDATE ni crear).
    Solo captura BadRequest/Conflict (los 9 codes de invariante de CheckSlotReason); un
    NotFoundException (id inexistente) PROPAGA como 404 — un id borrado no es "ocupado",
    y mantiene el `reason` dentro de la unión del contrato TS."""
    try:
        await validate_booking_invariants(
            db,
            doctor_id=doctor_id,
            office_id=office_id,
            product_id=product_id,
            scheduled_for=scheduled_for,
            exclude_id=None,
            for_update=False,
        )
        return CheckSlotResponse(available=True, reason=None)
    except (BadRequestException, ConflictException) as exc:
        return CheckSlotResponse(available=False, reason=getattr(exc, "code", None))
