from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "wallet_follows",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("address", sa.String(64), index=True),
        sa.Column("chain", sa.String(16), default="evm"),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "observed_trades",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("chain", sa.String(16), index=True),
        sa.Column("tx_hash", sa.String(80), index=True),
        sa.Column("block_number", sa.Integer),
        sa.Column("wallet", sa.String(64), index=True),
        sa.Column("dex", sa.String(64)),
        sa.Column("method", sa.String(64)),
        sa.Column("token_in", sa.String(64)),
        sa.Column("token_out", sa.String(64)),
        sa.Column("amount_in_wei", sa.String(80)),
        sa.Column("min_out_wei", sa.String(80)),
        sa.Column("raw_input", sa.Text),
        sa.Column("timestamp", sa.DateTime, nullable=False),
        sa.Column("processed", sa.Boolean, default=False, index=True),
    )
    op.create_table(
        "executed_trades",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("observed_trade_id", sa.Integer, sa.ForeignKey("observed_trades.id"), index=True),
        sa.Column("status", sa.String(32), default="skipped"),
        sa.Column("tx_hash", sa.String(80), index=True),
        sa.Column("gas_spent_wei", sa.String(80)),
        sa.Column("error", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("token_in", sa.String(64), index=True),
        sa.Column("token_out", sa.String(64), index=True),
        sa.Column("amount_in_wei", sa.String(80)),
        sa.Column("amount_out_wei", sa.String(80)),
        sa.Column("amount_in_usd", sa.Float),
        sa.Column("amount_out_usd", sa.Float),
        sa.Column("pnl_usd", sa.Float),
        sa.Column("realized_at", sa.DateTime),
    )


def downgrade():
    op.drop_table("executed_trades")
    op.drop_table("observed_trades")
    op.drop_table("wallet_follows")
