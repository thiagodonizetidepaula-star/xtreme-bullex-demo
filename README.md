# Xtreme Tiger Pocket 5s

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
