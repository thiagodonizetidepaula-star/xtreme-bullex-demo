## V41 — Agenda automática DEMO 10h, 14h e 20h (horário de Brasília)

- **Exclusivamente DEMO. Conta REAL continua bloqueada.** O usuário
  precisa conectar e confirmar a Pocket Option DEMO, selecionar
  estratégia, timeframe, expiração, valor, payout mínimo e stops e tocar
  **ATIVAR AGENDA DEMO**. Nunca agenda sem autorização no aplicativo.
- O servidor usa o fuso **America/Sao_Paulo** e as janelas diárias
  **10:00–10:10, 14:00–14:10 e 20:00–20:10**. Inicia o radar antes de
  cada horário para aquecer candles reais, mas **nenhuma ordem pode ser
  enviada antes do início da janela ou depois de seu encerramento**.
  Sem sinal confirmado dentro da janela, pula o horário; não recupera
  operações atrasadas. O limite é **uma tentativa de envio por horário**
  e no máximo três por dia, não três operações garantidas.
- O mesmo radar de todas as estratégias ZigZag/Fractal, técnicas e
  Triângulo RIGOROSO procura sinais reais com payout >80%, saldo e
  cotação atual; uma ordem pendente bloqueia as demais. Não permite
  Martingale, observação sem ordens ou teste único na agenda.
  Expiração ainda não confirmada exige entrada de valor 1 DEMO.
  Stop Win/Loss diário bloqueia os horários seguintes.
- Um horário é **consumido antes do envio ao broker**: falha de rede,
  ordem rejeitada ou resposta ambígua nunca reenvia a ordem no mesmo
  horário. Só resultado oficial vinculado ao ID da ordem libera a
  pendência. Os botões de PARAR e DESATIVAR AGENDA impedem novas ordens
  (não cancelam ordens já abertas na corretora).
- O agendador roda no servidor, não depende de o Android ficar aberto,
  **desde que o processo Render e a sessão WebSocket DEMO continuem
  ativos**. Render gratuito pode dormir ou reiniciar; a sessão DEMO,
  autenticação da corretora e a agenda **não são persistidas nem
  retomadas automaticamente**. Ao reiniciar ou desconectar, o usuário
  precisa reconectar e reativar. **Não há garantia de operação em
  horários exatos nem de serviço 24h**.
- O status de cada janela (aquecimento, próxima, consumida ou perdida)
  aparece no painel. Testes automatizados não substituem validação
  operacional em uma sessão DEMO autenticada.

## V40 — Operar automaticamente em DEMO e comparar qual estratégia performa melhor

- As oito estratégias técnicas **agora vêm selecionadas em OPERAR
  AUTOMÁTICO · somente DEMO**, em vez de observação. **Nenhuma ordem
  inicia sozinha**: usuário deve conectar a Pocket Option DEMO, escolher
  perfil, timeframe/expiração, valor 1 na primeira expiração não validada,
  stops, limite, e tocar **INICIAR AUTOMÁTICO DEMO**. A opção
  **APENAS OBSERVAR** continua disponível.
- O **Triângulo Breakout RIGOROSO** também permite operação DEMO
  automática contínua por escolha explícita, sem exigir aprovação
  anterior de paper trading; o usuário está justamente coletando
  resultados reais da conta DEMO. Não confundir essa permissão com
  validação de rentabilidade. Modo EQUILIBRADO permanece restrito a
  observação ou teste único. Controles de expiração, valor inicial 1,
  fechamento confirmado, payout, saldo, stop, limite, cooldown,
  expiração oficial e uma ordem pendente continuam obrigatórios.
- Aba **Histórico → Comparar estratégias**: combina operações
  **WIN/LOSS/EMPATE oficialmente confirmadas pela corretora** da sessão
  com até 300 registros privados anteriores salvos no Supabase (JWT,
  RLS e filtro adicional por user_id). Remove duplicatas por ID,
  exclui ordens pendentes e resultados contraditórios, e mostra
  **número de operações, WIN/LOSS, taxa de acerto, lucro/prejuízo
  líquido e ROI sobre valor total apostado** por perfil. Filtro por
  expiração (3s, 5s, M1, M2, M3, M5) permite comparações mais justas.
  Menos de 30 operações são marcadas **amostra inicial**; nem uma
  amostra maior prova superioridade sem validação fora da amostra.
