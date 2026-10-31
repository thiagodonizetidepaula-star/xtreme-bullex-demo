package com.xtremetiger.pocketdemoassist

import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.JsResult
import android.webkit.WebResourceRequest
import android.webkit.WebStorage
import android.webkit.WebView
import android.webkit.WebViewClient
import android.webkit.WebResourceError
import android.webkit.WebResourceResponse
import android.net.http.SslError
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature

/**
 * EXPERIMENTAL / DEMO ONLY.
 * It is NOT an official Pocket Option OAuth integration.
 * Nothing in this file publishes changes to the existing Xtreme Tiger website.
 */
class MainActivity : Activity() {
    private val tigerUrl = "https://xtreme-pocket-5s.onrender.com/"
    private val brokerUrl = "https://pocketoption.com/"
    private val brokerOrigins = setOf("https://pocketoption.com", "https://*.pocketoption.com")
    private var capturedPacket: String? = null  // volatile only; no persistence or logs
    private lateinit var tiger: WebView
    private lateinit var broker: WebView
    private lateinit var platform: WebView
    private lateinit var status: TextView
    private lateinit var transferButton: Button
    private lateinit var connectionIssuePanel: LinearLayout
    private lateinit var connectionIssueText: TextView
    private var brokerLoadFailed = false
    // One explicit per-attempt authorization: auto-send only a detected DEMO packet.
    private var autoTransferApproved = false
    private lateinit var brokerState: TextView
    private val monitorHandler = Handler(Looper.getMainLooper())
    private var monitorActive = false
    private val monitor = object : Runnable {
        override fun run() {
            if (!monitorActive || !::tiger.isInitialized) return
            tiger.evaluateJavascript("""
                (() => {
                    const active = document.getElementById('dashboard')?.hidden === false;
                    if (!active) return 'LOGIN';
                    const badge = document.getElementById('connection')?.textContent?.trim() || 'DESCONECTADO';
                    const age = document.getElementById('age')?.textContent?.trim() || '—';
                    // Status-only request while foreground; this NEVER creates an order.
                    if (typeof api === 'function') api('status').catch(() => {});
                    return badge + '|' + age;
                })()
            """.trimIndent()) { raw ->
                if (!monitorActive) return@evaluateJavascript
                val x = jsValue(raw)
                brokerState.text = when {
                    x == "LOGIN" -> "Estado: entre no painel Xtreme antes de conectar a corretora."
                    x.startsWith("DEMO CONFIRMADA|") ->
                        "Estado: DEMO CONFIRMADA • Último tick: " + x.substringAfter("|")
                    x.startsWith("CONECTANDO|") -> "Estado: conectando à DEMO…"
                    x.startsWith("VALIDANDO DEMO|") -> "Estado: aguardando confirmação DEMO…"
                    else -> "Estado: DEMO desconectada. Toque CONECTAR POCKET DEMO."
                }
            }
            monitorHandler.postDelayed(this, 15000L)
        }
    }
    private var probeSupported = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WebView.setWebContentsDebuggingEnabled(false)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(10, 15, 19))
        }
        val header = TextView(this).apply {
            text = "XTREME TIGER  •  DEMO  •  ANDROID V15"
            textSize = 14f
            setTextColor(Color.rgb(193, 238, 116))
            setPadding(18, 20, 18, 10)
        }
        status = TextView(this).apply {
            text = "V15 DEMO: escolha RÁPIDA 3-45 segundos ou M5/M1 1-30 minutos. Prazos separados para Android."
            textSize = 12f
            setTextColor(Color.WHITE)
            setPadding(18, 8, 18, 14)
        }
        brokerState = TextView(this).apply {
            text = "Estado: DEMO desconectada."
            textSize = 12f
            setTextColor(Color.rgb(193, 238, 116))
            setPadding(18, 0, 18, 10)
        }
        val controls = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(10, 0, 10, 8)
        }
        val openTiger = Button(this).apply {
            text = "PAINEL XTREME"
            setOnClickListener { showTiger() }
        }
        val openBroker = Button(this).apply {
            text = "CONECTAR POCKET DEMO"
            setOnClickListener { confirmBeforeOpeningBroker() }
        }
        val viewPlatform = Button(this).apply {
            text = "VER PLATAFORMA"
            setOnClickListener { showOfficialPlatform() }
        }
        transferButton = Button(this).apply {
            text = "ENVIAR SESSÃO DEMO PARA O XTREME"
            isEnabled = false
            visibility = View.GONE
            setOnClickListener { confirmTransfer() }
        }
        val discard = Button(this).apply {
            text = "LIMPAR SESSÃO"
            setOnClickListener { clearExperimentalSession() }
        }
        val manual = Button(this).apply {
            text = "TESTE MANUAL 5S"
            setOnClickListener { openManualTest() }
        }
        val start = Button(this).apply {
            text = "M5 → M1 / V12"
            setOnClickListener { showSignalPanel() }
        }
        val stop = Button(this).apply {
            text = "PARAR BOT"
            setOnClickListener { stopDemoBot() }
        }
        fun pair(a: Button, b: Button) = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(a, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(b, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
        controls.addView(pair(openTiger, viewPlatform))
        controls.addView(pair(openBroker, start))
        controls.addView(pair(stop, discard))
        controls.addView(transferButton)
        connectionIssueText = TextView(this).apply {
            text = "Não foi possível abrir o site oficial."
            textSize = 13f
            setTextColor(Color.WHITE)
            setPadding(14, 10, 14, 10)
        }
        val retryBroker = Button(this).apply {
            text = "TENTAR NOVAMENTE"
            setOnClickListener {
                if (!probeSupported) {
                    status.text = "Este Android não suporta a integração DEMO."
                } else {
                    brokerLoadFailed = false
                    connectionIssuePanel.visibility = View.GONE
                    broker.visibility = View.VISIBLE
                    tiger.visibility = View.GONE
                    status.text = "Tentando o site oficial novamente. Nenhuma ordem será criada."
                    broker.loadUrl(brokerUrl)
                }
            }
        }
        val checkInChrome = Button(this).apply {
            text = "VERIFICAR NO CHROME"
            setOnClickListener {
                autoTransferApproved = false
                status.text = "Abrindo o site oficial no navegador. O Chrome não conecta automaticamente o bot."
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(brokerUrl)))
            }
        }
        connectionIssuePanel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(34, 29, 26))
            visibility = View.GONE
            addView(connectionIssueText)
            addView(pair(retryBroker, checkInChrome))
        }
        val frame = FrameLayout(this)
        root.addView(header)
        root.addView(status)
        root.addView(brokerState)
        root.addView(controls)
        root.addView(connectionIssuePanel)
        root.addView(frame, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)

        tiger = configuredWebView(tigerUrl)
        broker = configuredWebView(brokerUrl)
        // Independent viewer: no demo auth probe or native bridge installed.
        platform = configuredWebView(brokerUrl)
        frame.addView(tiger, FrameLayout.LayoutParams(-1, -1))
        frame.addView(broker, FrameLayout.LayoutParams(-1, -1))
        frame.addView(platform, FrameLayout.LayoutParams(-1, -1))
        broker.visibility = View.GONE
        platform.visibility = View.GONE

        probeSupported = WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER) &&
                WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)
        if (probeSupported) {
            WebViewCompat.addWebMessageListener(
                broker, "XtremeDemoBridge", brokerOrigins
            ) { _, message, sourceOrigin, isMainFrame, _ ->
                if (!isMainFrame || !approvedBrokerOrigin(sourceOrigin)) return@addWebMessageListener
                val candidate = DemoAuthPacket.validate(message.data) ?: return@addWebMessageListener
                runOnUiThread {
                    capturedPacket = candidate
                    transferButton.isEnabled = true
                    transferButton.visibility = View.VISIBLE
                    if (autoTransferApproved) {
                        autoTransferApproved = false
                        status.text = "Sessão DEMO detectada. Enviando ao Xtreme conforme sua autorização..."
                        transferToExistingApp(candidate)
                    } else {
                        status.text = "Sessão DEMO detectada. Faça login no Xtreme e confirme o envio."
                    }
                }
            }
            val script = assets.open("demo-probe.js").bufferedReader().use { it.readText() }
            WebViewCompat.addDocumentStartJavaScript(broker, script, brokerOrigins)
        } else {
            status.text = "WebView deste Android não oferece os recursos necessários. Nenhuma captura será feita. O Xtreme normal continua disponível."
        }
        tiger.loadUrl(tigerUrl)
    }

    private fun approvedBrokerOrigin(uri: Uri): Boolean {
        if (uri.scheme != "https") return false
        val h = uri.host?.lowercase() ?: return false
        return h == "pocketoption.com" || h.endsWith(".pocketoption.com")
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configuredWebView(homeUrl: String): WebView {
        return WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            settings.javaScriptCanOpenWindowsAutomatically = false
            settings.setSupportMultipleWindows(false)
            settings.mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
            isSaveEnabled = false
            webChromeClient = object : WebChromeClient() {
                override fun onJsConfirm(
                    view: WebView?, url: String?, message: String?, result: JsResult?
                ): Boolean {
                    // Only intercept the known manual-order confirmation from OUR Xtreme web app.
                    // Pocket Option prompts retain their normal browser behavior.
                    if (homeUrl != tigerUrl ||
                        Uri.parse(url ?: "").host != "xtreme-pocket-5s.onrender.com" ||
                        !message.orEmpty().startsWith("Enviar uma ordem de ") ||
                        !message.orEmpty().contains("na conta DEMO") ||
                        !message.orEmpty().contains("5 segundos")) {
                        return false
                    }
                    if (result == null) return true
                    AlertDialog.Builder(this@MainActivity)
                        .setTitle("Confirmar ordem MANUAL — conta DEMO")
                        .setMessage(message.orEmpty() + "\\n\\nNão é uma ordem real. Aguarde a confirmação do servidor e da corretora antes de repetir.")
                        .setPositiveButton("Confirmar DEMO") { _, _ ->
                            result.confirm()
                            status.text = "Ordem DEMO confirmada no Android. Veja a resposta perto dos botões de compra/venda."
                        }
                        .setNegativeButton("Cancelar") { _, _ ->
                            result.cancel()
                            status.text = "Ordem manual cancelada. Nada foi enviado por esta tentativa."
                        }
                        .setOnCancelListener { result.cancel() }
                        .show()
                    return true
                }
            }
            webViewClient = object : WebViewClient() {
                override fun onReceivedError(view: WebView?, request: WebResourceRequest?, error: WebResourceError?) {
                    super.onReceivedError(view, request, error)
                    if (homeUrl != brokerUrl || request?.isForMainFrame != true) return
                    val code = error?.errorCode ?: 0
                    val reason = when (code) {
                        WebViewClient.ERROR_TIMEOUT -> "A conexão com o site oficial excedeu o tempo limite."
                        WebViewClient.ERROR_HOST_LOOKUP -> "O Android não conseguiu localizar o domínio oficial."
                        WebViewClient.ERROR_CONNECT -> "A conexão com o servidor oficial não foi estabelecida."
                        WebViewClient.ERROR_IO -> "O Android não conseguiu concluir a leitura da página oficial."
                        else -> "A página oficial não pôde ser carregada (erro $code)."
                    }
                    showBrokerConnectionIssue(reason)
                }
                override fun onReceivedHttpError(view: WebView?, request: WebResourceRequest?, errorResponse: WebResourceResponse?) {
                    super.onReceivedHttpError(view, request, errorResponse)
                    if (homeUrl != brokerUrl || request?.isForMainFrame != true) return
                    val code = errorResponse?.statusCode ?: 0
                    if (code >= 400) {
                        showBrokerConnectionIssue("O servidor oficial respondeu HTTP $code. Não tentaremos contornar restrições de acesso.")
                    }
                }
                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    if (homeUrl == tigerUrl && url?.startsWith(tigerUrl) == true) {
                        val js = assets.open("web-ui-assist.js").bufferedReader().use { it.readText() }
                        view?.evaluateJavascript(js, null)
                    } else if (homeUrl == brokerUrl && !brokerLoadFailed && url != null &&
                               approvedBrokerOrigin(Uri.parse(url))) {
                        connectionIssuePanel.visibility = View.GONE
                    }
                }
                override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                    val u = request?.url ?: return true
                    val host = u.host?.lowercase() ?: return true
                    val allowed = u.scheme == "https" && (
                        if (homeUrl == tigerUrl) host == "xtreme-pocket-5s.onrender.com"
                        else host == "pocketoption.com" || host.endsWith(".pocketoption.com")
                    )
                    if (!allowed && u.scheme == "https" && request.isForMainFrame) {
                        // External SSO/login may break the experiment: do not intercept other sites.
                        startActivity(Intent(Intent.ACTION_VIEW, u))
                    }
                    return !allowed
                }

                override fun onReceivedSslError(view: WebView?, handler: SslErrorHandler?, error: SslError?) {
                    handler?.cancel()
                    if (homeUrl == brokerUrl) {
                        showBrokerConnectionIssue("O certificado HTTPS não foi validado. A conexão foi bloqueada.")
                    } else {
                        status.text = "Certificado HTTPS não validado. Navegação bloqueada."
                    }
                }
            }
        }
    }

    private fun showTiger() {
        tiger.visibility = View.VISIBLE
        broker.visibility = View.GONE
        platform.visibility = View.GONE
    }

    private fun showOfficialPlatform() {
        autoTransferApproved = false
        broker.visibility = View.GONE
        tiger.visibility = View.GONE
        platform.visibility = View.VISIBLE
        if (platform.url?.startsWith(brokerUrl) != true) {
            brokerLoadFailed = false
            connectionIssuePanel.visibility = View.GONE
            platform.loadUrl(brokerUrl)
        }
        status.text = "Visualização do site oficial no Android. Este botão não envia ordens. O acesso depende da rede, disponibilidade e região."
    }

    private fun showBrokerConnectionIssue(reason: String) {
        brokerLoadFailed = true
        autoTransferApproved = false
        capturedPacket = null
        transferButton.isEnabled = false
        transferButton.visibility = View.GONE
        connectionIssueText.text = reason + "\nConfira se o site oficial abre no Chrome. Se não abrir, pode haver indisponibilidade da rede, do serviço ou restrição regional. Não tente contornar bloqueios de acesso."
        connectionIssuePanel.visibility = View.VISIBLE
        broker.stopLoading()
        if (::platform.isInitialized) platform.stopLoading()
        showTiger()
        status.text = "A Pocket Option não carregou. O painel Xtreme permanece disponível."
    }

    private fun confirmBeforeOpeningBroker() {
        if (!probeSupported) {
            status.text = "Seu Android não suporta a captura experimental. Use o Xtreme Tiger normal."
            return
        }
        AlertDialog.Builder(this)
            .setTitle("Conectar somente conta DEMO?")
            .setMessage("Após sua autorização, abriremos a Pocket Option neste navegador interno. Se detectarmos uma sessão DEMO, tentaremos enviá-la AUTOMATICAMENTE ao seu Xtreme Tiger conectado, sem copiar SSID. Você precisa já estar logado no painel Xtreme. Não lemos sua senha nem conectamos contas reais. Esta integração é experimental e pode falhar. Autoriza esta tentativa?")
            .setNegativeButton("Cancelar", null)
            .setPositiveButton("Autorizar DEMO") { _, _ ->
                autoTransferApproved = true
                capturedPacket = null
                transferButton.isEnabled = false
                transferButton.visibility = View.GONE
                brokerLoadFailed = false
                connectionIssuePanel.visibility = View.GONE
                broker.visibility = View.VISIBLE
                tiger.visibility = View.GONE
                platform.visibility = View.GONE
                broker.loadUrl(brokerUrl)
                status.text = "Abra a Pocket Option em modo DEMO. Assim que a sessão DEMO aparecer, o app tentará conectar ao Xtreme automaticamente."
            }.show()
    }

    private fun confirmTransfer() {
        val packet = capturedPacket ?: return
        if (DemoAuthPacket.validate(packet) == null) {
            capturedPacket = null
            transferButton.isEnabled = false
            transferButton.visibility = View.GONE
            return
        }
        AlertDialog.Builder(this)
            .setTitle("Enviar somente sessão DEMO?")
            .setMessage("Este código dá acesso à sua sessão da corretora. Ele será enviado somente ao seu Xtreme Tiger pelo HTTPS, após você confirmar. Nenhuma ordem será criada por esta ação. Verifique que está logado no aplicativo Xtreme.")
            .setNegativeButton("Cancelar", null)
            .setPositiveButton("Enviar ao Xtreme") { _, _ -> transferToExistingApp(packet) }
            .show()
    }

    private fun transferToExistingApp(packet: String) {
        // Send to existing form only after user action. No token in URL, log, or storage.
        showTiger()
        // Never inject the credential-equivalent packet into another domain.
        if (tiger.url?.startsWith(tigerUrl) != true) {
            status.text = "Página do Xtreme indisponível. Volte ao painel e faça login para continuar."
            return
        }
        val quoted = org.json.JSONObject.quote(packet)
        val js = """
            (() => {
                const pane = document.getElementById('dashboard');
                const input = document.getElementById('ssid');
                const btn = document.getElementById('connect');
                if (!pane || pane.hidden) return 'LOGIN_NECESSARIO';
                if (!input || !btn || btn.disabled) return 'FORM_INDISPONIVEL';
                input.value = $quoted;
                btn.click();
                input.value = '';
                return 'ENVIO_SOLICITADO';
            })()
        """.trimIndent()
        tiger.evaluateJavascript(js) { result ->
            // A click is NOT proof of broker authentication. Poll confirmation in Xtreme status.
            when (jsValue(result)) {
                "ENVIO_SOLICITADO" -> {
                    capturedPacket = null
                    transferButton.isEnabled = false
                    transferButton.visibility = View.GONE
                    broker.loadUrl("about:blank")
                    status.text = "Sessão enviada. Aguardando confirmação da conta DEMO pelo servidor..."
                    checkDemoConfirmation(0)
                }
                "LOGIN_NECESSARIO" -> {
                    status.text = "Entre no PAINEL XTREME primeiro. A sessão demo está disponível para reenviar."
                }
                else -> status.text = "Formulário indisponível. Abra o painel e tente novamente pelo botão Enviar sessão."
            }
        }
    }

    private fun checkDemoConfirmation(attempt: Int) {
        if (attempt >= 15) {
            status.text = "Conexão DEMO não confirmada em 30s. Confira o status do Xtreme; não inicie operações."
            return
        }
        android.os.Handler(android.os.Looper.getMainLooper()).postDelayed({
            if (isFinishing || isDestroyed) return@postDelayed
            tiger.evaluateJavascript("""
                (() => {
                    const badge = document.getElementById('connection')?.textContent?.trim() || '';
                    const message = document.getElementById('status')?.textContent || '';
                    if (badge === 'DEMO CONFIRMADA') return 'CONFIRMADA';
                    if (badge === 'DESCONECTADO' && /recusada|encerrada|expirada|indisponível|erro|falha/i.test(message)) return 'FALHA';
                    return 'AGUARDANDO';
                })()
            """.trimIndent()) { result ->
                when (jsValue(result)) {
                    "CONFIRMADA" -> status.text = "Conta DEMO confirmada pelo servidor. O automático depende dos limites e do estado do painel."
                    "FALHA" -> status.text = "A Pocket Option não confirmou a sessão. Confira a mensagem do Xtreme e tente reconectar pela conta DEMO."
                    else -> checkDemoConfirmation(attempt + 1)
                }
            }
        }, 2000L)
    }

    private fun jsValue(raw: String?): String =
        try { org.json.JSONTokener(raw ?: "").nextValue() as? String ?: "" }
        catch (_: Exception) { "" }

    private fun openManualTest() {
        showTiger()
        tiger.evaluateJavascript("""
            (() => {
                if (document.getElementById('dashboard')?.hidden !== false) return 'LOGIN';
                if (document.getElementById('connection')?.textContent?.trim() !== 'DEMO CONFIRMADA') return 'DEMO';
                const select = document.getElementById('asset');
                const subscribe = document.getElementById('subscribe');
                if (!select || !subscribe || subscribe.disabled) return 'INATIVO';
                const otc = [...select.options].filter(x => x.value.endsWith('_otc') && !x.disabled);
                if (!otc.length) return 'SEM_OTC';
                if (!select.value.endsWith('_otc')) select.value = otc[0].value;
                subscribe.click(); // Ask for price stream; does NOT create an order.
                document.getElementById('call')?.closest('.card')?.scrollIntoView({behavior:'smooth',block:'start'});
                return 'COTACOES|' + select.options[select.selectedIndex]?.textContent;
            })()
        """.trimIndent()) { raw ->
            val result = jsValue(raw)
            status.text = when {
                result.startsWith("COTACOES|") ->
                    "Solicitei preços de " + result.substringAfter("|") +
                    ". Aguarde o 'Último tick' mostrar segundos. Só então faça UMA operação MANUAL demo de 5s e aguarde o resultado."
                result == "SEM_OTC" -> "Ainda não há ativo OTC disponível. Aguarde o catálogo ou reconecte a DEMO."
                result == "INATIVO" -> "O painel ainda não está pronto. Aguarde o catálogo e tente novamente."
                result == "LOGIN" -> "Entre primeiro no painel Xtreme Tiger."
                result == "DEMO" -> "A DEMO desconectou. Toque CONECTAR POCKET DEMO; não precisa de SSID."
                else -> "Não foi possível carregar as cotações; confira a conexão."
            }
        }
    }

    private fun showSignalPanel() {
        showTiger()
        status.text = "Conecte DEMO, escolha TIPO DE ANÁLISE e EXPIRAÇÃO. Agora 3, 5, 6, 7 e 10 segundos aparecem direto no modo RÁPIDA."
        tiger.evaluateJavascript("""
            (() => {
                const panel=document.querySelector('.signal-console');
                if(!panel) return 'LOGIN';
                panel.scrollIntoView({behavior:'smooth',block:'center'});
                return 'OK';
            })()
        """.trimIndent()) { raw ->
            if (jsValue(raw) == "LOGIN")
                status.text = "Entre no seu painel Xtreme para ver os sinais DEMO."
        }
    }

    private fun startDemoBot() {
        showTiger()
        tiger.evaluateJavascript("""
            (() => {
                if (document.getElementById('dashboard')?.hidden !== false) return 'LOGIN';
                if (document.getElementById('connection')?.textContent?.trim() !== 'DEMO CONFIRMADA') return 'DEMO';
                const button = document.getElementById('auto');
                if (!button) return 'SEM_BOTAO';
                if (button.textContent.includes('em execução')) return 'ATIVO';
                if (button.disabled) {
                    document.getElementById('call')?.closest('.card')?.scrollIntoView({behavior:'smooth',block:'start'});
                    return 'VALIDAR';
                }
                button.scrollIntoView({behavior:'smooth',block:'start'});
                return 'PRONTO|' + ['amount','stop_win','stop_loss','limit','min_payout']
                    .map(id => document.getElementById(id)?.value || '?').join('|');
            })()
        """.trimIndent()) { raw ->
            val answer = jsValue(raw)
            if (answer.startsWith("PRONTO|")) {
                val v = answer.split("|")
                if (v.size != 6) { status.text = "Configure os parâmetros no painel."; return@evaluateJavascript }
                AlertDialog.Builder(this).setTitle("Iniciar bot SOMENTE DEMO?")
                    .setMessage("Valor: ${v[1]} por entrada; Stop Win: ${v[2]}; Stop Loss: ${v[3]}; Limite: ${v[4]} operações; Payout mínimo: ${v[5]}%.\n\nOperações já enviadas podem continuar pendentes. Confirma?")
                    .setNegativeButton("Cancelar", null)
                    .setPositiveButton("Iniciar DEMO") { _, _ ->
                        tiger.evaluateJavascript("""
                            (() => {
                                const button = document.getElementById('auto');
                                if (document.getElementById('connection')?.textContent?.trim() !== 'DEMO CONFIRMADA'
                                   || !button || button.disabled) return 'BLOQUEADO';
                                button.click();
                                return 'SOLICITADO';
                            })()
                        """.trimIndent()) { result ->
                            status.text = if (jsValue(result) == "SOLICITADO")
                                "Início solicitado. Confirme no painel a mensagem Automático em execução."
                            else "Bot bloqueado. Confira a confirmação DEMO e os limites de segurança."
                        }
                    }.show()
            } else {
                status.text = when(answer) {
                    "VALIDAR" -> "O servidor bloqueou a ativação. Confira a seção do automático e eventuais ordens pendentes."
                    "ATIVO" -> "O automático DEMO já está em execução."
                    "DEMO" -> "A conta DEMO não está confirmada. Reconecte."
                    "LOGIN" -> "Entre primeiro no Xtreme Tiger."
                    else -> "Abra o painel para verificar o automático."
                }
            }
        }
    }

    private fun stopDemoBot() {
        AlertDialog.Builder(this).setTitle("Parar novas operações DEMO?")
            .setMessage("Uma operação já enviada não será cancelada automaticamente.")
            .setNegativeButton("Cancelar", null)
            .setPositiveButton("Parar") { _, _ ->
                showTiger()
                tiger.evaluateJavascript("""
                    (() => {
                        if (document.getElementById('dashboard')?.hidden !== false) return 'LOGIN';
                        const button=document.getElementById('stop');
                        if (!button) return 'SEM_BOTAO';
                        button.click(); return 'SOLICITADO';
                    })()
                """.trimIndent()) { raw ->
                    status.text = if (jsValue(raw) == "SOLICITADO")
                        "Parada solicitada. Confira no painel e verifique ordens pendentes na corretora."
                    else "Abra e entre no painel para parar o bot."
                }
            }.show()
    }

    private fun clearExperimentalSession() {
        autoTransferApproved = false
        capturedPacket = null
        transferButton.isEnabled = false
        transferButton.visibility = View.GONE
        broker.loadUrl("about:blank")
        CookieManager.getInstance().removeAllCookies(null)
        CookieManager.getInstance().flush()
        WebStorage.getInstance().deleteAllData()
        status.text = "Sessão descartada e cookies do navegador interno apagados. Talvez seja preciso entrar novamente."
        showTiger()
    }

    override fun onResume() {
        super.onResume()
        monitorActive = true
        monitorHandler.removeCallbacks(monitor)
        if (::tiger.isInitialized) monitorHandler.post(monitor)
    }

    override fun onPause() {
        monitorActive = false
        monitorHandler.removeCallbacks(monitor)
        super.onPause()
    }

    @Deprecated("Legacy back navigation")
    override fun onBackPressed() {
        if (broker.visibility == View.VISIBLE || platform.visibility == View.VISIBLE) showTiger()
        else if (tiger.canGoBack()) tiger.goBack()
        else super.onBackPressed()
    }

    override fun onDestroy() {
        monitorActive = false
        monitorHandler.removeCallbacks(monitor)
        autoTransferApproved = false
        capturedPacket = null
        tiger.destroy()
        broker.destroy()
        platform.destroy()
        super.onDestroy()
    }
}
