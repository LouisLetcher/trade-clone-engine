from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    ForeignKey,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session


class Base(DeclarativeBase):
    pass


class WalletFollow(Base):
    __tablename__ = "wallet_follows"

    id: Mapped[int] = mapped_column(primary_key=True)
    address: Mapped[str] = mapped_column(String(64), index=True)
    chain: Mapped[str] = mapped_column(String(16), default="evm")
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ObservedTrade(Base):
    __tablename__ = "observed_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    chain: Mapped[str] = mapped_column(String(16), index=True)
    tx_hash: Mapped[str] = mapped_column(String(80), index=True)
    block_number: Mapped[int] = mapped_column(Integer)
    wallet: Mapped[str] = mapped_column(String(64), index=True)
    dex: Mapped[str | None] = mapped_column(String(64))
    method: Mapped[str | None] = mapped_column(String(64))
    token_in: Mapped[str | None] = mapped_column(String(64))
    token_out: Mapped[str | None] = mapped_column(String(64))
    amount_in_wei: Mapped[str | None] = mapped_column(String(80))
    min_out_wei: Mapped[str | None] = mapped_column(String(80))
    raw_input: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    executions: Mapped[list[ExecutedTrade]] = relationship(back_populates="observed_trade")


class ExecutedTrade(Base):
    __tablename__ = "executed_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    observed_trade_id: Mapped[int] = mapped_column(ForeignKey("observed_trades.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="skipped")  # skipped|success|failed
    tx_hash: Mapped[str | None] = mapped_column(String(80), index=True)
    gas_spent_wei: Mapped[str | None] = mapped_column(String(80))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # PnL/amount tracking
    token_in: Mapped[str | None] = mapped_column(String(64), index=True)
    token_out: Mapped[str | None] = mapped_column(String(64), index=True)
    amount_in_wei: Mapped[str | None] = mapped_column(String(80))
    amount_out_wei: Mapped[str | None] = mapped_column(String(80))
    amount_in_usd: Mapped[float | None] = mapped_column()
    amount_out_usd: Mapped[float | None] = mapped_column()
    pnl_usd: Mapped[float | None] = mapped_column()
    realized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    observed_trade: Mapped[ObservedTrade] = relationship(back_populates="executions")


def make_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True, future=True)


def make_session_factory(database_url: str):
    engine = make_engine(database_url)
    # Migrations are managed via Alembic. We intentionally avoid create_all here.
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


@contextmanager
def session_scope(SessionFactory) -> Generator[Session, None, None]:
    session: Session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