- A comparação usa exclusivamente resultados oficiais da conta DEMO,
  não sinais simulados, observações ou backtests. O histórico é
  isolado por usuário e a memória do painel é limpa ao trocar conta
  ou zerar o histórico. Se o banco estiver indisponível, o painel
  mostra explicitamente apenas a sessão atual.
- **Não promete 70% de acerto** e não opera em conta real.

## V39 — Múltiplas estratégias técnicas, observação/DEMO e varredura OTC >80%

- **⚙ Configurações / Estratégia** now exposes the original unchanged
  **ZigZag + Fractal**, **ZigZag zonas**, existing **Triângulo Breakout**,
  and **eight independent experimental** closed-candle engines:
  EMA8/21+ADX trend, EMA swing/pullback, support/resistance breakout,
  support/resistance rejection, Bollinger channel breakout,
  RSI+Bollinger reversal, confirmed candlestick patterns, MACD+ADX.
  The *News/Economic* option is visibly disabled until a verifiable,
  time-stamped economic calendar feed is integrated; no invented news.
- Technical engines operate on **verified closed OHLC candles only**,
  using the existing `VerifiedBars` and broker historical validator,
  with ATR, EMA, ADX, RSI, MACD and Bollinger filters. 42 consecutive
  completed bars warm up; incomplete/sparse/gapped candles never authorize
  orders. Historical imports seed context but do not replay old signals.
- Each new technical strategy has **OBSERVAÇÃO sem ordens** as the
  default. The operator may explicitly select **TESTAR AUTOMÁTICO ·
  somente DEMO**, subject to confirmed DEMO account, verified live feed,
  expiry compatibility, payout, risk stops, broker expiry validation,
  cooldown and **one unresolved order at a time**. The first unvalidated
  expiry requires stake 1 DEMO. The operator must manually start.
  These profiles have **no independent out-of-sample profitability
  validation** and no promised accuracy. Do not conflate expiry
  validation with statistical strategy approval.
- Technical **analysis timeframe / option expiry** research combinations:
  5s chart → 3s/5s; M1 → 60s/120s; M2 → 120s/180s; M5 → 300s.
  These are **selectable research combinations**, not broker-confirmed
  expiry availability or proof that any one is profitable. Original
  ZigZag timeframe/expiry combinations remain unchanged.
- The market radar subscribes and monitors **all open OTC DEMO symbols
  with broker payout strictly >80%**, additionally respecting the
  operator-selected minimum (UI default 80%). The old hard-coded
  radar 88% floor and 20-asset status display cap were removed.
  A requested subscription is not proof of a live stream; every order
  requires independently verified fresh real quotes.
- Each submitted DEMO order now records its strategy, expiry and Gale
  level in the existing audit/history. The opt-in 1×2 Gale remains
  separate from the technical entry logic and follows the existing
  official-LOSS/next-candle/stop-budget rules; it is disabled for
  observation, zones and triangles.
- **70% accuracy is a research target, not a guarantee**. No new
  profile is labeled validated. Chronological walk-forward analysis
  with payout-adjusted net returns, confidence intervals and
  independent broker DEMO outcomes is required to evaluate it.

## V38 — Martingale opcional 1 Gale ×2 na próxima vela (DEMO)

The clean **⚙ Configurações** tab now provides an **unchecked by default**
opt-in checkbox `Martingale · 1 Gale ×2 na próxima vela (DEMO)`. The user must
enable it **before manually starting auto**. It is sent as boolean
`gale_enabled` to the existing DEMO ZigZag + Fractal strategy. The ZigZag
signal detector is not modified, but a *separate follow-up* may be sent after a
confirmed losing trade, independent of a new ZigZag setup:

