# Xtreme Analista — two independent PRACTICE engines

Analyst worker.py has no order commands. Optional executor_worker.py uses a separate authenticated Bullex session and confirms PRACTICE before each order and at actual websocket send. No real account mode is supported. Connection alone never starts orders.

Build: pip install -r requirements.txt && python bootstrap.py && python -m unittest test_analyst -v
Start: gunicorn app:app --workers 1 --threads 8 --timeout 180 --bind 0.0.0.0:$PORT

Environment: SESSION_SECRET, ANALYST_GATEWAY, ANALYST_GATEWAY_KEY in Render only. Supabase private gateway persists research and up to 500 demo order records. Database pre-send checkpoint is required; ambiguous orders stop execution and need manual broker review. No automatic retry or restart. No passwords persisted.

Analysis selection: wick/cross/engulf at 3m; raw Sniper HL2 and Sniper + ATR18x2 trend at 1/2/3/5m. Archived results retained. Executor freezes up to three combinations at explicit start, requiring >=30 completed theoretical outcomes and positive per-unit theoretical return. These are experimental candidates, not validated strategies. Each run has a fixed stake, order cap, payout floor, stop loss, stop win, and one order at a time. Expiry follows the selected combination. Signals older than two seconds are skipped. Stopping analysis also stops new execution; already submitted orders continue to result.

Free Render can sleep or restart, so overnight availability is not guaranteed. Broker integration is unofficial and 2FA remains unsupported. The actual broker login and order flow must be verified by the owner in PRACTICE. Unit tests use fake brokers and never place orders.


When no candidate is eligible at start, executor enters waiting mode and monitors new analysis; when eligible candidates appear, it freezes their selection and waits for a fresh signal. Action feedback remains visible across polling updates. Demo guards and qualification requirements are unchanged.


Live operation panel uses server_now plus monotonic browser elapsed time and broker-confirmed expiration. It distinguishes qualification wait, searching, sending, open, finalizing, confirmed result, uncertain and stale connection. Zero seconds never implies WIN/LOSS; stale state hides the countdown after 15s. Run node test_live_ui.cjs for display-state regression tests. No order logic changes in this display revision.


Latency fix: compact per-account order_checkpoint replaces full research save on critical pre-send path. Restore merges it into order history and marks unresolved sends uncertain. Separate executor prefetches market and demo balance near minute boundary; dispatch uses cache no older than 8 seconds and an absolute maximum entry delay of 5 seconds, rechecked at actual websocket send. Signals outside the bound are never sent. Full research saves remain outside pre-send. No automatic retry on uncertain send. Gateway v2 and order_checkpoint column must be deployed before this revision.


Current selection rule: observed wins/completed observations >=60%, no minimum of 30 observations and no additional positive-return qualification. Ties count in completed denominator; pending/missing quotes do not. Integer comparison prevents rounding below-threshold rates up to 60%. Top three eligible combinations are reevaluated while idle, and selected sample sizes are displayed. This is a user-selected demo criterion, not a claim of statistical validation or future accuracy.
