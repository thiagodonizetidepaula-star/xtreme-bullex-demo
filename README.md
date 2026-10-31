# Xtreme Tiger Pocket 5s

## V22 — ZigZag + Fractal + Linha + PRICE ACTION, candle 5s / expiração 3s, 5s ou 60s

The **same existing 5s ZigZag scanner** now offers three DEMO expiration settings: **3 seconds**, **5 seconds** and **60 seconds (one minute)**. The signal timeframe always stays **5-second CLOSED candles**, regardless of the chosen expiration. This is not the tick-only 3s strategy nor the M1 indicator. The rest of the M1 and M2 profiles are unchanged.

Signal criteria use the existing two-confirmed-fractal down-sloping resistance line and completed ZigZag reversal, plus price-action candle confirmation:

- **BUY / CALL:** green fractal trough confirmed; two real 5s closes beyond a descending resistance line; and the latest *closed* 5s candle is bullish and its close exceeds the **previous candle's high**.
- **SELL / PUT:** confirmed red fractal at the closed rising ZigZag leg; resistance remains intact; and the latest *closed* 5s candle is bearish and its close falls **below the previous candle's low**.
- **WAIT:** wick-only break, not enough real candles/history, stale per-asset feed, lateral/ambiguous price action or unconfirmed fractal/ZigZag tip.

**3s latency rule:** discard any 5s signal or market feed more than **one second old** before placing a short-duration order; still check all other payout, DEMO, pending order and risk guards. Expiration is sent as the selected 3/5/60 integer seconds, not inferred from the chart timeframe. For every previously unverified expiration, use **demo amount 1** initially and validate settlement returned by broker.

This is a tighter *hypothesis* and could reduce the frequency of signals. It is not a proven increase in trading accuracy; a 5s bar and especially 3s expiry are highly sensitive to price noise and network delay. Synthetic unit tests cannot prove actual broker fill time, profitability, historical data availability or compatibility. Never enable real-money trading.

## V21 — ZigZag + Fractal + Linha M2 com expiração M1/M2/M3 (DEMO)

A new independent chart-analysis profile **ZIGZAG + FRACTAL + LINHA · ANÁLISE M2** is added to the existing Android WebView. It builds **120-second closed candles** from authenticated Pocket Option DEMO tick streams, or requests and validates prior broker history with `period=120`. It uses the same confirmed fractal peaks/lows, closed ZigZag reversal, two descending fractal highs for resistance, and breakout confirmation rules used by the existing modes. **The expiration is independently selected as 60, 120 or 180 seconds** (M1/M2/M3). Choosing M1 expiry never changes the M2 analysis candles.

- The bot scans open regular/OTC assets only when fresh per-asset DEMO broker quotes exist, and cannot manufacture missing candles or execute historical signals.
- Technical context is primed from verified prior closed M2 candles when the unofficial broker history interface supplies them. Missing verifiable history means the bot waits for actual complete candles; it never skips pivot/fractal confirmation.
- Signals only arise on the next LIVE completed M2 candle after all confirmations, never from a still-repainting ZigZag tip.
- M1 (60s ZigZag), 5s fast ZigZag, and existing tick/M5 profiles remain available and are not replaced.
- Initial test is limited to amount 1 DEMO for any new requested expiry until the broker result and duration are validated. Min payout, max operations, stops, one pending order, and cooldown are retained.

This strategy is experimental, not validated to be profitable. The unofficial broker history service may fail or provide incomplete data, which must not be interpreted as permission to trade with missing confirmation. All testing in CI uses deterministic synthetic prices, never a user account or real orders.

## V20 — Usar velas anteriores da Pocket Option antes de buscar sinais

Instead of waiting to construct 22 new chart candles after every start, the
DEMO scanner requests past quote/candle history from Pocket Option through
`loadHistoryPeriod` and can ingest independently identified
`updateHistoryNewFast` history. Responses are validated per asset, timeframe,
time alignment, OHLC bounds, recent source clock, real quote coverage, and
closed-candle continuity. **No invented candles, stale signals, or orders
based solely on historical data.** History primes indicators, and a new
live **closed** 5-second or M1 candle is still required for a trade.