- Only after a **broker-acknowledged, matched, payout-consistent official LOSS**,
  with **broker-validated option duration** and a live current watch on the
  **same instrument**. An unknown or mismatched duration does not arm Gale.
- Exactly **one follow-up** (`gale_level=1`) at **2× the losing stake**,
  in the **same CALL or PUT direction** and using the configured expiry.
  The next real candle is based on the selected scan timeframe (5s/M1/M2).
  The bot waits for the **first fresh tick near its opening** (≤1s for
  5s, ≤2s for M1/M2). If that opening tick is missed, disconnected, stale
  or the candle window advances, the Gale is discarded (no late retry).
- The usual 10-second signal cooldown is bypassed **only for this one
  broker-validated Gale**; otherwise the ordinary ZigZag scanner, pause,
  expiry and order checks remain untouched.
- **One unresolved order maximum**, **confirmed DEMO only**, available
  asset and payout floor, balance, stake ≤100, max-order count,
  stop-win/stop-loss and an additional hypothetical **worst-case full
  Gale loss** check. Never exceeds the configured stop-loss budget.
  After the follow-up settles, it **cannot trigger another Gale**.
- The server never assumes a WIN/LOSS based on an expired timer: it waits
  for the matched official broker result. Gale status is visible in
  Configurações. Any closed/rejected/no-feed failure fails safe.
- Martingale multiplies possible losses and **cannot guarantee
  recovery or profit**, even on DEMO; keep the checkbox OFF unless
  deliberately testing the escalation.

## V37 — ZigZag + Fractal original restaurado · pendências DEMO conciliadas automaticamente

As requested, restored the **pre-Heikin-Ashi V32 ZigZag + Fractal** broker,
radar, original OHLC builder, and clean UI. Heikin Ashi is no longer an
entry rule, chart filter or displayed indicator. ZigZag, Fractal and Price
Action logic are *not modified*; the usual DEMO stake, chosen expiry,
maximum-order count, stops, payout, cooldown and single unresolved position
guard remain.

**Official trade result handling is improved without replaying trades:**
- A new DE​MO trade still requires an explicit start of auto. The existing
  `successopenOrder` event must acknowledge that **exact requestId** and
  return the broker order ID.
- `successcloseOrder` and `updateClosedDeals` are both accepted as official
  closing-result sources. They may contain a single deal, an array, or
  `data.deals`; **only an exact broker order ID match** can settle the
  pending record. A close that arrives before its open ACK is cached briefly
  and reconciled only after the matching ACK arrives.
- Upon verified broker close with internally consistent opening/closing
  prices and payout, WIN/LOSS/EMPATE is registered, the pending flag is
  cleared automatically, and (if the user-activated DEMO scanner is still
  running) it resumes **new** signal checks after the configured cooldown.
- An official `failopenOrder` with the exact requestId releases a rejected
  pending request as `REJEITADA` and halts auto to avoid repeating a
  potentially unsupported order.
- On the expiry-aware timeout, a pending order remains blocked, but a
  running DEMO scanner does not unnecessarily stop merely because the
  official close is delayed. A later matched close will release it without
  manual user action. There is **no unsafe time-only release**, invented
  WIN/LOSS, assumed balance update, trade retry, or automatic real-money
  execution.
- If Pocket Option never sends enough authenticated close information,
  automatic reconciliation cannot prove the position closed and the
  manual reconciliation fallback remains available. This is a limitation
  of the unofficial integration rather than an automatic-trade permission.

Tests cover close-before-ACK, late closes, both close-message shapes, id
mismatches, explicit rejections, no replay and restoration of V32 controls.
Automated regression tests are not the same as a live broker DEMO execution
test.

## V36 — Heikin Ashi: operar somente após a última vela de cor minoritária

Original **ZigZag + Fractal engine is unchanged**; the Heikin Ashi module
still considers the most recent short slice of real, fully closed broker
candles and votes green versus red. The HA filter adds a causal entry gate:
- If **green > red**, a fresh ZigZag CALL signal is eligible only when
  the latest **closed Heikin Ashi candle is green** and has closed **after
  the most recent red (minority) candle** in the available short history.
