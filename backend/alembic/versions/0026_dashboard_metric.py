"""add dashboard rollup + refresh state + source indices (módulo dashboards, Fase 1)

Revision ID: 0026_dashboard_metric
Revises: 0025_calendar_connection
Create Date: 2026-06-24 00:00:00

Crea `dashboard_daily_metric` (PK·A·T — el rollup diario, UNIQUE por grano + índice de cobertura)
+ `dashboard_refresh_state` (PK·A·T — singleton de observabilidad). Ambas SIN SoftDelete (derivadas
del rollup, idempotentes). Agrega índices ADITIVOS en las columnas temporales de las tablas fuente
que el job de refresh escanea por fecha (hoy no indexadas): lead_status_history.changed_at,
conversation.opened_at, person_customer_status.became_customer_at. (NO se indexa person.created_on:
ninguna métrica del rollup lo usa — customers_new va por became_customer_at.) appointment YA tiene
(branch_id, scheduled_for, status_id) → no se toca. Tablas nuevas vacías + índices aditivos → sin FK
huérfana ni constraint sobre datos pre-existentes (a diferencia de la lección §20 de marketing).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_dashboard_metric"
down_revision: str | None = "0025_calendar_connection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── dashboard_daily_metric (PK·A·T, sin SoftDelete) ──
    op.create_table(
        "dashboard_daily_metric",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("metric_date", sa.Date(), nullable=False),
        sa.Column(
            "branch_id", sa.String(length=36), nullable=True
        ),  # FK lógica (ADR-009), sin constraint
        sa.Column("metric", sa.String(length=40), nullable=False),
        sa.Column("segment", sa.String(length=60), nullable=True),
        sa.Column("count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("value", sa.Numeric(precision=14, scale=6), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )
    op.create_unique_constraint(
        "uq_dashboard_daily_metric_grain",
        "dashboard_daily_metric",
        ["metric_date", "branch_id", "metric", "segment"],
    )
    op.create_index(
        "ix_dashboard_daily_metric_lookup",
        "dashboard_daily_metric",
        ["metric", "metric_date", "branch_id"],
    )

    # ── dashboard_refresh_state (PK·A·T, singleton) ──
    op.create_table(
        "dashboard_refresh_state",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_days", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ok"),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
    )

    # ── Índices ADITIVOS en las tablas fuente (acelerar el escaneo por fecha del job) ──
    op.create_index("ix_lead_status_history_changed_at", "lead_status_history", ["changed_at"])
    op.create_index("ix_conversation_opened_at", "conversation", ["opened_at"])
    op.create_index(
        "ix_person_customer_status_became_at", "person_customer_status", ["became_customer_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_person_customer_status_became_at", table_name="person_customer_status")
    op.drop_index("ix_conversation_opened_at", table_name="conversation")
    op.drop_index("ix_lead_status_history_changed_at", table_name="lead_status_history")
    op.drop_table("dashboard_refresh_state")
    op.drop_index("ix_dashboard_daily_metric_lookup", table_name="dashboard_daily_metric")
    op.drop_constraint("uq_dashboard_daily_metric_grain", "dashboard_daily_metric", type_="unique")
    op.drop_table("dashboard_daily_metric")
