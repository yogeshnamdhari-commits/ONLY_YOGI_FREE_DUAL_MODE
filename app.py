
from __future__ import annotations
import re
import math
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
st.caption("Option A: tagged wallet sample  |  Option B: raw Bitcoin network activity  |  Signal Confirmation: read-only")

st.warning(
    "This is a local Streamlit companion to TradingView. Pine Script cannot call arbitrary REST APIs, "
    "so these external data are displayed here, not injected into your Pine indicator. "
    "No order execution is included. All signals are provisional and read-only."
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

@st.cache_data(ttl=300, show_spinner=False)
def get_binance_klines(symbol="BTCUSDT", interval="4h", limit=200):
    return api_get(f"{BINANCE_FUTURES}/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": limit})

@st.cache_data(ttl=60, show_spinner=False)
def get_binance_open_interest(symbol="BTCUSDT"):
    return api_get(f"{BINANCE_FUTURES}/fapi/v1/openInterest", {"symbol": symbol})

@st.cache_data(ttl=60, show_spinner=False)
def get_binance_funding_rate(symbol="BTCUSDT"):
    return api_get(f"{BINANCE_FUTURES}/fapi/v1/fundingRate", {"symbol": symbol})

@st.cache_data(ttl=60, show_spinner=False)
def get_binance_agg_trades(symbol="BTCUSDT", limit=500):
    return api_get(f"{BINANCE_FUTURES}/fapi/v1/aggTrades", {"symbol": symbol, "limit": limit})

def ema_values(prices, period):
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    result = [sum(prices[:period]) / period]
    for price in prices[period:]:
        result.append(price * multiplier + result[-1] * (1 - multiplier))
    return result

