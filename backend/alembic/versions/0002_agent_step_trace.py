"""Add model and prompt version fields to agent traces."""

from alembic import op
import sqlalchemy as sa

revision = "0002_agent_step_trace"
down_revision = "0001_initial_and_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_steps", sa.Column("model_version", sa.String(length=64), nullable=False, server_default=""))
    op.add_column("agent_steps", sa.Column("prompt_version", sa.String(length=64), nullable=False, server_default=""))
    op.add_column("agent_steps", sa.Column("error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_steps", "error_message")
    op.drop_column("agent_steps", "prompt_version")
    op.drop_column("agent_steps", "model_version")
