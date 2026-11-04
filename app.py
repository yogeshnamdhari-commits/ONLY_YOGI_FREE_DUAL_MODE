
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests
import streamlit as st

APP_TITLE = "ONLY YOGI — Free Dual-Mode Bitcoin Data"
MEMPOOL = "https://mempool.space/api"
BINANCE_FUTURES = "https://fapi.binance.com"
BGEOMETRICS = "https://bitcoin-data.com/v1"
MAX_TAGGED_ADDRESSES = 10
HEADERS = {"User-Agent": "ONLY-YOGI-Free-Dual-Mode/1.0", "Accept": "application/json"}

st.set_page_config(page_title=APP_TITLE, page_icon="₿", layout="wide")
st.title("₿ ONLY YOGI — Free Dual-Mode Bitcoin Data")
st.markdown("**Local dashboard:** [http://localhost:8508](http://localhost:8508)")
st.caption("Option A: tagged wallet sample  |  Option B: raw Bitcoin network activity")

st.warning(
    "This is a local Streamlit companion to TradingView. Pine Script cannot call arbitrary REST APIs, "
    "so these external data are displayed here, not injected into your Pine indicator. "
    "BUY/SELL signals are deliberately not generated."
)

def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def api_get(url: str, params: dict | None = None, timeout: int = 12) -> Any:
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    if r.status_code == 429:
        raise RuntimeError("HTTP 429: public API rate limit reached. Wait before retrying.")
    r.raise_for_status()
    return r.json()

