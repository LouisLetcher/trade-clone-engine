# Trade Clone Engine

Modular copy-trading engine to follow configured wallets, detect their DEX swaps on EVM chains, and (optionally) mirror those trades. Built with Python, FastAPI, SQLAlchemy, and Web3. Docker Compose makes it easy to deploy to cloud.

Important: This repository is for educational purposes only. Nothing here is financial advice. The project defaults to dry-run execution. Copy-trading carries significant financial and technical risk. Use at your own risk.

## Features

- Follow configurable wallets and watch their DEX swaps
- EVM chain support (Ethereum/Base) with Uniswap V2/V3 decoding
- Persist observations and executions in Postgres
- Executor service (dry-run by default) to mirror trades
- Uniswap V2 and V3 (exactInputSingle) execution with approvals, slippage, copy ratio, gas controls
- Optional aggregator routing via 1inch or 0x for best price
- FastAPI service for health, trades list, executions, and simple summary
- Docker Compose for local and cloud deployment

## Quick Start

1. Copy `.env.example` to `.env` and set a WebSocket RPC URL.

```sh
cp .env.example .env
```

1. Configure wallets to follow in `config/wallets.yaml` (gitignored). Start from the example:

```sh
cp config/wallets.example.yaml config/wallets.yaml
```

1. Build and start services:

```sh
docker compose up --build
```

1. API available at `http://localhost:8000` with endpoints: `/health`, `/trades`, `/executions`, `/summary`. A simple dashboard is also available at `/dashboard`.
   DB migrations run automatically in each service container via Alembic. To avoid race conditions, only one service should run migrations; this repo sets `TCE_RUN_MIGRATIONS=true` on the `api` service.

## Configuration

Environment variables (prefixed `TCE_`):

- `TCE_DATABASE_URL`: SQLAlchemy URL, defaults to Postgres in Compose
- `TCE_EVM_RPC_WS_URL`: EVM WebSocket RPC URL
- `TCE_EVM_CHAIN_ID`: EVM chain id (1=Ethereum, 8453=Base)
- `TCE_DRY_RUN`: `true|false` to control executor behavior
- `TCE_EVM_PRIVATE_KEY`: Private key for executing copy trades (required when dry-run is false)
- `TCE_EXECUTOR_ADDRESS`: Optional address override (derived from key if not set)
- `TCE_SLIPPAGE_BPS`: Slippage in basis points (e.g., 300 = 3%)
- `TCE_COPY_RATIO`: Fraction of observed amount to mirror (e.g., 0.2 for 20%)
- `TCE_MAX_NATIVE_IN_WEI`: Cap for native input on ETH->token swaps (0 to disable)
- `TCE_TX_DEADLINE_SECONDS`: Seconds until swap deadline
- `TCE_MAX_PRIORITY_FEE_GWEI` / `TCE_MAX_FEE_GWEI`: Optional EIP-1559 overrides
- `TCE_LOG_LEVEL`: Log level (`INFO`, `DEBUG`)
- Aggregators: set `TCE_AGGREGATOR` to `1inch` or `0x`; configure `TCE_ONEINCH_*` or `TCE_ZEROEX_*` URLs/keys as needed.
- Solana RPC: `TCE_SOL_RPC_URL` (watcher scaffold only, not enabled by default).

Wallets live in `config/wallets.yaml`:

```yaml
wallets:
  - chain: evm
    address: "0x..."
    notes: "Label for this wallet"
    copy_ratio: 0.2
    slippage_bps: 300
    max_native_in_wei: 0
    allowed_tokens: []
    denied_tokens: []
```

## Services

- `postgres`: database for trades
- `watcher`: scans new blocks for swaps by followed wallets
- `executor`: simulates or mirrors trades (dry-run by default)
- `api`: exposes simple endpoints for monitoring and serves a lightweight dashboard at `/dashboard` (dark UI).
Note: Solana watcher/executor are scaffolded and not enabled by default.

### Running Ethereum + Polygon concurrently

- Watchers:
  - Ethereum: `docker compose up --build watcher`
  - Polygon: `docker compose up --build watcher_polygon` (set `TCE_POLYGON_EVM_RPC_WS_URL` in `.env`)
- Executors:
  - Ethereum: `docker compose up --build executor`
  - Polygon: `docker compose up --build executor_polygon` (uses `TCE_POLYGON_EVM_RPC_WS_URL`)