- If **red > green**, a fresh ZigZag PUT signal is eligible only after
  the most recent minority **green** is followed by a confirmed **red**.
- An active/recent minority-colored last candle, a doji/neutral candle,
  a color tie, strong wicks, sideways market or a ZigZag signal pointing
  against the predominant color vetoes the trade. No entry on the
  minority candle, and no repaint or anticipation of a future candle.
- If all recent candles are the predominant color, no new counter-color
  bar is forced: the uninterrupted dominant sequence can still pass
  the HA filter, but a **new current** ZigZag/Fractal signal is required.

The HA filter exposes `last_minority_time`, `last_color`,
`bars_after_minority` and `entry_after_minority` for diagnosis. Historical
signal directions and the underlying ZigZag, expiration, stop, payout,
cooldown, confirmed-DEMO and broker order paths are preserved. No live
win-rate or profitability is inferred from synthetic regression tests.

## V35 — Heikin Ashi: votação rápida das cores recentes

**Requested change: Heikin Ashi only.** Original ZigZag + Fractal engine,
confirmed-pivot entries and all DEMO order/risk limits are unchanged.

No 30-minute lookback or 30-minute warmup. The filter uses only the latest
consecutive genuine CLOSED broker candles available before a newly confirmed
ZigZag entry: up to **36 candles of 5s (3 minutes)**, **10 candles of M1**
or **5 candles of M2**. Broker history for 5s now requests about 3 minutes
instead of half an hour (higher timeframes request enough data for ZigZag).
Minimum actual contiguous candles for this filter: 12, 6 and 4 respectively;
ZigZag retains its own longer pivot warmup if necessary.

The HA color with the **larger count** chooses CALL or PUT; a strict
58% majority and 16-point edge are no longer required. An exact tie blocks.
Existing checks still block sideways movement, dojis, excessive wicks,
contradictory ZigZag/Fractal signals, delayed data and any stale/unverified
broker quote. The presence of a green/red majority **does not itself
trigger an entry**; the original ZigZag+Fractal must signal, and the broker
must be in confirmed DEMO mode. The UI reports colored candle counts
rather than an irrelevant "minutes analyzed" wait.

No profit-rate promise is made. A small majority may be noisy; evaluate
Win/Loss and actual broker DEMO settlements separately.

## V34 — Correção: Heikin Ashi retroativo (NÃO esperar 30 minutos)

The **30 minutes are a maximum backward-looking window**, not a 30-minute
warmup or a requirement to watch 360 new candles. Immediately after
Pocket Option DEMO live-quote verification, the app requests broker
historical OHLC for the selected chart: ~30m past for 5s/M1, and enough
extra M2 bars to keep the existing ZigZag pivot detector functional.
These are **already closed historical broker candles**, never invented.
It never trades from a historical/unfinished candle; a fresh, closed
ZigZag/Fractal signal and current quote are still required.

The Heikin Ashi filter reads ONLY the last <=30m of history; if fewer
actual candles are available, it can operate on a real **contiguous
shorter suffix** (5s: at least 34 closed bars, M1: at least 10, M2:
at least 5), subject to all previously required wick, doji, trend and
sideways checks. It counts only the included historical candles, and the
dashboard shows **actual minutes analyzed**, instead of demanding a 30m
wait. This is independent of ZigZag's own required confirmed-fractal
history; no data, gaps or stale price feeds are never guessed into a
signal. When the broker provides 30m of history, the bot can evaluate
that immediately, not after 30m of running.

The app retains DEMO only, user-controlled start, a single unresolved
order, cooldown, payout and stop controls. The color majority is not a
guarantee of profitability or a reliable forecast of 3s/5s outcomes.

## V33 — Filtro Heikin Ashi por maioria das velas dos últimos 30 minutos