History requests are throttled across subscribed open assets; only a live
verified feed allows seeding. The UI shows the number of assets with genuine
historical data and ready indicator context. If the unofficial adapter does
not return verifiable history for an asset, that asset safely builds candles
from actual incoming quotes and cannot instantly trigger a signal.
Historical-candle reception and genuine demo order execution still need to
be verified with a real demo session; unit tests are synthetic and network-free.

## V19 — ZigZag/Fractal/Linha QUICK 5s (DEMO only)

A new **ZIGZAG + FRACTAL + LINHA · 5s RÁPIDO** profile is available *alongside* the original 60-second/M1 profile in the same Android WebView and Render service. Do not confuse expiry (the option closes after 5 seconds) with chart timeframe (each real, completely observed candle is also five seconds).

- Scans available regular and OTC assets using independently received, current DEMO quotes.
- Buckets broker quote timestamps into real five-second candles, requiring at least two distinct seconds and sufficient within-candle coverage. Missing or too-sparse intervals discard the technical warmup; no artificial candles or forward-filled ticks.
- Runs the same ZigZag 5/12/3-inspired confirmed pivot, two-right-bar Fractal 2, confirmed lower-high resistance, breakout BUY (two completed candles holding above the line), and SELL only under intact resistance.
- Warmup requires **22 full 5-second candles (~110 seconds minimum)** rather than 22 M1 candles, but patterns may take much longer; no arbitrary frequency of orders is promised.
- Broker-driven expiry is set to exactly **5 seconds** for this mode. Existing min payout, demo session checks, one unresolved order at a time, cooldown, risk stops and official result reconciliation apply. Initial automatic duration validation is limited to a demo amount of 1.
- Other strategies, including original M1 trendline scanner and separate 3/5-second tick exhaustion, remain available and separate.

**Risk:** Five-second price behavior is especially noisy and latency-sensitive; these ZigZag/Fractal settings are experimental and *not validated for profitable binary-options entries*. A broker confirmation of an order's expiry is not proof of a trading edge. The unofficial API may fail to stream some assets; a subscription request alone never counts as a verified feed. No trades on a real-money account are supported.

## V18 experimental trendline reversal confirmation (DEMO only)

The existing **ZIGZAG + FRACTAL** OTC-wide scanner now uses **two confirmed descending red fractal highs** to draw a resistance line on the M1 chart (only real, completed candles). It can issue either:

- **SELL / PUT 60 seconds:** confirmed red Fractal 2 AND completed rising ZigZag leg AND close beneath intact descending resistance; an incipient breakout vetoes sells.
- **BUY / CALL 60 seconds:** a confirmed green Fractal 2 bottom followed by an M1 close above descending resistance and one more fully closed M1 candle holding above it. A wick/touch alone is not a signal.
- **WAIT:** ambiguous trendline, missing candles, stale/unavailable quotes, any incomplete pivot or late repeated signal.

The app shows real closed candles and the projected resistance for one actual scanned feed, with diagnostics. Eligible OTC assets are searched independently, but only streams actually delivered by the unofficial Pocket Option integration can be evaluated. A signal is not a guarantee of a future price move. An entry at expiration 60s remains an unproven experimental hypothesis. No REAL trading sessions are accepted and no live order was tested without a user-authenticated DEMO session.

## V17 experimental ZigZag + Fractal scanner (DEMO only)

**V17 description below is historical. V18 above supersedes the SELL-only strategy.**

