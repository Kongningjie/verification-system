"""add generated checklists and immutable versions

Revision ID: 20260926_0003
Revises: 20260926_0002
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260926_0003"
down_revision: str | Sequence[str] | None = "20260926_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "verification_task",
        sa.Column("checklist_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "verification_task",
        sa.Column("confirmed_checklist_version", sa.Integer(), nullable=True),
    )
    op.create_table(
        "check_item",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=31), nullable=False),
        sa.Column("source_comment_id", sa.String(length=64), nullable=True),
        sa.Column("rule_id", sa.String(length=100), nullable=True),
        sa.Column("rule_version", sa.String(length=32), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.Column("check_type", sa.String(length=31), nullable=False),
        sa.Column("severity", sa.String(length=31), nullable=False),
        sa.Column("required_source_categories", sa.JSON(), nullable=False),
        sa.Column("target_hint", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("generation_warnings", sa.JSON(), nullable=False),
        sa.Column("source_comment_text", sa.Text(), nullable=True),
        sa.Column("source_selected_text", sa.Text(), nullable=True),
        sa.Column("source_heading_path", sa.JSON(), nullable=False),
        sa.Column("generation_metadata", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["verification_task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_check_item_task_id", "check_item", ["task_id"])
    op.create_index("ix_check_item_source_comment_id", "check_item", ["source_comment_id"])
    op.create_table(
        "checklist_version",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("ruleset_version", sa.String(length=32), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["verification_task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "version_number", name="uq_checklist_version_task_number"),
    )
    op.create_index("ix_checklist_version_task_id", "checklist_version", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_checklist_version_task_id", table_name="checklist_version")
    op.drop_table("checklist_version")
    op.drop_index("ix_check_item_source_comment_id", table_name="check_item")
    op.drop_index("ix_check_item_task_id", table_name="check_item")
    op.drop_table("check_item")
    op.drop_column("verification_task", "confirmed_checklist_version")
    op.drop_column("verification_task", "checklist_revision")