def number(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (ValueError, TypeError):
        return None

def btc(sats: int | float | None) -> str:
    return "—" if sats is None else f"{float(sats) / 100_000_000:,.8f} BTC"

def usd(v: float | None) -> str:
    return "—" if v is None else f"${v:,.2f}"

@st.cache_data(ttl=20, show_spinner=False)
def get_binance_perp():
    return api_get(f"{BINANCE_FUTURES}/fapi/v2/ticker/price", {"symbol": "BTCUSDT"})

@st.cache_data(ttl=60, show_spinner=False)
def get_mempool():
    return api_get(f"{MEMPOOL}/mempool")

@st.cache_data(ttl=60, show_spinner=False)
def get_tip_height():
    return int(api_get(f"{MEMPOOL}/blocks/tip/height"))

@st.cache_data(ttl=120, show_spinner=False)
def get_blocks(height: int):
    return api_get(f"{MEMPOOL}/blocks/{height}")

@st.cache_data(ttl=120, show_spinner=False)
def get_fees():
    return api_get(f"{MEMPOOL}/v1/fees/recommended")

@st.cache_data(ttl=120, show_spinner=False)
def get_recent_mempool_txs():
    return api_get(f"{MEMPOOL}/mempool/recent")

@st.cache_data(ttl=900, show_spinner=False)
def get_mining_pools():
    return api_get(f"{MEMPOOL}/v1/mining/pools/24h")

@st.cache_data(ttl=21600, show_spinner=False)
def get_bg_metric(endpoint: str):
    return api_get(f"{BGEOMETRICS}/{endpoint}/last")

def latest_record(payload: Any):
    if isinstance(payload, list):
        row = payload[-1] if payload and isinstance(payload[-1], dict) else {}
    elif isinstance(payload, dict):
        data = payload.get("data")
        row = data[-1] if isinstance(data, list) and data and isinstance(data[-1], dict) else payload
    else:
        row = {}
    date = row.get("d") or row.get("date") or row.get("day") or row.get("timestamp") or row.get("unixTs")
    value = None
    for k, v in row.items():
        if k in {"d", "date", "day", "timestamp", "unixTs", "id"}:
            continue
        value = number(v)
        if value is not None:
            break
    return (str(date) if date is not None else None, value, row)

@st.cache_data(ttl=300, show_spinner=False)
def get_address_txs(address: str):
    # Mempool.space address endpoint returns up to 50 mempool + first 25 confirmed txs.
    return api_get(f"{MEMPOOL}/address/{address}/txs")

def plausible_btc_address(address: str) -> bool:
    return bool(re.match(r"^(bc1[0-9a-z]{20,}|[13][a-km-zA-HJ-NP-Z1-9]{25,})$", address))

def parse_watchlist(upload) -> pd.DataFrame:
    if upload is None:
        return pd.DataFrame(columns=["entity", "entity_type", "address", "source", "confidence"])
    df = pd.read_csv(upload)
    required = {"entity", "entity_type", "address"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError("Missing CSV columns: " + ", ".join(sorted(missing)))
    for c in required:
        df[c] = df[c].astype(str).str.strip()
    df = df[(df["entity"] != "") & (df["address"] != "")].copy()
    # The same address must not be assigned to two different entities: that
    # would double-count value changes and corrupt per-entity totals.
    duplicated_across_entities = (
        df.groupby("address")["entity"].nunique().loc[lambda x: x > 1]
    )
    if not duplicated_across_entities.empty:
        raise ValueError(
            "These addresses are assigned to multiple entity labels: "
            + ", ".join(duplicated_across_entities.index.tolist())
            + ". Put all addresses for one cluster under one entity label."
        )
    df = df.drop_duplicates(subset=["entity", "address"]).copy()
    if "source" not in df:
        df["source"] = "user-supplied"
    if "confidence" not in df:
        df["confidence"] = "unverified"
    df["address_format"] = df["address"].map(lambda x: "plausible" if plausible_btc_address(x) else "check")
    return df

def aggregate_entity(addresses: set[str], txs: list[dict]):
    # Net monitored-address balance change = tagged outputs - tagged inputs.
    seen = set()
    ins = outs = count = internal = 0
    for tx in txs:
        txid = tx.get("txid")
        if not txid or txid in seen:
            continue
        seen.add(txid)
        input_sats = 0
        output_sats = 0
        for vin in tx.get("vin", []):
            prev = vin.get("prevout") or {}
            if prev.get("scriptpubkey_address") in addresses:
                input_sats += int(prev.get("value") or 0)
        for vout in tx.get("vout", []):
            if vout.get("scriptpubkey_address") in addresses:
                output_sats += int(vout.get("value") or 0)
        if input_sats or output_sats:
            count += 1
            ins += input_sats
            outs += output_sats
            if input_sats and output_sats:
                internal += 1
    return ins, outs, count, internal

@st.fragment(run_every=60)
def raw_live():
    st.subheader("Option B — Raw Bitcoin blockchain and market data")
    st.caption("No exchange/miner wallet labels are applied in this mode. Raw network activity is not exchange flow.")
    errors = []
    price = mem = tip = fees = blocks = recent = pools = None
    cols = st.columns(4)
    try:
        price = number(get_binance_perp().get("price"))
        cols[0].metric("BTCUSDT perpetual", usd(price))
    except Exception as e:
        errors.append(f"Binance Futures: {e}")
        cols[0].metric("BTCUSDT perpetual", "Unavailable")
    try:
        mem = get_mempool()
        cols[1].metric("Mempool transactions", f"{int(mem.get('count', 0)):,}")
        cols[2].metric("Mempool virtual size", f"{float(mem.get('vsize', 0))/1_000_000:,.2f} M vB")
    except Exception as e:
        errors.append(f"Mempool: {e}")
        cols[1].metric("Mempool transactions", "Unavailable")
        cols[2].metric("Mempool virtual size", "Unavailable")
    try:
        tip = get_tip_height()
        cols[3].metric("Latest block height", f"{tip:,}")
        blocks = get_blocks(tip)
    except Exception as e:
        errors.append(f"Blocks: {e}")
    try:
        fees = get_fees()
    except Exception as e:
        errors.append(f"Fee estimates: {e}")
    try:
        recent = get_recent_mempool_txs()
    except Exception as e:
        errors.append(f"Recent mempool txs: {e}")
    try:
        pools = get_mining_pools()
    except Exception as e:
        errors.append(f"Mining pool tags: {e}")

    st.caption(f"Last panel refresh: {utc_now()} · automatic refresh: 60 seconds")
    if fees:
        fc = st.columns(4)
        fc[0].metric("Fastest fee", f"{fees.get('fastestFee','—')} sat/vB")
        fc[1].metric("30-minute fee", f"{fees.get('halfHourFee','—')} sat/vB")
        fc[2].metric("1-hour fee", f"{fees.get('hourFee','—')} sat/vB")
        fc[3].metric("Economy fee", f"{fees.get('economyFee','—')} sat/vB")

    if mem:
        total_fee = number(mem.get("total_fee"))
        st.write(
            f"Pending virtual size: {float(mem.get('vsize',0)):,.0f} vB · "
            + (f"Reported pending fees: {total_fee:,.0f} sats" if total_fee is not None else "Pending fees: —")
        )

    if blocks:
        rows = []
        for b in blocks:
            extra = b.get("extras") or {}
            pool = extra.get("pool") or {}
            ts = b.get("timestamp")
            rows.append({
                "Height": b.get("height"),
                "UTC": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if ts else "—",
                "Transactions": b.get("tx_count"),
                "Size bytes": b.get("size"),
                "Pool tag": pool.get("name", "Unknown"),
                "Average fee sat/vB": extra.get("avgFee"),
            })
        st.markdown("**Recent confirmed blocks**")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if recent:
        rows = [{
            "Txid": t.get("txid"),
            "Value BTC": (number(t.get("value")) or 0) / 100_000_000,
            "Fee sats": t.get("fee"),
            "Virtual size": t.get("vsize"),
        } for t in recent]
        st.markdown("**Latest 10 mempool transactions**")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if pools:
        pool_list = pools.get("pools", pools.get("data", [])) if isinstance(pools, dict) else pools
        if isinstance(pool_list, list):
            rows = [{
                "Mining pool tag": x.get("name", "Unknown"),
                "Blocks": x.get("blockCount", x.get("blocks", x.get("count"))),
                "Share": x.get("share"),
            } for x in pool_list[:10]]
            if rows:
                st.markdown("**Mining pool block attribution — trailing 24 hours**")
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                st.caption(
                    "Pool tags identify blocks attributed to pools. They are not miner-wallet flows "
                    "and do not establish miner selling."
                )

    if errors:
        with st.expander(f"Source warnings ({len(errors)})"):
            for e in errors:
                st.error(e)

def render_tagged():
    st.subheader("Option A — Tagged-wallet monitoring")
    st.caption("Only addresses you supply are monitored. This is not a whole-exchange or whole-miner total.")
    st.info(
        "Upload a CSV with required columns entity, entity_type, address. Optional columns: source, confidence. "
        "Use public addresses only. Never upload private keys, seed phrases or exchange credentials."
    )
    upload = st.file_uploader("Public Bitcoin address watchlist CSV", type=["csv"], key="watchlist")
    if upload is None:
        st.markdown("CSV template:")
        st.code("entity,entity_type,address,source,confidence\n", language="csv")
        return
    try:
        watch = parse_watchlist(upload)
    except Exception as e:
        st.error(f"CSV error: {e}")
        return
    if watch.empty:
        st.warning("No usable addresses in the CSV.")
        return
    if len(watch) > MAX_TAGGED_ADDRESSES:
        st.error(f"Free polling profile supports at most {MAX_TAGGED_ADDRESSES} addresses per refresh.")
        return
    st.write(f"{len(watch)} addresses · {watch['entity'].nunique()} entity labels")
    st.dataframe(watch, use_container_width=True, hide_index=True)
    st.warning(
        "Each address-history response contains only a limited recent page (up to 50 mempool plus "
        "25 confirmed transactions). Results are not a complete 24-hour ledger."
    )
    if st.button("Fetch / refresh tagged address sample", type="primary"):
        all_txs = {}
        errs = []
        with st.spinner("Fetching the supplied public addresses..."):
            for addr in watch["address"].tolist():
                if not plausible_btc_address(addr):
                    errs.append(f"{addr}: address format needs checking")
                    continue
                try:
                    for tx in get_address_txs(addr):
                        if tx.get("txid"):
                            all_txs[tx["txid"]] = tx
                except Exception as e:
                    errs.append(f"{addr}: {e}")
        rows = []
        total_in = total_out = 0
        for entity, group in watch.groupby("entity"):
            ins, outs, n, internal = aggregate_entity(set(group["address"]), list(all_txs.values()))
            total_in += ins
            total_out += outs
            rows.append({
                "Entity": entity,
                "Type": ", ".join(sorted(set(group["entity_type"]))),
                "Addresses": group["address"].nunique(),
                "Observed txs": n,
                "Tagged inputs BTC": ins / 100_000_000,
                "Tagged outputs BTC": outs / 100_000_000,
                "Net balance change BTC": (outs - ins) / 100_000_000,
                "Txs with tagged inputs and outputs": internal,
            })
        st.session_state["tagged_result"] = {
            "time": utc_now(), "n_txs": len(all_txs), "rows": rows,
            "input": total_in, "output": total_out, "errors": errs,
        }
    result = st.session_state.get("tagged_result")
    if result:
        st.caption(f"Last fetch: {result['time']}")
        c = st.columns(3)
        c[0].metric("Unique txs observed", f"{result['n_txs']:,}")
        c[1].metric("BTC spent from tagged addresses", btc(result["input"]))
        c[2].metric("Net tagged balance change", btc(result["output"] - result["input"]))
        st.dataframe(pd.DataFrame(result["rows"]), use_container_width=True, hide_index=True)
        st.caption(
            "Net balance change = outputs to watched addresses minus inputs spent from watched addresses. "
            "Internal transfers cancel in net only where both sides are present in the fetched sample. "
            "Coverage depends on completeness of the user-supplied address labels and API response pages."
        )
        for e in result["errors"]:
            st.error(e)

def render_daily():
    st.subheader("Free daily on-chain metrics — BGeometrics")
    st.caption(
        "Daily-updated reference data, not tick-level real-time. Free plan: 8 requests/hour and 15/day. "
        "Exchange and miner aggregate flow endpoints are not included in the free plan. "
        "This panel makes three requests only when you click the button."
    )
    if st.button("Fetch daily free metrics (3 requests)", type="primary"):
        results, errors = {}, []
        with st.spinner("Fetching market cap, realized cap and active addresses..."):
            for endpoint in ["market-cap", "realized-cap", "active-addresses"]:
                try:
                    results[endpoint] = latest_record(get_bg_metric(endpoint))
                except Exception as e:
                    errors.append(f"{endpoint}: {e}")
        st.session_state["bg_result"] = {"time": utc_now(), "data": results, "errors": errors}
    result = st.session_state.get("bg_result")
    if not result:
        st.info("Not fetched in this session. Press the button to use three free API requests.")
        return
    st.caption(f"Fetched: {result['time']} · BGeometrics free API")
    data = result["data"]
    labels = [
        ("market-cap", "Market capitalization"),
        ("realized-cap", "Realized capitalization"),
        ("active-addresses", "Active addresses"),
    ]
    for key, label in labels:
        if key in data:
            dt, val, raw = data[key]
            st.write(f"**{label}:** {val:,.4f}" if val is not None else f"**{label}:** No numeric value parsed")
            st.caption(f"Observation date: {dt or 'not returned'} · fields: {', '.join(raw.keys()) if raw else 'none'}")
    if "market-cap" in data and "realized-cap" in data:
        d1, cap, _ = data["market-cap"]
        d2, realized, _ = data["realized-cap"]
        if cap is not None and realized and realized > 0 and d1 and d1 == d2:
            st.metric("Derived MVRV (same-date market cap ÷ realized cap)", f"{cap/realized:.4f}")
        else:
            st.warning("MVRV not calculated: market-cap and realized-cap data are unavailable or dates differ.")
    for e in result["errors"]:
        st.error(e)

with st.sidebar:
    st.header("Run configuration")
    st.write("Raw market/network auto-refresh: **60 seconds**")
    st.write("Tagged-wallet refresh: **manual**")
    st.write("BGeometrics daily metrics: **manual, three calls**")
    st.divider()
    st.caption("No paid keys are required for the two modes. Public-service limits apply.")

t_raw, t_tag, t_daily, t_info = st.tabs([
    "Option B — Raw Blockchain", "Option A — Tagged Wallets",
    "Free Daily On-Chain", "Definitions & Limits"
])
with t_raw:
    raw_live()
with t_tag:
    render_tagged()
with t_daily:
    render_daily()
with t_info:
    st.markdown("""
### Option B — Raw Blockchain
Whole-network blocks, mempool backlog, fee estimates, recent mempool transaction samples,
Binance BTCUSDT perpetual quote, and mining-pool block attribution. No exchange/miner address
labels are inferred.

### Option A — Tagged Wallets
User-supplied public Bitcoin addresses only. The app computes tagged inputs, tagged outputs and
net tagged balance change over the limited transactions returned by the address-history endpoint.
These are partial samples, not 24-hour totals or complete exchange/miner flows.

### Free Daily On-Chain
BGeometrics free API gives selected daily metrics. The free-plan documentation limits API calls and
reserves exchange/miner aggregate flows for paid plans. This dashboard derives MVRV only if market-cap
and realized-cap dates match.

### TradingView integration boundary
Pine Script cannot call arbitrary REST APIs or localhost endpoints. Run this Streamlit companion
beside TradingView. Do not copy tagged-address sample values into vendor-wide EX-IN/EX-OUT or
MNR-IN/MNR-OUT cells.
""")
    st.markdown("""
**Official API documentation**
- [Binance public USDⓈ-M Futures market-data REST API](https://developers.binance.info/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)
- [Mempool.space REST API](https://mempool.space/docs/api/rest)
- [Mempool.space WebSocket API](https://mempool.space/docs/api/websocket)
- [BGeometrics free plan and endpoint list](https://bitcoin-data.com/bguser/free-features.html)
- [Freedom Street public blockchain API](https://docs.freedom.st/)
""")

st.caption(
    "Public APIs can delay, rate-limit or fail. Raw chain observations and tagged-address estimates are "
    "not investment advice or certified whole-market exchange/miner flow data."
)