Select **ZIGZAG + FRACTAL · todos OTC · VENDA 1min**, use amount 1 for the first expiry validation, then explicitly start DEMO automation. The scanner requests live quote subscriptions for every available OTC asset with payout >= the configured minimum (at least 88%), and keeps **independent** M1 candle histories. It can send **PUT only**, expiry 60 seconds, after a five-bar ZigZag high following a confirmed low and a red Fractal 2 (two fully closed M1 candles to the right) with a minimum 12-price-point reversal and three-bar pivot separation. No unfinished tip, stale feed, missing minute or bulk-replayed quotes can trigger an order. One pending order at a time, official result checks, stops and 60-minute session cap remain enforced.

**Limitations:** This is an approximation of Pocket Option's visual ZigZag 5/12/3, not a byte-for-byte reproduction of its indicator. Broker tick size and internal indicator rules are not public. subscribeSymbol + changeSymbol are requested per asset but this unofficial API may not deliver every requested stream. The panel reports eligible, requested, *actually receiving* and warmed assets separately; no verified stream means no order. No live DEMO execution has been confirmed without a connected user's session. Render Free may sleep and erase in-memory candles if the app is backgrounded. There is no guarantee of entries or profitable results.


Standalone demo-only Pocket Option app. No OpenAI API and no generated market data.

## Run
Python 3.11+: `pip install -r requirements.txt`, set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY, then `python server.py`. Default port 10000. One server process; in-memory sessions are isolated by verified Supabase user id. Limits: three concurrent users, 120-second inactivity disconnect.

## Authentication
Application accounts use Supabase email/password authentication. Broker authentication uses the complete Socket.IO `42["auth",{...}]` payload with integer `isDemo:1`. Stored only in memory, never in database, browser storage or logs. New deploys and inactivity erase broker sessions. Neither a Pocket Option password nor a real-account session is accepted. TLS verification remains enabled.

## Execution and limitations
Only demo endpoints are configured. The broker must authenticate and explicitly confirm demo balance. Price age, open OTC asset, payout, balance, amount, single outstanding request and cooldown checks run server-side. Unknown results stop automation; requests are never retried. A manually initiated order must have its five-second duration confirmed from broker timestamps before auto mode unlocks. The strategy uses five- and twenty-second means and three-second momentum; it is experimental, not a trained AI or proven strategy. Outcomes require official close-deal prices and a payout-consistent profit field; incompatible payloads keep the order unresolved.

Stop win/loss is based on settled net results since activation, so one order can exceed a stop. Shutdown never cancels an order already accepted by the broker. Keep the panel open. Free Render hosting does not guarantee uninterrupted service. Reconnection and server restart require explicit user action; inspect unresolved trades at the broker before proceeding.

## Protocol research
Compared `ChipaDevTeam/PocketOptionAPI` (archived), `Mastaaa1987/PocketOptionAPI-v2` (desktop pywebview login), and `chema-creator/PocketOptionApi` (Socket.IO examples). Original adapter implementation based on observed protocol documentation in:
- https://github.com/chema-creator/PocketOptionApi/blob/main/pocketoptionapi/ws/client.py
- https://github.com/chema-creator/PocketOptionApi/blob/main/pocketoptionapi/constants.py
- https://github.com/chema-creator/PocketOptionApi/blob/main/pocketoptionapi/ws/channels/buyv3.py

No upstream package is executed or vendored. Research found upstream disabled TLS and authentication payload logging; this implementation does neither. The integration is unofficial and may stop working or be refused by Pocket Option. Live authentication and order execution require the user's demo session and have NOT been validated without it.

## Data
`public.pocket_tiger_demo_history`, RLS ownership by auth.uid(), no anon privileges. Only order ids, market parameters and filtered results are persisted. Existing Mesa Trader tables are unchanged. UI polling and auth refresh keep the app session active; user must reconnect after server restart. History is capped to 300 rows in the panel, downloadable as CSV.

## Tests
`python -m unittest -v` covers auth parsing, real-account rejection, duplicate and stale order blocking, binary events, official result matching, net/gross profit, and five-second validation. No broker network request or trade is performed by these tests.
