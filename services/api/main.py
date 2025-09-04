from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select

from trade_clone_engine.analytics.metrics import get_summary
from trade_clone_engine.config import AppSettings
from trade_clone_engine.db import ExecutedTrade, ObservedTrade, make_session_factory

app = FastAPI(title="Trade Clone Engine API")
settings = AppSettings()
SessionFactory = make_session_factory(settings.database_url)

# Static dashboard
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    p = static_dir / "dashboard.html"
    if not p.exists():
        return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)
    return HTMLResponse(p.read_text())


class TradeOut(BaseModel):
    id: int
    chain: str
    tx_hash: str
    block_number: int
    wallet: str
    dex: str | None
    method: str | None
    token_in: str | None
    token_out: str | None
    amount_in_wei: str | None
    min_out_wei: str | None
    processed: bool

    @classmethod
    def from_model(cls, m: ObservedTrade):
        return cls(
            id=m.id,
            chain=m.chain,
            tx_hash=m.tx_hash,
            block_number=m.block_number,
            wallet=m.wallet,
            dex=m.dex,
            method=m.method,
            token_in=m.token_in,
            token_out=m.token_out,
            amount_in_wei=m.amount_in_wei,
            min_out_wei=m.min_out_wei,
            processed=m.processed,
        )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/trades")
def list_trades(limit: int = 50):
    from trade_clone_engine.db import session_scope

    with session_scope(SessionFactory) as s:
        rows = (
            s.execute(select(ObservedTrade).order_by(ObservedTrade.id.desc()).limit(limit))
            .scalars()
            .all()
        )
        return [TradeOut.from_model(r).model_dump() for r in rows]


class ExecutionOut(BaseModel):
    id: int
    observed_trade_id: int
    status: str
    tx_hash: str | None
    gas_spent_wei: str | None
    error: str | None

    @classmethod
    def from_model(cls, m: ExecutedTrade):
        return cls(
            id=m.id,
            observed_trade_id=m.observed_trade_id,
            status=m.status,
            tx_hash=m.tx_hash,
            gas_spent_wei=m.gas_spent_wei,
            error=m.error,
        )


@app.get("/executions")
def list_executions(limit: int = 50):
    from trade_clone_engine.db import session_scope

    with session_scope(SessionFactory) as s:
        rows = (
            s.execute(select(ExecutedTrade).order_by(ExecutedTrade.id.desc()).limit(limit))
            .scalars()
            .all()
        )
        return [ExecutionOut.from_model(r).model_dump() for r in rows]


@app.get("/summary")
def summary():
    s = get_summary(SessionFactory)
    return s.__dict__


@app.get("/pnl")
def pnl_summary():
    from trade_clone_engine.db import session_scope

    with session_scope(SessionFactory) as s:
        total = s.scalar(
            select(func.coalesce(func.sum(ExecutedTrade.pnl_usd), 0.0)).where(
                ExecutedTrade.status == "success"
            )
        )
        rows = s.execute(
            select(ObservedTrade.wallet, func.coalesce(func.sum(ExecutedTrade.pnl_usd), 0.0))
            .join(ExecutedTrade, ExecutedTrade.observed_trade_id == ObservedTrade.id)
            .where(ExecutedTrade.status == "success")
            .group_by(ObservedTrade.wallet)
        ).all()
        return {
            "total_pnl_usd": float(total or 0.0),
            "by_wallet": {w: float(v or 0.0) for w, v in rows},
        }