def rsi_value(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(-change)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        current_rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        current_rsi = 100 - (100 / (1 + rs))
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            current_rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            current_rsi = 100 - (100 / (1 + rs))
    return current_rsi

def cvd_from_trades(trades):
    buy_volume = 0.0
    sell_volume = 0.0
    for t in trades:
        qty = float(t.get("q", 0))
        if t.get("m") is True:
            sell_volume += qty
        else:
            buy_volume += qty
    return buy_volume - sell_volume, buy_volume, sell_volume

def bg_supply_profitability():
    candidates = ["supply-profit", "supply-in-profit", "profit-loss", "supply-profitability"]
    for endpoint in candidates:
        try:
            payload = get_bg_metric(endpoint)
            dt, value, raw = latest_record(payload)
            if value is not None:
                return {"endpoint": endpoint, "date": dt, "value": value, "raw": raw, "error": None}
        except Exception as e:
            continue
    return {"endpoint": None, "date": None, "value": None, "raw": {}, "error": "supply profitability endpoint not available on free tier"}

def bg_holder_distribution():
    candidates = ["holder-distribution", "balance-cohorts", "wallet-cohorts", "address-cohorts"]
    for endpoint in candidates:
        try:
            payload = get_bg_metric(endpoint)
            dt, value, raw = latest_record(payload)
            if value is not None or raw:
                return {"endpoint": endpoint, "date": dt, "value": value, "raw": raw, "error": None}
        except Exception:
            continue
    return {"endpoint": None, "date": None, "value": None, "raw": {}, "error": "holder distribution endpoint not available on free tier"}

def bg_hodl_waves():
    candidates = ["hodl-waves", "hodlwave", "realized-age"]
    for endpoint in candidates:
        try:
            payload = get_bg_metric(endpoint)
            dt, value, raw = latest_record(payload)
            if value is not None or raw:
                return {"endpoint": endpoint, "date": dt, "value": value, "raw": raw, "error": None}
        except Exception:
            continue
    return {"endpoint": None, "date": None, "value": None, "raw": {}, "error": "HODL waves endpoint not available on free tier"}

def is_fresh(ts_str, max_age_hours=48):
    if not ts_str:
        return False
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00")) if "T" in ts_str else datetime.strptime(ts_str, "%Y-%m-%d")
        ts = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
        age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        return age_hours <= max_age_hours
    except Exception:
        return False

def render_signal_confirmation():
    st.subheader("Signal Confirmation — Read-Only")
    st.caption("Stage A evaluates market bias from on-chain data. Stage B confirms with technical and derivatives data. Final decision appears only when conditions align and data is fresh.")

    bg_data = {}
    bg_errors = []
    fetch_bg = st.button("Fetch daily on-chain snapshot (Stage A)", type="primary", key="signal_fetch_bg")
    if fetch_bg:
        endpoints = ["market-cap", "realized-cap", "active-addresses", "dominance", "tvl", "developer-activity", "social-sentiment"]
        with st.spinner("Fetching BGeometrics free metrics..."):
            for endpoint in endpoints:
                try:
                    bg_data[endpoint] = latest_record(get_bg_metric(endpoint))
                except Exception as e:
                    bg_errors.append(f"{endpoint}: {e}")
        sp = bg_supply_profitability()
        if sp["error"]:
            bg_errors.append(f"supply-profitability: {sp['error']}")
        else:
            bg_data["supply-profitability"] = (sp["date"], sp["value"], sp["raw"])
        hd = bg_holder_distribution()
        if hd["error"]:
            bg_errors.append(f"holder-distribution: {hd['error']}")
        else:
            bg_data["holder-distribution"] = (hd["date"], hd["value"], hd["raw"])
        hw = bg_hodl_waves()
        if hw["error"]:
            bg_errors.append(f"hodl-waves: {hw['error']}")
        else:
            bg_data["hodl-waves"] = (hw["date"], hw["value"], hw["raw"])
        st.session_state["signal_bg"] = {"time": utc_now(), "data": bg_data, "errors": bg_errors}

    result = st.session_state.get("signal_bg")
    if not result:
        st.info("Stage A not fetched yet. Press the button to load the daily on-chain snapshot.")
    else:
        st.caption(f"Stage A fetched: {result['time']} · BGeometrics free API (bounded to ~11 calls)")
        data = result["data"]

        st.markdown("### Stage A — Market Bias")
        bias_score = 0
        bias_factors = []

        d_mcap, cap, _ = data.get("market-cap", (None, None, {}))
        d_realized, realized, _ = data.get("realized-cap", (None, None, {}))
        d_active, active, _ = data.get("active-addresses", (None, None, {}))
        d_dom, dom, _ = data.get("dominance", (None, None, {}))

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Market cap", usd(cap), f"date: {d_mcap or '—'}")
        col2.metric("Realized cap", usd(realized), f"date: {d_realized or '—'}")
        col3.metric("Active addresses", f"{active:,.0f}" if active else "—", f"date: {d_active or '—'}")
        col4.metric("BTC dominance", f"{dom:,.2f}%" if dom else "—", f"date: {d_dom or '—'}")

        if cap is not None and realized and realized > 0 and d_mcap and d_realized and d_mcap == d_realized:
            mvrv = cap / realized
            st.metric("MVRV (same-date)", f"{mvrv:.4f}")
            if mvrv <= 1.0:
                bias_score += 1
                bias_factors.append("MVRV at/below accumulation threshold (bullish)")
            elif mvrv >= 3.5:
                bias_score -= 1
                bias_factors.append("MVRV at/above overheated threshold (bearish)")
            else:
                bias_factors.append("MVRV between thresholds (neutral)")
        else:
            st.warning("MVRV not calculated: market-cap and realized-cap dates differ or data missing.")
            bias_factors.append("MVRV unavailable (neutral)")

        sp_date, sp_value, sp_raw = data.get("supply-profitability", (None, None, {}))
        if sp_value is not None:
            st.metric("Supply profitability indicator", f"{sp_value:,.4f}", f"date: {sp_date or '—'}")
            if sp_value > 0:
                bias_score += 1
                bias_factors.append("Supply profitability positive (bullish)")
            else:
                bias_score -= 1
                bias_factors.append("Supply profitability negative (bearish)")
        else:
            st.info("Supply profitability: not available on free tier.")
            bias_factors.append("Supply profitability unavailable (neutral)")

        hd_date, hd_value, hd_raw = data.get("holder-distribution", (None, None, {}))
        if hd_raw:
            st.write("Holder distribution raw fields:", ", ".join(hd_raw.keys()) if hd_raw else "none")
            st.caption(f"Observation date: {hd_date or 'not returned'}")
        else:
            st.info("Holder distribution cohorts: not available on free tier.")

        hw_date, hw_value, hw_raw = data.get("hodl-waves", (None, None, {}))
        if hw_raw:
            st.write("HODL waves raw fields:", ", ".join(hw_raw.keys()) if hw_raw else "none")
            st.caption(f"Observation date: {hw_date or 'not returned'}")
        else:
            st.info("HODL waves: not available on free tier.")

        for e in result["errors"]:
            st.error(e)

        st.markdown("---")
        st.markdown("### Stage B — Technical & Derivatives Confirmation")
        st.caption("Binance public Futures endpoints. 1H/4H EMA 20, 50, 144, 200; RSI; breakout; volume; CVD; open interest; funding rate.")

        fetch_tech = st.button("Fetch technical confirmation (Stage B)", type="primary", key="signal_fetch_tech")
        if fetch_tech:
            tech_data = {}
            tech_errors = []
            with st.spinner("Fetching Binance Futures market data..."):
                try:
                    perp = get_binance_perp()
                    tech_data["price"] = number(perp.get("price"))
                except Exception as e:
                    tech_errors.append(f"Binance price: {e}")
                    tech_data["price"] = None

                try:
                    klines_4h = get_binance_klines(interval="4h", limit=200)
                    close_4h = [float(k[4]) for k in klines_4h]
                    high_4h = [float(k[2]) for k in klines_4h]
                    low_4h = [float(k[3]) for k in klines_4h]
                    vol_4h = [float(k[5]) for k in klines_4h]
                    tech_data["klines_4h"] = {"close": close_4h, "high": high_4h, "low": low_4h, "volume": vol_4h}
                except Exception as e:
                    tech_errors.append(f"Binance 4H klines: {e}")
                    tech_data["klines_4h"] = None

                try:
                    klines_1h = get_binance_klines(interval="1h", limit=200)
                    close_1h = [float(k[4]) for k in klines_1h]
                    tech_data["klines_1h"] = {"close": close_1h}
                except Exception as e:
                    tech_errors.append(f"Binance 1H klines: {e}")
                    tech_data["klines_1h"] = None

                try:
                    oi = get_binance_open_interest()
                    tech_data["open_interest"] = number(oi.get("openInterest"))
                except Exception as e:
                    tech_errors.append(f"Binance open interest: {e}")
                    tech_data["open_interest"] = None

                try:
                    fr = get_binance_funding_rate()
                    tech_data["funding_rate"] = number(fr.get("fundingRate"))
                    tech_data["funding_time"] = fr.get("fundingTime")
                except Exception as e:
                    tech_errors.append(f"Binance funding rate: {e}")
                    tech_data["funding_rate"] = None
                    tech_data["funding_time"] = None

                try:
                    trades = get_binance_agg_trades(limit=500)
                    cvd, buy_vol, sell_vol = cvd_from_trades(trades)
                    tech_data["cvd"] = cvd
                    tech_data["buy_volume"] = buy_vol
                    tech_data["sell_volume"] = sell_vol
                except Exception as e:
                    tech_errors.append(f"Binance agg trades: {e}")
                    tech_data["cvd"] = None
                    tech_data["buy_volume"] = None
                    tech_data["sell_volume"] = None

            st.session_state["signal_tech"] = {"time": utc_now(), "data": tech_data, "errors": tech_errors}

        tech_result = st.session_state.get("signal_tech")
        if tech_result:
            st.caption(f"Stage B fetched: {tech_result['time']} · Binance Futures public API")
            tdata = tech_result["data"]

            price = tdata.get("price")
            if price:
                st.metric("BTCUSDT perpetual", usd(price))
            else:
                st.metric("BTCUSDT perpetual", "Unavailable")

            k4 = tdata.get("klines_4h")
            k1 = tdata.get("klines_1h")
            tech_score = 0
            tech_factors = []

            if k4:
                close_4h = k4["close"]
                ema20 = ema_values(close_4h, 20)
                ema50 = ema_values(close_4h, 50)
                ema144 = ema_values(close_4h, 144)
                ema200 = ema_values(close_4h, 200)

                if ema20 and ema50 and ema144 and ema200:
                    e20, e50, e144, e200 = ema20[-1], ema50[-1], ema144[-1], ema200[-1]
                    st.write(f"4H EMA20: {e20:,.2f} · EMA50: {e50:,.2f} · EMA144: {e144:,.2f} · EMA200: {e200:,.2f}")
                    if price and price > e200:
                        tech_score += 1
                        tech_factors.append("Price above 4H EMA200 (bullish)")
                    else:
                        tech_factors.append("Price at/below 4H EMA200 (neutral/bearish)")
                    if e20 > e50 > e144 > e200:
                        tech_score += 1
                        tech_factors.append("4H EMA bullish alignment (20>50>144>200)")
                    elif e20 < e50 < e144 < e200:
                        tech_score -= 1
                        tech_factors.append("4H EMA bearish alignment (20<50<144<200)")
                    else:
                        tech_factors.append("4H EMA mixed alignment (neutral)")
                else:
                    st.info("4H EMA: insufficient data.")
            else:
                st.info("4H klines unavailable.")

            if k1:
                close_1h = k1["close"]
                rsi14 = rsi_value(close_1h, 14)
                if rsi14 is not None:
                    st.metric("1H RSI(14)", f"{rsi14:.2f}")
                    if 40 < rsi14 < 70:
                        tech_factors.append("1H RSI in neutral zone (40-70)")
                    elif rsi14 >= 70:
                        tech_score -= 1
                        tech_factors.append("1H RSI overbought (>=70, bearish)")
                    elif rsi14 <= 30:
                        tech_score += 1
                        tech_factors.append("1H RSI oversold (<=30, bullish)")
                else:
                    st.info("1H RSI: insufficient data.")
            else:
                st.info("1H klines unavailable.")

            oi = tdata.get("open_interest")
            if oi is not None:
                st.metric("Open interest", f"{oi:,.4f} BTC")
            else:
                st.info("Open interest unavailable.")

            fr = tdata.get("funding_rate")
            if fr is not None:
                st.metric("Funding rate", f"{fr*100:,.4f}%")
                if abs(fr) < 0.0001:
                    tech_factors.append("Funding rate near neutral")
                elif fr > 0:
                    tech_factors.append("Funding rate positive (longs pay shorts)")
                else:
                    tech_factors.append("Funding rate negative (shorts pay longs)")
            else:
                st.info("Funding rate unavailable.")

            cvd = tdata.get("cvd")
            if cvd is not None:
                st.metric("CVD (sampled)", f"{cvd:,.4f} BTC")
                if cvd > 0:
                    tech_score += 1
                    tech_factors.append("CVD positive (buyer aggression)")
                elif cvd < 0:
                    tech_score -= 1
                    tech_factors.append("CVD negative (seller aggression)")
                else:
                    tech_factors.append("CVD neutral")
            else:
                st.info("CVD unavailable.")

            for e in tech_result["errors"]:
                st.error(e)

            st.markdown("---")
            st.markdown("### Exchange / Miner Flows")
            st.error("Exchange inflow/outflow and miner inflow/outflow are excluded from the BGeometrics free tier. Marked unavailable — do not substitute tagged-address samples as aggregate exchange/miner flow.")

            st.markdown("---")
            st.markdown("### Final Decision")
            total_score = bias_score + tech_score
            data_fresh = bool(result and tech_result)
            if data_fresh and bias_score >= 1 and tech_score >= 1:
                decision = "CONFIRMED BUY"
                decision_color = "green"
            elif data_fresh and bias_score <= -1 and tech_score <= -1:
                decision = "CONFIRMED SELL"
                decision_color = "red"
            else:
                decision = "WAIT"
                decision_color = "gray"

            st.markdown(f"**Signal bias score: {bias_score} | Technical confirmation score: {tech_score} | Combined: {total_score}**")
            st.markdown(f"### :{decision_color}[{decision}]")
            st.caption("Bias factors: " + "; ".join(bias_factors) if bias_factors else "No bias factors.")
            st.caption("Technical factors: " + "; ".join(tech_factors) if tech_factors else "No technical factors.")
            st.caption("Provisional signal only. Not investment advice. No order execution.")

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

with st.sidebar:
    st.header("Run configuration")
    st.write("Raw market/network auto-refresh: **60 seconds**")
    st.write("Tagged-wallet refresh: **manual**")
    st.write("BGeometrics daily metrics: **manual, three calls**")
    st.write("Signal confirmation: **manual fetch**")
    st.divider()
    st.caption("No paid keys are required for the two modes. Public-service limits apply. Read-only; no order execution.")

t_raw, t_tag, t_daily, t_signal, t_info = st.tabs([
    "Option B — Raw Blockchain", "Option A — Tagged Wallets",
    "Free Daily On-Chain", "Signal Confirmation", "Definitions & Limits"
])
with t_raw:
    raw_live()
with t_tag:
    render_tagged()
with t_daily:
    render_daily()
with t_signal:
    render_signal_confirmation()
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

### Signal Confirmation (v2.0)
Stage A evaluates market bias from BGeometrics free metrics: market cap, realized cap, active addresses,
MVRV, supply profitability, holder distribution, and HODL waves. Bounded to approximately 11 API calls;
fetch once daily.

Stage B confirms with Binance public Futures data: 1H/4H EMA 20/50/144/200, RSI(14), breakout context,
volume, sampled CVD, open interest, and funding rate.

Final decision logic:
- CONFIRMED BUY: Stage A bias score >= 1 AND Stage B technical score >= 1 AND data fresh
- CONFIRMED SELL: Stage A bias score <= -1 AND Stage B technical score <= -1 AND data fresh
- WAIT: conditions conflict, confirmation incomplete, or required data stale/missing

Exchange/miner aggregate flows are not available on the BGeometrics free tier and are explicitly
marked unavailable. Tagged-address samples must not be substituted for aggregate exchange/miner flow.

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
    "not investment advice or certified whole-market exchange/miner flow data. The signal rules are "
    "provisional and have not been demonstrated profitable; no order execution is included."
)
