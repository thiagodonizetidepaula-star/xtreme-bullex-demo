# NOVA QUANT | Strategy Lab V1

A separate experimental Bullex PRACTICE-only application. New UI, settings,
scanner, user session, and dedicated Render service. Xtreme-Tiger stays on its
own branch and service. This branch reuses only the pinned broker transport
(worker.py, executor_worker.py, bootstrap.py), not any Xtreme strategy rules.

## Behavior
- Genuine broker-native closed M1 and M5 bars; no synthesized M5 candles.
- Researches 9 parameter hypotheses across four families: Bollinger reentry,
  Bollinger squeeze, Bollinger midline momentum, and EMA pullback. RSI14/EMA9
  EMA21/ATR14 are used as indicators and filters.
- Chronological 70/30 historical train/holdout. MIN_TRAIN=5, MIN_TEST=3,
  holdout directional win rate >= 58% for an experimental gate. Samples
  are tiny; validation is exploratory, not robust predictive proof.
- Backtest enters at next candle open, exits at next candle close. NO historical
  payouts, spreads, slippage or provider rejections are modeled. Trades during
  historical period are hypothetical and never included in session WIN/LOSS.
- PRACTICE automatic trading is OFF by default, requires explicit action, and
  only uses signals meeting the gate, payout >=80%, closed-candle window <=3
  seconds, fresh broker clock, broker confirmation, remaining stop loss, stops,
  single active order, and capped stake.
- No real-account order support. No real money usage.
- Credentials in memory only, not persisted or shared with Xtreme-Tiger.
- Each Render deploy resets in-memory sessions and requires a new PRACTICE login.
- Do not log the same Bullex account into NOVA QUANT and Xtreme simultaneously.
- Built on free Render instance if available; expect cold starts or quota limits.

## Run
- python -m unittest quant_lab.test_brain
- Existing bootstrap.py installs the connector; python quant_lab/app.py
- Environment PORT may be set by Render.

## Risk
Binary options can result in total loss of the stake. Random parameter search
and small walk-forward holdout are not evidence of a consistently profitable
strategy. No machine learning system can promise a particular win rate.
