# Xtreme Tiger — Android proof of concept (NOT RELEASED)

This folder is an **isolated experiment** for a user's own Pocket Option **DEMO** account on Android. It does not modify the Xtreme Tiger web app on Render and must not be treated as a working Pocket Option connection.

## User flow

1. Open the Android debug app and log into the original Xtreme Tiger using its normal web login.
2. Tap **CONECTAR POCKET DEMO** and approve a single demo-only automatic session handoff for this attempt. A **separate in-app WebView** opens the official Pocket Option HTTPS site; it does **not** share Chrome cookies. Log into the broker's website there if the broker permits WebView login, and explicitly select the DEMO account.
3. On supported Android WebViews, a document-start probe watches for an outgoing Socket.IO **auth** message with integer `isDemo: 1`. The native bridge only accepts HTTPS messages originating from the official Pocket Option domain and validates again. If detected, it is temporarily held **in RAM only**.
4. After you approve the per-attempt authorization, a detected DEMO packet is automatically supplied to the *existing* SSID form through a one-time DOM operation, and the normal Xtreme backend checks/uses it. The Android app never submits trades itself.
5. The Android UI clearly displays **ANDROID V3**, hides the SSID form when DEMO is confirmed, and shows manual test, start and stop controls. **Only** the existing Xtreme status showing DEMO confirmation counts as successfully connected. The WebView probe merely identifies an authentication-shaped packet; it cannot prove the broker accepted it.

## Caveats

- No official Pocket Option OAuth/API was found. This is a fragile technical experiment, not an approved integration.
- The Chrome login **cannot** be read or reused. WebView uses a separate browser profile; Google/Facebook/2FA/CAPTCHA or page changes may break the flow.
- The WebSocket code might execute in a Worker or a different origin or might not be the same protocol; then the probe **will not** detect it. The program does not attempt to bypass a login challenge or remove TLS validation.
- Auth packets are credential-equivalent. Never share, record, log, upload to GitHub, or paste into chat. The script intentionally ignores real-account sessions. Native code never asks for the Pocket Option password.
- "Descartar sessão" clears local WebView cookies/storage; this can also require signing in to Xtreme again.
- This is **only a source-code prototype**, pending compilation, installation and validation on an Android device. No live-broker handshake has been tested.
- Check Pocket Option terms before testing unofficial automation. Never enable real-money execution.

## Build

The GitHub Actions workflow `android-demo-experiment.yml` performs JUnit and JS mock tests, then assembles a **debug** APK (CI artifact only, no Play Store release, no Render deployment). Alternatively, open this folder as an Android Studio project with Android SDK 35 and JDK 17. Use Gradle 8.10.2.

```bash
cd android-experimental
node tests/probe.test.mjs
gradle testDebugUnitTest assembleDebug
```

Inspect the commit, CI results and Android WebView test before trusting a local install. The existing Render deployment remains on `pocket-tiger-5s-v1`; never merge this prototype into that branch without real device validation.


## V3 Android installation and consent

- Android debug APKs built on separate ephemeral GitHub runners may be signed by different local debug keys. Users of V1 or V2 must **uninstall the old experimental APK first** and then install V3. Installation does **not** update the existing app reliably.
- Android V3 is obvious in the banner. If the title still reads **EXPERIMENTAL** and buttons are numbered 1, 2, 3, then the old APK is installed.
- Automatic demo session transfer is only enabled for the **single attempt** after tapping **CONECTAR POCKET DEMO** and explicitly approving. It does not reuse Chrome cookies, run unattended, bypass login, or save credentials. If Xtreme is not logged in, the user must log into the panel and manually retry the in-memory handoff.
- Transfer is never represented as success before the Xtreme UI reports **DEMO CONFIRMADA**. Confirmation check times out after 30 seconds and does not trigger orders.

## V4 — improved session feedback and manual trial
- Android header contains V4; do not assume any older APK has these changes.
- The Android embedded Xtreme dashboard ALWAYS hides the old SSID field and its F12 instructions (the DOM connection button remains for a one-time, consented handoff).
- A foreground-only status monitor runs every 15 seconds, even when the Pocket Option browser is visible, to reduce the original server's 120-second idle-disconnect risk. It makes only a user-authenticated status request and NEVER sends orders. Disconnects caused by broker refusal or Android backgrounding still require reconnection.
- TESTE MANUAL 5S selects an available OTC asset if necessary, clicks Analisar ativo (subscribes to price stream), and scrolls to the manual 5-second order controls. This does NOT place an order. The user must explicitly confirm one demo trade after real ticks arrive; only a broker-verified five-second close unlocks automated demo.

## V5 — visible manual confirmation and order response

- The embedded Xtreme web view uses an Android-native confirmation dialog ONLY for the expected manual demo trade message from the verified Xtreme domain. It never auto-confirms an order and does not intercept Pocket Option dialogs. Cancel means no request should be sent.
- Android-injected, ephemeral client-only diagnostics show the backend response to POST /api/order beside the manual buttons instead of relying on the top-of-screen status that is overwritten during polling. The diagnostic does not read or persist any SSID, password, Authorization header or order payload.
- HTTP 200 means the app server *received* the request, **NOT** that Pocket Option accepted or settled a trade. Success requires broker event/history confirmation. On ambiguous failure, check the broker before repeating.
- The original Render web app and all broker-side checks remain unchanged. In particular, automatic DEMO remains locked until a broker-verified five-second manual order has settled.