The **only user-facing strategy remains ZigZag + Fractal**. On the DEMO
automatic scanner, prior to every ZigZag signal becoming a Pocket Option order,
calculate **Heikin Ashi from real CLOSED contiguous OHLC broker candles**:
- **5s:** 360 completed consecutive 5-second bars; **M1:** 30 bars; **M2:** 15 bars. No candles from the current forming bucket, historical gap, stale stream or artificial interpolation.
- Count **green versus red** HA candles over exactly the last 30 minutes; require a clear >=58% winning color majority with >=16 percentage-point gap. More greens means CALL-only; more reds PUT-only. A contradictory ZigZag/Fractal signal is discarded.
- Last candle direction and latest 2 minutes must still support that 30m direction.
- Reject dojis, body-to-range weakness and many both-sided wicks (including last two candles); reject low net displacement and low directional movement efficiency as **sideways**. Rejected signals do not place orders.
- A prior closed-candle HA opening may seed the recursive conversion, but vote counts never include candles from before 30 minutes. HA colors are *synthetic-derived indicators*, not broker execution prices.
- Require the latest real ZigZag candle to have just closed. Old or sparse historical data never create new orders. Broker history reading for 5s was expanded from 90 to 450 bars and its deque increased to 500 so a genuine 30m trend can be evaluated.

The **Operação** tab shows the counts and reasons for each chosen chart. Original
ZigZag/Fractal, stops, configured order limit, cooldown, official result wait,
expiry validation and DEMO-only authorization are unchanged. The filter may
substantially reduce entries, particularly while history is unavailable. It
cannot guarantee that winning-color majority predicts the next 3s/5s/M1 expiry;
it is a directional filter to test, not a verified profit improvement.

## V32 — Uma única estratégia visível: ZIGZAG + FRACTAL · automático DEMO com múltiplas entradas

The clean V31 Android/Web panel now exposes **ZIGZAG + FRACTAL only** in the strategy dropdown. User selects a separate chart timeframe:
- **5s closed candles:** broker expirations 3s, 5s or M1 (60s).
- **M1:** expiry 60s.
- **M2:** expiry 60s, 120s or 180s.
Existing triangle/price-action engines remain in source for regression and historical compatibility, but are not selectable in the V32 screen or auto order path.

The same existing REAL DEMO ZigZag/Fractal scanner is explicitly configured with `strategy=zigzag_fractal`, `scan_all=true`, `triangle_mode=false`, `triangle_trial_only=false`, `zone_mode=false`. It is a **continuous risk-capped session**, not the old one-shot experimental triangle test. The maximum number of orders is user-configurable **1–1000** (default 20). The bot can submit multiple independent entries after each **confirmed broker outcome**. No overlapping pending orders, payout below minimum, stale quote, duplicate signal, stopped session, Stop Win/Stop Loss or violated cooldown can trigger an order. Auto still requires manual start and only a confirmed DEMO account. First-ever expiry validation remains stake-limited to 1 DEMO, but is **not** a one-operation cap for ZigZag. A session is also time-bounded (currently 60 minutes), independent of the configured order cap; it is not guaranteed to remain active 24/7. Trade-count maximum is NOT a guarantee that the bot will find or send that many trades.

The Android native overlay from V16 is a separately installed APK; the newer native experiment can simplify it but changes to the Render web UI cannot rewrite the installed native APK automatically.

## V31 — Conectar pela plataforma (Android) sem copiar SSID

The redesigned Xtreme Tiger settings now prioritize **CONECTAR PELA PLATAFORMA · DEMO** on Android V18 or later, using an origin-scoped `XtremeAppBridge` WebMessage listener. The Android app opens the **official HTTPS Pocket Option site in its in-app WebView** only after explicit user confirmation. The pre-existing experimental Android document-start probe can pick up an outbound **DEMO** authentication packet and hand it to the existing server connection only for that consented attempt. The backend still validates isDemo=1 and confirms the account and balance. A WebView login is **not** proof of bot connection until the backend reports **DEMO CONFIRMADA**.

