# ONLY YOGI — Bitcoin Data Dashboard (master)

The default `master` branch currently contains the **Free Dual-Mode Bitcoin Data Dashboard 1.0**. The optional **Signal Engine v2.0.1** is distributed separately as a versioned ZIP bundle under `releases/v2.0.1/`.

This distinction is intentional: merge commit `4b4f5f41bf8031ae1334b42906f060b1f660f1d1` added the v2.0.1 release bundle and CI workflow, while preserving the original root `app.py`. The v2.0.1 signal engine is not the root dashboard entry point.

## Current master dashboard — Dual-mode raw/tagged Bitcoin data

### Option B — Raw Blockchain (baseline)
- Binance USDⓈ-M Futures BTCUSDT public ticker
- Mempool.space current mempool backlog
- Latest block height and recent blocks
- Recommended mining fees
- Recent unconfirmed transaction sample
- Mining-pool block attribution over the trailing 24 hours

No exchange/miner wallet labels are applied. Mining-pool block attribution is not miner-wallet flow or proof of selling.

### Option A — Tagged Wallets (partial labelled coverage)
Upload a CSV with `entity`, `entity_type`, `address`; optional `source`, `confidence`.
The app reads the latest transaction history page for up to 10 user-supplied addresses, deduplicates txids and calculates tagged input/output values and net tagged balance change.

This is only the addresses and transactions that you supply/receive. It is not a complete exchange/miner aggregate or a complete 24-hour ledger.

### Free Daily On-Chain
Manual BGeometrics free API calls for market cap, realized cap and active addresses. MVRV is derived only if market-cap and realized-cap observations have matching dates.

## TradingView boundary
Pine Script cannot call arbitrary REST APIs or localhost endpoints. This is a separate local Streamlit companion to view beside TradingView. It does not inject live API data into the Pine indicator.

The root dual-mode dashboard does not generate a validated BUY/SELL signal.

## Port and install — master dashboard

**Configured local address:** `http://localhost:8508`  
**Configured Streamlit port:** `8508`

```bash
git clone https://github.com/yogeshnamdhari-commits/ONLY_YOGI_FREE_DUAL_MODE.git
cd ONLY_YOGI_FREE_DUAL_MODE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py --server.port 8508
```

Open `http://localhost:8508`.

## Optional Signal Engine v2.0.1 release bundle

This is a separate release package, not the root app on `master`.

1. Clone or pull the repository's `master` branch.
2. Reconstruct the v2.0.1 ZIP:

```bash
bash releases/v2.0.1/assemble_bundle.command
```

3. Follow [the v2.0.1 release README](releases/v2.0.1/README.md) to unzip it into a separate directory, install dependencies and run its included tests.
4. The v2.0.1 app is separately launched on `http://localhost:8508`; stop the root dashboard first if it already occupies that port, or choose another unused port.

Release archive SHA-256:
`5f2381e825c7c4886152ccd35852ebf8f5a119ed301099b96f0aefd08e8148ac`

**Signal limitations:** The v2.0.1 rules are provisional and not evidence of profitability. The package is read-only and does not place orders. Missing, stale, malformed or date-misaligned inputs should result in WAIT. The free raw blockchain feed does not establish total labelled exchange/miner flows.

## Option A CSV format

```csv
entity,entity_type,address,source,confidence
```

Use only real, documented public Bitcoin addresses. Never upload seed phrases, private keys, exchange credentials or API secrets.
