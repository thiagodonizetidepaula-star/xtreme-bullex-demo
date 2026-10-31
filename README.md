# Xtreme Tiger Pocket 5s

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