The native bridge accepts **only the exact HTTPS Xtreme Tiger origin and its main frame**, with only the literal `connect-demo` command. No trade/order command is exposed. It does **not** retrieve Chrome cookies, passwords or real account sessions; Android's platform support or broker login changes may prevent connection. The original manual SSID element remains in the DOM for backward-compatible handoff; it is hidden from Android interface and behind optional advanced details in ordinary browsers.

**Important browser difference:** on Windows/Chrome, there is no official cross-site OAuth integration. The button **ABRIR SITE OFICIAL DA POCKET OPTION** opens the official site, **but does not connect the server or import credentials**. Connection without SSID needs the Android native bridge, and the native experiment still depends on the broker permitting the WebView login.

The Android V18 source and APK build belong to the isolated `experiment/android-pocket-demo-assist` branch; the Render deployment serves only the new web UI. An Android APK build is not inferred from a successful Render build, and a previous native APK may need uninstalling before installing a differently signed debug build. Do not claim that the broker connection is tested until a user's own authenticated DEMO status verifies it.

## V30 — Xtreme Tiger: painel limpo de operações (Android web/PC)

The existing authenticated app now uses a mobile-first **three-tab** UI:
- **Operação**: current DEMO asset and connection, prominent WIN / LOSS and session win-rate, live candle-close countdown based only on a recent real broker feed, orange animated flame countdown for candle close **or** a pending DEMO option expiration, original signal, original start/stop controls and a **Pausar** shortcut. Pausar deliberately calls the existing stop endpoint (halts new entries; restart manually). Chart is hidden in a collapsible section but reads the exact same real quote data.
- **⚙ Configurações**: existing asset, strategy, analysis timeframe, option expiry, quick tick-based input modes, optional triangle filters, operator mode, DEMO session connection and settings for stake, minimum payout, stop win/loss, maximum orders and cooldown. **Martingale is visibly disabled** because the current backend does not implement a tested gale system; no fictitious button or live progression is introduced.
- **Histórico**: real server DEMO session history, outcome, asset, direction, expiry, time and net amount; existing reset-history action is preserved. Diagnostics remain available under settings.

A V30 UI is served via `/xtreme_ui.js` and `/xtreme_ui.css` on the existing server and loads *after* original `/app.js`; it only relocates original DOM nodes and reuses their event listeners. It does not change Pocket Option authentication, Supabase, the DEMO order protocol, risk constraints or strategy logic. It never counts down to a *guaranteed trade*: absent a pending order, the flame means **time until the next candle closes**; trades still require a validated signal and user-chosen automatic DEMO mode. Timer is withheld if quotes are stale or account is disconnected. Countdown uses client clock and therefore is an estimate, not the broker's guaranteed settlement clock.

The gray Android-native buttons belong to the older installed APK WebView shell and **cannot be removed from the web repository** alone. The cleaner V30 content will appear inside the embedded web view as well as on desktop; updating native overlay requires a new separately signed Android APK. No APK was created by this web update.

## V27 — TRIÂNGULO BREAKOUT 5s: leitura equilibrada + expiração 3s/5s DEMO

The triangle strategy can be explicitly configured with **real closed 5-second chart candles** and **3-second or 5-second option expiry**. These are separate clocks. The Android/web selector defaults to 5s analysis for *new* triangle selections; earlier active M1/M2/M5 selections are preserved. The 3/5-second choices only appear with 5s analysis because M1 candles cannot establish a 3s outcome.

**Balanced mode** reduces experimental candle thresholds (body >=52%, 2 of last 3 candles aligned, wick/close filters, ATR margin 0.15 instead of 0.22, 26 closed 5s candles for initial context instead of 34) while **still rejecting** doji, sideways, weak bodies, oversized wicks, old or incomplete candles, and false/wick-only breakouts. This does not imply higher accuracy. Original *strict* mode remains selectable and unchanged for previous timeframes.

