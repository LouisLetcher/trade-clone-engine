-- Sample Dune SQL: EVM Meme Trader PnL (realized)
-- Adjust table names based on your chain and DEX coverage (Ethereum shown)
-- Outputs columns: wallet, realized_pnl_usd, win_rate, trades

WITH swaps AS (
  SELECT
    t.from AS wallet,
    t.hash AS tx_hash,
    t.block_time,
    -- Identify meme tokens via a maintained list/table, or heuristics (small FDV, tags)
    CASE WHEN tok.symbol ILIKE '%INU%' OR tok.symbol ILIKE '%PEPE%' THEN 1 ELSE 0 END AS is_meme,
    -- token amounts (simplified; use decoded event tables for accuracy)
    (ev_in.amount_raw) AS amount_in_raw,
    (ev_out.amount_raw) AS amount_out_raw,
    ev_in.token_address AS token_in,
    ev_out.token_address AS token_out
  FROM ethereum.traces t
  LEFT JOIN dex.trades ev_in ON ev_in.tx_hash = t.hash AND ev_in.side = 'sell'
  LEFT JOIN dex.trades ev_out ON ev_out.tx_hash = t.hash AND ev_out.side = 'buy'
  LEFT JOIN tokens.erc20 tok ON tok.contract_address = ev_out.token_address
  WHERE t.success = true
    AND t.block_time > now() - interval '30 days'
), priced AS (
  SELECT
    s.wallet,
    s.tx_hash,
    s.block_time,
    s.is_meme,
    s.amount_in_raw * p_in.price_usd / 1e18 AS amount_in_usd,
    s.amount_out_raw * p_out.price_usd / 1e18 AS amount_out_usd
  FROM swaps s
  LEFT JOIN prices.usd p_in ON p_in.contract_address = s.token_in AND p_in.minute = date_trunc('minute', s.block_time)
  LEFT JOIN prices.usd p_out ON p_out.contract_address = s.token_out AND p_out.minute = date_trunc('minute', s.block_time)
  WHERE s.is_meme = 1
), pnl AS (
  SELECT
    wallet,
    COUNT(*) AS trades,
    AVG(CASE WHEN amount_out_usd > amount_in_usd THEN 1 ELSE 0 END) AS win_rate,
    SUM(amount_out_usd - amount_in_usd) AS realized_pnl_usd
  FROM priced
  GROUP BY wallet
)
SELECT * FROM pnl ORDER BY realized_pnl_usd DESC;
