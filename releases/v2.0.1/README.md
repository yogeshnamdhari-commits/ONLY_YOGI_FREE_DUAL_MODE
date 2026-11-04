# ONLY YOGI Signal Engine v2.0.1 — Port 8508

This release bundle contains the complete Streamlit application, signal engine, tests,
configuration, installation launcher, README, audit report, release notes, and CI workflow.

## Reconstruct the ZIP on macOS

From a clone of this branch:

```bash
bash releases/v2.0.1/assemble_bundle.command
```

The script concatenates the numbered Base64 segments, verifies the published SHA-256,
and runs `unzip -t` before reporting success.

## Install

```bash
mkdir -p ~/Downloads/ONLY_YOGI_SIGNAL_ENGINE
unzip -o releases/v2.0.1/ONLY_YOGI_SIGNAL_ENGINE_PORT_8508.zip -d ~/Downloads/ONLY_YOGI_SIGNAL_ENGINE
cd ~/Downloads/ONLY_YOGI_SIGNAL_ENGINE
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m unittest discover -s tests -v
streamlit run app.py --server.port 8508
```

Open http://localhost:8508.

## Safety and validation

- Read-only dashboard. No order placement or account credentials.
- BUY/SELL confirmation is a provisional rules-based decision, not proof of profitability.
- WAIT is expected whenever required inputs are missing, stale, malformed, or date-misaligned.
- Free on-chain data do not provide complete labelled exchange or miner flow totals.
- The package's nine unit tests and Python compile checks passed before this repository publication.
- Live API validation and a local launch on the user's Mac remain outstanding.