Three explicit execution modes:
- **Observation:** zero orders, logs signal timestamps and direction. Default.
- **One DEMO trial (3s or 5s ONLY):** user opts in explicitly and uses stake **exactly 1 (USD DEMO)**. Engine uses verified live quote feed and closed 5s triangle pivot/fractal/Price Action confirmation, broker's payout floor, cooldown and one pending order guard. It sends **at most one DEMO order** then automatically stops until user restarts. Trial verifies request/acknowledged official close and expiry duration; it **does not** declare the strategy profitable or approved for continuous operation. 3s signals older than 1 second are discarded.
- **Continuous DEMO:** remains blocked until the original chronological holdout and broker-verified expiry approval, with original strict sensitivity. A trial result alone does not approve continuous operation. Real money is never enabled.

UI shows clearly whether selected mode is observing, a one-shot test, or eligible for continuous validation. Prior trades and other strategy modes stay untouched. Synthetic unit tests are *not* an assertion that Pocket Option actually accepts and settles every 3s/5s option. In particular, 3s is more sensitive to delays, and expiry shorter than chart timeframe cannot be backtested using OHLC alone.

## V25 · TRIÂNGULO BREAKOUT — PRICE ACTION · observação primeiro

Added as a separate, opt-in strategy to the existing Android/Web Xtreme Tiger and
existing verified Pocket Option DEMO scanner. **Existing profiles, login, orders,
placar and history are preserved.** This strategy reads real, closed, consecutive
5-second, M1, M2 or M5 candles using live DEMO ticks or verified prior broker
history. No screenshots or made-up price lines are used.

The engine confirms highs/lows using **two later CLOSED candles** (Fractal 2),
detects:
- **Ascending:** two roughly horizontal resistance swing highs and ascending
  swing lows; convergence and positive wedge width are required.
- **Descending:** roughly horizontal support swing lows and lower highs.
- **Symmetric:** lower swing highs and higher swing lows.
- **Breakout:** fresh candle closes beyond converging boundary by >=0.22×ATR,
  closing beyond prior candle high (CALL) or low (PUT), with strong body,
  trend-aware candle psychology and no overlapping previous order.
- **Retest:** later closed candle rejects the already-broken boundary, confirms
  the breakout direction, and passes body, wick and lateralization checks.
  User can choose breakout, retest or both.
- **False break:** a wick only or closure inside the zone never triggers a signal.
- **Optional EMA 8/21 or ADX >=18** filters; ATR margin is built into the
  strategy. Horizontal support/resistance zones and the two colored triangle
  edges are drawn from confirmed historical pivots.

The chart renders identified triangles and real candle data for 5s/M1/M2/M5,
with a translucent forming bar. **Observation mode is always the default** and
does **not** send orders. In observation mode, the server logs the symbol,
timeframe, expiry, pattern, direction, approximate signal-close price and time,
separately from the broker's real order history.

Before DEMO automatic mode can be enabled, the server needs a chronological
out-of-sample paper validation for the EXACT symbol/timeframe/expiry and a
verified broker DEMO expiry. No sample = blocked. Backtesting uses a full
walk-forward, at least 250 valid consecutive bars, train 70% then holdout 30%,
at least 60 train signals and 25 holdout signals, and positive payout-adjusted
net results in both sets. Group performance by UTC hour. Simulated entry uses
the next completed bar's opening price, so it is NOT proof of broker fills,
profitability or timing. Expirations below candle timeframe are explicitly
*not* validatable by those OHLC bars and remain blocked pending tick-level
outcome data. Report status and reasons in the app.

Initial supported expiration choices: 3s,5s,60s,120s,180s,300s subject to
the chosen analysis timeframe. The separate automatic demo path still enforces
fresh quotes, DEMO session, payout minimum, stake controls, cooldown, stop
win/loss, single pending order and max operations. It never operates real money
or auto-activates merely because the app was opened.

**IMPORTANT:** This is a research/DEMO strategy, not a confirmed profitable
trading system. A walk-forward paper pass alone cannot prove real order
execution quality, and small sample results cannot justify live trading.

## V24 — Gráfico ao vivo e zonas Price Action (DEMO)

