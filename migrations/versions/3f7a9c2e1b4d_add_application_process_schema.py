"""add_application_process_schema

Revision ID: 3f7a9c2e1b4d
Revises: 2b4c8a1e3f5d
Create Date: 2026-06-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3f7a9c2e1b4d"
down_revision: str | Sequence[str] | None = "2b4c8a1e3f5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "services",
        sa.Column("service_id", sa.String(length=64), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("icon", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("step2_title", sa.String(length=255), nullable=True),
        sa.Column("step2_lede", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.user_id"],
            name=op.f("fk_services_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("service_id", name=op.f("pk_services")),
        sa.UniqueConstraint("slug", name=op.f("uq_services_slug")),
    )
    op.create_table(
        "service_steps",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("service_id", sa.String(length=64), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.service_id"],
            name=op.f("fk_service_steps_service_id_services"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_steps")),
        sa.UniqueConstraint("service_id", "step_number", name="uq_service_steps_service_step"),
    )
    op.create_index("ix_service_steps_service_id", "service_steps", ["service_id"])
    op.create_table(
        "service_document_requirements",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("service_id", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("doc_type", sa.String(length=32), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_size_mb", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("allowed_mime_types", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.service_id"],
            name=op.f("fk_service_document_requirements_service_id_services"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_document_requirements")),
        sa.UniqueConstraint("service_id", "key", name="uq_service_doc_req_service_key"),
    )
    op.create_index(
        "ix_service_doc_req_service_id", "service_document_requirements", ["service_id"]
    )
    op.create_table(
        "service_form_fields",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("service_id", sa.String(length=64), nullable=False),
        sa.Column("field_key", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("field_type", sa.String(length=32), nullable=False),
        sa.Column("help_text", sa.Text(), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("conditional_on_field", sa.String(length=128), nullable=True),
        sa.Column("conditional_on_value", sa.String(length=255), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_length", sa.Integer(), nullable=True),
        sa.Column("placeholder", sa.String(length=255), nullable=True),
        sa.Column("card_id", sa.String(length=128), nullable=True),
        sa.Column("card_title", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.service_id"],
            name=op.f("fk_service_form_fields_service_id_services"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_form_fields")),
        sa.UniqueConstraint("service_id", "field_key", name="uq_service_form_fields_service_key"),
    )
    op.create_index("ix_service_form_fields_service_id", "service_form_fields", ["service_id"])
    op.create_table(
        "service_pricing_tiers",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("service_id", sa.String(length=64), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("platform_fee", sa.Integer(), nullable=False),
        sa.Column("government_fee", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("eta_business_days", sa.Integer(), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.service_id"],
            name=op.f("fk_service_pricing_tiers_service_id_services"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_service_pricing_tiers")),
        sa.UniqueConstraint("service_id", "tier", name="uq_service_pricing_tiers_service_tier"),
    )
    op.create_index("ix_service_pricing_tiers_service_id", "service_pricing_tiers", ["service_id"])
    op.create_table(
        "applications",
        sa.Column("application_id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("service_id", sa.String(length=64), nullable=False),
        sa.Column("service_slug", sa.String(length=128), nullable=False),
        sa.Column("service_name", sa.String(length=255), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("assigned_agent_id", sa.String(length=64), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("personal_info", sa.JSON(), nullable=False),
        sa.Column("service_data", sa.JSON(), nullable=False),
        sa.Column("payment_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("payment_amount", sa.Integer(), nullable=True),
        sa.Column("submission_ip", sa.String(length=64), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_agent_id"],
            ["users.user_id"],
            name=op.f("fk_applications_assigned_agent_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["users.user_id"],
            name=op.f("fk_applications_client_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.service_id"],
            name=op.f("fk_applications_service_id_services"),
        ),
        sa.PrimaryKeyConstraint("application_id", name=op.f("pk_applications")),
        sa.UniqueConstraint("code", name=op.f("uq_applications_code")),
    )
    op.create_index("ix_applications_client_id", "applications", ["client_id"])
    op.create_index("ix_applications_assigned_agent_id", "applications", ["assigned_agent_id"])
    op.create_index("ix_applications_status", "applications", ["status"])
    op.create_index("ix_applications_service_id", "applications", ["service_id"])
    op.create_index("ix_applications_submitted_at", "applications", ["submitted_at"])
    op.create_table(
        "application_status_history",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("application_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("changed_by", sa.String(length=64), nullable=True),
        sa.Column("changed_by_role", sa.String(length=32), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.application_id"],
            name=op.f("fk_application_status_history_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.user_id"],
            name=op.f("fk_application_status_history_changed_by_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_status_history")),
    )
    op.create_index(
        "ix_app_status_history_application_id",
        "application_status_history",
        ["application_id"],
    )
    op.create_table(
        "application_assignment_history",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("application_id", sa.String(length=64), nullable=False),
        sa.Column("previous_agent_id", sa.String(length=64), nullable=True),
        sa.Column("new_agent_id", sa.String(length=64), nullable=True),
        sa.Column("performed_by", sa.String(length=64), nullable=False),
        sa.Column("performed_by_role", sa.String(length=32), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.application_id"],
            name=op.f("fk_application_assignment_history_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["new_agent_id"],
            ["users.user_id"],
            name=op.f("fk_application_assignment_history_new_agent_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["performed_by"],
            ["users.user_id"],
            name=op.f("fk_application_assignment_history_performed_by_users"),
        ),
        sa.ForeignKeyConstraint(
            ["previous_agent_id"],
            ["users.user_id"],
            name=op.f("fk_application_assignment_history_previous_agent_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_assignment_history")),
    )
    op.create_index(
        "ix_app_assignment_history_application_id",
        "application_assignment_history",
        ["application_id"],
    )
    op.create_table(
        "agent_settings",
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("accepting_cases", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("daily_case_cap", sa.Integer(), nullable=True),
        sa.Column("notification_new_case", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notification_client_reply", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notification_sla_alert", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "notification_daily_summary", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            name=op.f("fk_agent_settings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_agent_settings")),
    )
    op.create_table(
        "application_documents",
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("application_id", sa.String(length=64), nullable=False),
        sa.Column("requirement_key", sa.String(length=128), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_role", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("qc_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("qc_notes", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("replaced_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.application_id"],
            name=op.f("fk_application_documents_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by"],
            ["application_documents.document_id"],
            name=op.f("fk_application_documents_replaced_by_application_documents"),
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.user_id"],
            name=op.f("fk_application_documents_uploaded_by_users"),
        ),
        sa.PrimaryKeyConstraint("document_id", name=op.f("pk_application_documents")),
    )
    op.create_index("ix_application_documents_application_id", "application_documents", ["application_id"])
    op.create_index(
        "ix_application_documents_active_req",
        "application_documents",
        ["application_id", "requirement_key"],
    )
    op.create_table(
        "application_messages",
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("application_id", sa.String(length=64), nullable=False),
        sa.Column("sender_id", sa.String(length=64), nullable=True),
        sa.Column("sender_role", sa.String(length=32), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attachments", sa.JSON(), nullable=False),
        sa.Column("is_read_by_client", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read_by_agent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.application_id"],
            name=op.f("fk_application_messages_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"],
            ["users.user_id"],
            name=op.f("fk_application_messages_sender_id_users"),
        ),
        sa.PrimaryKeyConstraint("message_id", name=op.f("pk_application_messages")),
    )
    op.create_index("ix_application_messages_application_id", "application_messages", ["application_id"])


def downgrade() -> None:
    op.drop_index("ix_application_messages_application_id", table_name="application_messages")
    op.drop_table("application_messages")
    op.drop_index("ix_application_documents_active_req", table_name="application_documents")
    op.drop_index("ix_application_documents_application_id", table_name="application_documents")
    op.drop_table("application_documents")
    op.drop_table("agent_settings")
    op.drop_index("ix_app_assignment_history_application_id", table_name="application_assignment_history")
    op.drop_table("application_assignment_history")
    op.drop_index("ix_app_status_history_application_id", table_name="application_status_history")
    op.drop_table("application_status_history")
    op.drop_index("ix_applications_submitted_at", table_name="applications")
    op.drop_index("ix_applications_service_id", table_name="applications")
    op.drop_index("ix_applications_status", table_name="applications")
    op.drop_index("ix_applications_assigned_agent_id", table_name="applications")
    op.drop_index("ix_applications_client_id", table_name="applications")
    op.drop_table("applications")
    op.drop_index("ix_service_pricing_tiers_service_id", table_name="service_pricing_tiers")
    op.drop_table("service_pricing_tiers")
    op.drop_index("ix_service_form_fields_service_id", table_name="service_form_fields")
    op.drop_table("service_form_fields")
    op.drop_index("ix_service_doc_req_service_id", table_name="service_document_requirements")
    op.drop_table("service_document_requirements")
    op.drop_index("ix_service_steps_service_id", table_name="service_steps")
    op.drop_table("service_steps")
    op.drop_table("services")
