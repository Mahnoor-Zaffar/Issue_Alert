"""initial schema

Revision ID: 6a7a9b049e10
Revises:
Create Date: 2026-07-21 13:25:42.593586

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "6a7a9b049e10"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seen_issues",
        sa.Column("github_id", sa.Integer(), primary_key=True),
        sa.Column("first_seen_at", sa.Text(), nullable=False, server_default=sa.func.datetime("now")),
    )
    op.create_table(
        "issues",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("github_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("html_url", sa.Text(), nullable=False),
        sa.Column("repo_full_name", sa.Text(), nullable=False),
        sa.Column("repo_clone_url", sa.Text(), nullable=False),
        sa.Column("labels", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("language", sa.Text()),
        sa.Column("repo_stars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("bookmarked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dismissed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("viewed_at", sa.Text()),
        sa.Column("github_created_at", sa.Text()),
        sa.Column("comments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.Text(), nullable=False, server_default="open"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text()),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.func.datetime("now")),
        sa.Column("updated_at", sa.Text(), nullable=False, server_default=sa.func.datetime("now")),
    )
    op.create_table(
        "triage_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("issue_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("architecture_context", sa.Text()),
        sa.Column("issue_breakdown", sa.Text()),
        sa.Column("action_plan", sa.Text()),
        sa.Column("raw_response", sa.Text()),
        sa.Column("difficulty", sa.Text()),
        sa.Column("pr_url", sa.Text()),
        sa.Column("pr_head_sha", sa.Text()),
        sa.Column("pr_status", sa.Text()),
        sa.Column("pr_checked_at", sa.Text()),
        sa.Column("claim_comment", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.func.datetime("now")),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "triage_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("issue_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.func.datetime("now")),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "daily_stats",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("date", sa.Text(), nullable=False, unique=True),
        sa.Column("triaged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bookmarked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("polled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.func.datetime("now")),
    )
    op.create_table(
        "daemon_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.CheckConstraint("id = 1"),
        sa.Column("last_poll_at", sa.Text()),
        sa.Column("last_poll_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_poll_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_poll_total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_poll_message", sa.Text()),
        sa.Column("poll_requested", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.CheckConstraint("id = 1"),
        sa.Column("languages", sa.Text(), nullable=False, server_default='["javascript","python"]'),
        sa.Column("labels", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("min_stars", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("show_dismissed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "webhook_queue",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=sa.func.datetime("now")),
    )
    op.create_table(
        "priority_repos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner", sa.Text(), nullable=False),
        sa.Column("repo", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False, unique=True),
        sa.Column("added_at", sa.Text(), nullable=False, server_default=sa.func.datetime("now")),
    )
    op.create_index("idx_issues_status", "issues", ["status"])
    op.create_index("idx_issues_updated_at", "issues", ["updated_at"])
    op.create_index("idx_issues_github_id", "issues", ["github_id"])
    op.create_index("idx_webhook_queue_processed", "webhook_queue", ["processed"])
    op.create_index("idx_triage_requests_issue_id", "triage_requests", ["issue_id"], unique=True)


def downgrade() -> None:
    op.drop_table("priority_repos")
    op.drop_table("webhook_queue")
    op.drop_table("user_preferences")
    op.drop_table("daemon_state")
    op.drop_table("daily_stats")
    op.drop_table("triage_requests")
    op.drop_table("triage_reports")
    op.drop_table("issues")
    op.drop_table("seen_issues")