Selectable **GRÁFICO AO VIVO · SUPORTE, RESISTÊNCIA E PRICE ACTION 5s** mode in the existing Android/web app (no new APK or server). The graph uses actual fresh Pocket Option DEMO quote ticks; it shows **closed 5-second candles** plus a visually translucent forming candle, which is **never traded**. Only chart streams actually received are displayed, not the screenshot price/asset and not fabricated prices.

The engine builds two confirmed pivot-based trendlines:
- **Ascending SUPPORT (green)** from two rising **Fractal-2 swing lows**.
- **Descending RESISTANCE (blue)** from two falling **Fractal-2 swing highs**.
- **Horizontal support/resistance zones** from the latest fully confirmed fractal low/high, with region width relative to median OHLC range.
- Each fractal requires two CLOSED candles to its right; the current and prior signal candles cannot manufacture pivot confirmation. Pivots must show an observed ZigZag-like swing amplitude above the typical range.

Trade candidates are emitted **ONLY after a new 5-second candle CLOSES** (never just touches the line): BUY on confirmed close above downward resistance or on a positive reversal/rejection of an observed support region; SELL on confirmed close below rising support or bearish reversal/rejection of a resistance region. Close must also break the prior candle high (BUY) or low (SELL), and pass the **full psychology filter**: 2-of-3 candle colors in that direction, full real candle body, no indecision, no congestion, no exhaustion, and only verified current live DEMO feeds. A single asset cannot emit two signals within four closed bars.

The new mode is **opt-in**: starting the existing DEMO automatic scanner remains an explicit user operation; it does not start placing orders merely because the chart opened. Possible expiries: **3s, 5s, 60s, 120s, 180s**, all while ANALYZING closed 5s candles. Existing payout, risk stops, cooldown, single pending order and demo amount-1 first-expiry validation remain. M1, M2 and previous 5s modes remain untouched. Historical broker candles may seed the technical context, but cannot themselves open an order.

**Accuracy/limitations:** The on-screen lines are experimental approximations inferred from observed OHLC pivot history; they are not native broker drawings and can differ from manually drawn trendlines on the screenshots. One confirmed breakout can still be a false breakout. No return/profit or "high precision" is guaranteed. CI tests use synthetic price paths; the live feed, broker 3s/5s/60s/120s/180s duration support and actual fills require verifying in an authenticated DEMO session.

# Xtreme Tiger Pocket 5s

## V23 — Filtro de psicologia de candles (5s ZigZag + Fractal + Linha + Price Action)

The 5-second ZigZag strategy now has a **mandatory closed-candle psychology veto** after all its existing confirmations, to avoid trading congestion and indecision. It NEVER creates a signal on its own. Directional candlestick quality rules for the last 12 fully completed **5s** OHLC bars:

- BUY requires a green breakout candle; SELL a red breakout candle. The candle's body must be **at least 60%** of its range; the close must be within the direction's nearest **24% of range**, opposing wick at most 26%.
- Count last **3 closed candles**; at least **2 must match the entry direction**. The current body must be **at least 110% of the previous 11-candle median body**, and its whole high-low range at least 78% of the recent median range. This is a descriptive candle-strength metric, **not a win-rate percentage**.
- Sideways veto: the ten-candle high/low span must exceed **2.5×** the previous median candle range, and directional close-to-close efficiency over seven candles must be **at least 0.29**. Veto excessively extended candles when range exceeds **3.25×** the median.
- Failed checks abort the signal and restore the unconsumed ZigZag pivot state. The dashboard displays the count (e.g. `2/3`), body percentage, directional efficiency and why a signal was blocked.
- M1 and M2 ZigZag strategies remain unchanged. The 5-second candle analysis still allows **3-second**, **5-second**, and **60-second** DEMO expiry, with stale-3s-signal rejection, verified live feeds, user-controlled demo risk stops and one pending order maximum.

The thresholds are experimental and can reject valid moves or admit losing trades. **No trading indicator can guarantee an absence of sideways losses or a high win rate.** Regression tests use synthetic price histories; broker-integrated live DEMO behavior and profitability are not established by CI tests.

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
