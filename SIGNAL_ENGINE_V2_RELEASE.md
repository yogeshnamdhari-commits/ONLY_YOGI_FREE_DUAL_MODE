# Signal Engine v2.0.1 — Optional release bundle

The v2.0.1 application package is stored as 13 Base64 segments under [releases/v2.0.1](releases/v2.0.1/README.md).

**Important scope distinction:** The merge of PR #1 added the release bundle, release notes, assembly script, and CI workflow to `master`. It did **not** replace the root `app.py` or the root dashboard's version. The merge commit explicitly states that root `app.py` returns to the v1 baseline while v2.0.1 `signal_engine.py` and tests live inside the ZIP bundle.

## Reconstruct

```bash
bash releases/v2.0.1/assemble_bundle.command
```

The script reconstructs the archive, checks SHA-256, and tests ZIP integrity.

SHA-256:
`5f2381e825c7c4886152ccd35852ebf8f5a119ed301099b96f0aefd08e8148ac`

## Validation status

The GitHub Actions runs triggered by the feature-branch push and PR both succeeded. They reconstructed the ZIP, installed dependencies, compiled Python, and ran the test suite. They were feature-branch runs before the merge; a separate post-merge master run was not present in the repository at the time of this note.

The nine test cases and compile checks passed in the CI package. This does not validate live provider availability, trading profitability, or the deployment on a particular Mac.

## Safety

- Read-only; no order placement or exchange credentials.
- Signal rules are provisional and have not been shown profitable.
- Missing, stale, malformed or date-misaligned required data should lead to WAIT.
- The package does not infer total labelled exchange/miner flows from incomplete raw blockchain samples.
