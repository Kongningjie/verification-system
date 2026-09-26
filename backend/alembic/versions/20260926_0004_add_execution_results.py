"""add evidence, execution runs, and system results

Revision ID: 20260926_0004
Revises: 20260926_0003
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260926_0004"
down_revision: str | Sequence[str] | None = "20260926_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("check_item_id", sa.String(36), nullable=False),
        sa.Column("evidence_id", sa.String(80), nullable=False),
        sa.Column("file_id", sa.String(36), nullable=True),
        sa.Column("role", sa.String(31), nullable=False),
        sa.Column("source_category", sa.String(31), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(31), nullable=False),
        sa.Column("locator", sa.JSON(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("asset_path", sa.String(512), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["verification_task.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["task_file.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "evidence_id", name="uq_evidence_task_stable"),
    )
    op.create_index("ix_evidence_task_id", "evidence", ["task_id"])
    op.create_index("ix_evidence_check_item_id", "evidence", ["check_item_id"])
    op.create_table(
        "check_result",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("check_item_id", sa.String(36), nullable=False),
        sa.Column("check_name", sa.String(255), nullable=False),
        sa.Column("check_type", sa.String(31), nullable=False),
        sa.Column("executor_type", sa.String(31), nullable=False),
        sa.Column("severity", sa.String(31), nullable=False),
        sa.Column("system_conclusion", sa.String(31), nullable=False),
        sa.Column("final_conclusion", sa.String(31), nullable=False),
        sa.Column("reason_code", sa.String(63), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("has_manual_override", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["verification_task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "check_item_id", name="uq_result_task_item"),
    )
    op.create_index("ix_check_result_task_id", "check_result", ["task_id"])
    op.create_index("ix_check_result_check_item_id", "check_result", ["check_item_id"])
    op.create_table(
        "check_run",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("check_item_id", sa.String(36), nullable=False),
        sa.Column("result_id", sa.String(36), nullable=True),
        sa.Column("run_type", sa.String(31), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("executor_type", sa.String(31), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("conclusion", sa.String(31), nullable=True),
        sa.Column("reason_code", sa.String(63), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("differences", sa.JSON(), nullable=False),
        sa.Column("missing_information", sa.JSON(), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["verification_task.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["result_id"], ["check_result.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_check_run_task_id", "check_run", ["task_id"])
    op.create_index("ix_check_run_check_item_id", "check_run", ["check_item_id"])


def downgrade() -> None:
    op.drop_index("ix_check_run_check_item_id", table_name="check_run")
    op.drop_index("ix_check_run_task_id", table_name="check_run")
    op.drop_table("check_run")
    op.drop_index("ix_check_result_check_item_id", table_name="check_result")
    op.drop_index("ix_check_result_task_id", table_name="check_result")
    op.drop_table("check_result")
    op.drop_index("ix_evidence_task_id", table_name="evidence")
    op.drop_index("ix_evidence_check_item_id", table_name="evidence")
    op.drop_table("evidence")