Ensure `config/wallets.yaml` includes the wallets you want to follow on each chain. Set `TCE_EVM_RPC_WS_URL` and `TCE_POLYGON_EVM_RPC_WS_URL` appropriately (e.g., your Alchemy WS URLs).

## Configured DEX Routers

Below are the pre-configured router addresses per chain (you can extend in `trade_clone_engine/config.py`).

- Ethereum (1):
  - Uniswap V2: `0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D`
  - Uniswap V3: `0xE592427A0AEce92De3Edee1F18E0157C05861564`
- Polygon (137):
  - Uniswap V3: `0xE592427A0AEce92De3Edee1F18E0157C05861564`
  - QuickSwap V2: `0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff`
  - SushiSwap V2: `0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506`
- Base (8453):
  - Uniswap V3: `0x2626664c2603336E57B271c5C0b26F421741e481`

## Clean Code & Structure

- Monorepo with a shared library package: `trade_clone_engine`.
- Clear separation of concerns: config, chains (watchers), execution, analytics.
- Simple DB models with SQLAlchemy and context-managed sessions.
- Minimal decoding via Uniswap V2/V3 ABIs for basic swap detection.
- Per-wallet overrides via `config/wallets.yaml` (copy ratio, slippage, caps, token allow/deny).
- Alembic-managed schema with automatic migrations on container start.

## Extending

- Add more chains by creating new adapters in `trade_clone_engine/chains/`.
- Add more DEX routers to `trade_clone_engine/config.py`.
- Aggregators: optional integration with 1inch/0x can be added later.
- Implement Solana watcher with Jupiter routing and Serum/Raydium logs.
- Add more analytics (realized PnL per wallet, per token) and dashboards.

## Local Development

- Python: use Python 3.11 (project supports ">=3.10,<3.13").
- Poetry (recommended):
  - `poetry env use 3.11`
  - `poetry install`
  - `poetry run pre-commit install`
  - `poetry run pytest -q`
  - Run stack: `docker compose up --build`
- Without Poetry:
  - `python3.11 -m venv .venv && source .venv/bin/activate`
  - `pip install -e .`
  - `pip install pre-commit && pre-commit install`
  - `pytest -q`

## Solana Watching Modes

- Subscription (default): Runs `solana_watcher_subscribe` which uses WebSocket log subscriptions for near real-time detection and token delta decoding.
  - Start with: `docker compose up --build solana_watcher_subscribe`
- Polling (opt-in): Runs `solana_watcher` which polls recent signatures. Useful when WS access is constrained.
  - Start with: `docker compose --profile polling up --build solana_watcher`

Add Solana wallets in `config/wallets.yaml` with `chain: solana` and the address.

## Discovery

- Sources: Nansen (requires `TCE_NANSEN_API_KEY`), GMGN (best-effort), Birdeye (set `TCE_BIRDEYE_API_KEY`).
- Configure:
  - `TCE_NANSEN_BASE_URL` (e.g., `https://api.nansen.ai/api/v1`)
  - `TCE_NANSEN_ENDPOINT_PATH` (e.g., `smart-money/top-traders?timeRange=7d` or `smart-money/dex-trades?timeRange=24h`)
  - `TCE_DISCOVER_CHAIN` to limit to one chain (e.g., `solana`)
  - `TCE_DISCOVER_INTERVAL_SEC` for schedule, or set `TCE_DISCOVER_ONCE=true` to run once
  - `TCE_DISCOVER_PRUNE_OTHERS=true` to prune non-target chains in `wallets.yaml`
- Outputs: updates `config/wallets.yaml` with curated wallets and safe per-wallet defaults.

## Discovery Label Filters

- Discovery can filter candidates by labels (e.g., exclude contract/team/exchange wallets).
- Environment variables:
  - `TCE_DISCOVER_ALLOWED_LABELS`: comma-separated allowlist (e.g., `smart money,trader,whale`). If set, only wallets with at least one allowed label are kept.
  - `TCE_DISCOVER_DENIED_LABELS`: comma-separated denylist (e.g., `contract,team,exchange,cex,market-maker`). Any wallet with a denied label is dropped.
- Currently applied to Nansen source; other sources can be wired once their label/tag schemas are confirmed.
- Enhance analytics with price data (e.g., Coingecko) to compute PnL.

## Security Notes

- Never commit private keys; use secret managers or env vars.
- Rate-limit and validate all external RPC and API calls.
- Implement observability (metrics/tracing) before running in production.
