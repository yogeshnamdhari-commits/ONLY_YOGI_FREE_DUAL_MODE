# ONLY YOGI Free Dual-Mode Dashboard — Build and Data-Source Audit

**Build:** 1.0  
**Date:** 3 November 2026  
**Status:** App source syntax-compiles; live third-party API integration has not been run in this offline build environment.

## Dual-mode behaviour

### Option B — Raw Blockchain
- Binance USDⓈ-M Futures public `GET /fapi/v2/ticker/price` for BTCUSDT perpetual.
- Mempool.space REST endpoints for mempool backlog, tip height, recent blocks, recommended fees, recent mempool transactions and 24-hour mining pool block attribution.
- Raw mode refreshes every 60 seconds using Streamlit fragments and endpoint-specific caching.
- No entity or exchange wallet labels are added.
- Mining-pool attribution indicates tagged block production, not miner wallet inflow/outflow or selling.

### Option A — Tagged Wallets
- User uploads public BTC addresses and their entity labels.
- The app fetches the latest address transaction page for up to 10 addresses on manual refresh.
- It deduplicates transactions by txid.
- For each entity, it sums inputs from tagged addresses and outputs to tagged addresses.
- Net change = tagged outputs − tagged inputs.
- Duplicate address assignments across different entities are rejected to prevent double counting.
- Mempool.space documents an address-history response of up to 50 mempool transactions plus the first 25 confirmed transactions. Therefore, the result is a limited returned-page sample, not a full 24-hour ledger and not a complete exchange/miner aggregate.
- No example or guessed exchange/miner wallet addresses are preloaded.

### Daily On-Chain
- The app uses BGeometrics free-plan endpoints: `/v1/market-cap/last`, `/v1/realized-cap/last`, `/v1/active-addresses/last`.
- It makes three requests only after a manual click and caches responses for six hours.
- It derives MVRV only when market-cap and realized-cap latest records have the same date.
- The official free-plan feature list states 8 requests/hour and 15 requests/day, and explicitly lists exchange and miner flow metrics as Advanced-only. The app does not call those paid endpoints.

## Important integration boundary

The app is a local Streamlit companion and does not inject arbitrary external REST data into Pine Script. TradingView Pine Script requests symbols exposed by TradingView; it cannot issue arbitrary REST calls to localhost or these services. The Streamlit view should be kept open beside the TradingView indicator.

## Static validation
- Python source compiled with Python's built-in `compile()` function: PASS.
- Third-party imports and Streamlit runtime were not launched in this environment.
- No HTTP/API calls were executed from the generated artifact environment.
- No live API availability, response schema, rate limit, or data freshness has been certified by this build.
- The app displays source API errors rather than silently substituting values.

## Known limitations
1. Option A is partial address coverage. Wallet label quality and completeness are user responsibility.
2. Address-history pages can truncate active addresses; no claim of full-day flow completeness is made.
3. Option A is manual refresh to reduce API load. It is not a tick-by-tick stream.
4. Option B polls public data every 60 seconds. It is near-real-time polling, not a tick stream.
5. BGeometrics free metrics are daily updated, not a real-time feed. Its API usage quotas are strict.
6. Public endpoints can change schema, impose rate limits, or become unavailable.
7. No BUY/SELL decision logic is included. These two data modes must first be validated before any trading signal is enabled.

## Official source references
- Binance public Futures market-data endpoint documentation: https://developers.binance.info/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data
- Binance market-data-only public endpoint FAQ: https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md
- Mempool.space REST API: https://mempool.space/docs/api/rest
- Mempool.space WebSocket API: https://mempool.space/docs/api/websocket
- BGeometrics free plan: https://bitcoin-data.com/bguser/free-features.html
- BGeometrics free API terms/rate limits: https://bgeometrics.com/terms/
- Freedom Street docs: https://docs.freedom.st/

