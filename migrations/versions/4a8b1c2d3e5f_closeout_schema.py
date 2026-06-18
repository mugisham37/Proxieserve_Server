"""closeout_schema

Revision ID: 4a8b1c2d3e5f
Revises: 3f7a9c2e1b4d
Create Date: 2026-06-18 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4a8b1c2d3e5f"
down_revision: str | Sequence[str] | None = "3f7a9c2e1b4d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_service_skills",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("service_category", sa.String(length=64), nullable=False),
        sa.Column("proficiency_level", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "proficiency_level >= 1 AND proficiency_level <= 5",
            name="ck_agent_service_skills_proficiency_level",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["users.user_id"],
            name=op.f("fk_agent_service_skills_agent_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_service_skills")),
        sa.UniqueConstraint(
            "agent_id",
            "service_category",
            name="uq_agent_service_skills_agent_category",
        ),
    )
    op.create_index(
        "ix_agent_service_skills_agent_id",
        "agent_service_skills",
        ["agent_id"],
    )

    op.create_table(
        "payments",
        sa.Column("payment_id", sa.String(length=64), nullable=False),
        sa.Column("application_id", sa.String(length=64), nullable=False),
        sa.Column("amount_rwf", sa.Integer(), nullable=False),
        sa.Column("government_fee_rwf", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("platform_fee_rwf", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vat_rate", sa.Numeric(precision=4, scale=3), nullable=False, server_default="0.18"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="RWF"),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("provider_transaction_id", sa.String(length=256), nullable=True),
        sa.Column("receipt_number", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("card_brand", sa.String(length=16), nullable=True),
        sa.Column("masked_phone", sa.String(length=32), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.application_id"],
            name=op.f("fk_payments_application_id_applications"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("payment_id", name=op.f("pk_payments")),
        sa.UniqueConstraint("receipt_number", name=op.f("uq_payments_receipt_number")),
    )
    op.create_index("ix_payments_application_id", "payments", ["application_id"])
    op.create_index("ix_payments_status", "payments", ["status"])

    op.create_table(
        "application_escalations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("application_id", sa.String(length=64), nullable=False),
        sa.Column("escalated_by", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("oversight_status", sa.String(length=32), nullable=False, server_default="escalated"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=64), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.application_id"],
            name=op.f("fk_application_escalations_application_id_applications"),
        ),
        sa.ForeignKeyConstraint(
            ["escalated_by"],
            ["users.user_id"],
            name=op.f("fk_application_escalations_escalated_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.user_id"],
            name=op.f("fk_application_escalations_resolved_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_escalations")),
    )
    op.create_index(
        "ix_application_escalations_application_id",
        "application_escalations",
        ["application_id"],
    )
    op.create_index(
        "ix_application_escalations_oversight_status",
        "application_escalations",
        ["oversight_status"],
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("actor_role", sa.String(length=32), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.user_id"],
            name=op.f("fk_audit_log_actor_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index("ix_audit_log_actor_id", "audit_log", ["actor_id"])
    op.create_index("ix_audit_log_kind", "audit_log", ["kind"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    op.create_table(
        "broadcasts",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("audience_description", sa.String(length=255), nullable=False),
        sa.Column("audience_filter", sa.JSON(), nullable=False),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_reach", sa.Integer(), nullable=True),
        sa.Column("estimated_reach", sa.Integer(), nullable=True),
        sa.Column("broadcast_status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.user_id"],
            name=op.f("fk_broadcasts_created_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_broadcasts")),
    )

    op.create_table(
        "platform_settings",
        sa.Column("id", sa.String(length=16), nullable=False, server_default="global"),
        sa.Column("accept_new_apps", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("guest_apps", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("data_retention_months", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("enforce_2fa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("session_timeout_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("ip_allowlist", sa.Text(), nullable=True),
        sa.Column("maintenance_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.user_id"],
            name=op.f("fk_platform_settings_updated_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_settings")),
    )

    op.add_column(
        "applications",
        sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column("sla_breached_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("applications", "sla_breached_at")
    op.drop_column("applications", "sla_deadline")
    op.drop_table("platform_settings")
    op.drop_table("broadcasts")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index("ix_audit_log_kind", table_name="audit_log")
    op.drop_index("ix_audit_log_actor_id", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_application_escalations_oversight_status", table_name="application_escalations")
    op.drop_index("ix_application_escalations_application_id", table_name="application_escalations")
    op.drop_table("application_escalations")
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_application_id", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_agent_service_skills_agent_id", table_name="agent_service_skills")
    op.drop_table("agent_service_skills")
