# ONLY YOGI — Free Dual-Mode Bitcoin Data Dashboard

A local Streamlit companion for the existing TradingView ONLY YOGI indicator. It includes both requested modes.

## Included modes

### Option B — Raw Blockchain (baseline)
- Binance USDⓈ-M Futures BTCUSDT public ticker
- Mempool.space current mempool backlog
- Latest block height and recent blocks
- Recommended mining fees
- Recent unconfirmed transaction sample
- Mining-pool block attribution over the trailing 24 hours

No exchange/miner wallet labels are applied. Mining-pool attribution is not miner-wallet flow or proof of selling.

### Option A — Tagged Wallets (partial labelled coverage)
Upload a CSV with `entity`, `entity_type`, `address`; optional `source`, `confidence`.
The app reads the latest transaction history page for up to 10 user-supplied addresses, deduplicates txids and calculates tagged input/output values and net tagged balance change.

This is only the addresses and transactions that you supply/receive. It is not a complete exchange/miner aggregate or a complete 24-hour ledger.

### Free Daily On-Chain
Manual BGeometrics free API calls for market cap, realized cap and active addresses. MVRV is derived only if market-cap and realized-cap observations have matching dates.

The free-plan documentation lists 8 requests/hour and 15 requests/day and excludes exchange/miner aggregate flow endpoints. This dashboard makes only three manual daily calls; do not repeatedly refresh to bypass limits.

## Important TradingView boundary

Pine Script cannot call arbitrary REST APIs or localhost endpoints. This is a separate local Streamlit companion to view beside TradingView. It does not inject live API data into the Pine indicator.

No BUY/SELL signal is generated. The existing ONLY YOGI signal remains disabled until feeds and methods are validated.

## Install on macOS

**Configured local address:** `http://localhost:8508`  
**Configured Streamlit port:** `8508`  

1. Download and unzip `ONLY_YOGI_FREE_DUAL_MODE_PORT_8508.zip`.
2. Open Terminal and change to the extracted folder. Alternatively, double-click `run_mac.command` to install dependencies and launch the app:

```bash
cd ~/Downloads/ONLY_YOGI_FREE_DUAL_MODE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py --server.port 8508
```

The included `.streamlit/config.toml` also sets port 8508 as the default. The launcher explicitly passes port 8508.  
3. Open `http://localhost:8508`.

## Option A CSV example

Use the blank `watchlist_template.csv` as a starting point:

```csv
entity,entity_type,address,source,confidence
```

Add real, documented public Bitcoin addresses. Example labels below are placeholders only:

```csv
Exchange Wallet A,exchange,REPLACE_WITH_REAL_BTC_ADDRESS,public_source_url,unverified
Mining Wallet A,miner,REPLACE_WITH_REAL_BTC_ADDRESS,public_source_url,unverified
```

Do not use addresses unless you can verify their source and label. Never upload seed phrases, private keys, exchange credentials or API secrets.

Option A is manual-refresh (not tick-by-tick). The Mempool.space address-history response is limited to up to 50 mempool transactions plus the first 25 confirmed transactions. Output is a sample of those returned transactions, not a guaranteed complete 24-hour window. Net balance change is tagged outputs minus tagged inputs. Internal transfers cancel in net only where both sides are present in the returned sample.

## API behaviour and refresh
- Raw network/market panel polls every 60 seconds (near-real-time, not tick-by-tick).
- Tagged-wallet mode is manual-refresh to reduce public API load.
- BGeometrics is manual-refresh and cached; three API calls per refresh.
- Public API services can change, delay, rate-limit or fail (HTTP 429). Wait and retry later.

## Data boundaries
- Binance public Futures market-data endpoint does not require an API key.
- Mempool.space REST endpoints are public but have usage limits.
- BGeometrics free tier gives daily metrics only; exchange and miner aggregate flow endpoints are paid.
- Option A labels are user-supplied and partial. Do not relabel these as total EX-IN / EX-OUT or MNR-IN / MNR-OUT.
