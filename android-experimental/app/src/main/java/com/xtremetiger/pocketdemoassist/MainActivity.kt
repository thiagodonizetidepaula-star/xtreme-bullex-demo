package com.xtremetiger.pocketdemoassist

import android.annotation.SuppressLint
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.SslErrorHandler
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebStorage
import android.webkit.WebView
import android.webkit.WebViewClient
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
    private lateinit var status: TextView
    private lateinit var transferButton: Button
    // One explicit per-attempt authorization: auto-send only a detected DEMO packet.
    private var autoTransferApproved = false
    private var probeSupported = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WebView.setWebContentsDebuggingEnabled(false)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(10, 15, 19))
        }
        val header = TextView(this).apply {
            text = "XTREME TIGER  •  DEMO  •  ANDROID V3"
            textSize = 14f
            setTextColor(Color.rgb(193, 238, 116))
            setPadding(18, 20, 18, 10)
        }
        status = TextView(this).apply {
            text = "V3: entre no PAINEL XTREME e toque CONECTAR DEMO. A conta real nunca será aceita."
            textSize = 12f
            setTextColor(Color.WHITE)
            setPadding(18, 8, 18, 14)
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
            text = "INICIAR BOT DEMO"
            setOnClickListener { startDemoBot() }
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
        controls.addView(pair(openTiger, openBroker))
        controls.addView(transferButton)
        controls.addView(pair(manual, start))
        controls.addView(pair(stop, discard))
        val frame = FrameLayout(this)
        root.addView(header)
        root.addView(status)
        root.addView(controls)
        root.addView(frame, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)

        tiger = configuredWebView(tigerUrl)
        broker = configuredWebView(brokerUrl)
        frame.addView(tiger, FrameLayout.LayoutParams(-1, -1))
        frame.addView(broker, FrameLayout.LayoutParams(-1, -1))
        broker.visibility = View.GONE

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
            webChromeClient = WebChromeClient()
            webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    if (homeUrl == tigerUrl && url?.startsWith(tigerUrl) == true) {
                        val js = assets.open("web-ui-assist.js").bufferedReader().use { it.readText() }
                        view?.evaluateJavascript(js, null)
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
                    status.text = "Certificado HTTPS não validado. Navegação bloqueada."
                }
            }
        }
    }

    private fun showTiger() {
        tiger.visibility = View.VISIBLE
        broker.visibility = View.GONE
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
                broker.visibility = View.VISIBLE
                tiger.visibility = View.GONE
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
                    "CONFIRMADA" -> status.text = "DEMO CONFIRMADA! O SSID desaparece do painel. Teste uma operação manual de 5s antes de iniciar o bot."
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
                document.getElementById('call')?.closest('.card')?.scrollIntoView({behavior:'smooth',block:'start'});
                return 'OK';
            })()
        """.trimIndent()) { raw ->
            status.text = when (jsValue(raw)) {
                "OK" -> "Faça uma operação MANUAL DEMO de 5s e aguarde a confirmação oficial para desbloquear o automático. Se necessário, selecione e analise o ativo antes."
                "LOGIN" -> "Primeiro entre na sua conta do Xtreme Tiger."
                "DEMO" -> "A conta DEMO ainda não foi confirmada no servidor. Conecte novamente."
                else -> "Não foi possível abrir o teste; confira o painel."
            }
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
                    "VALIDAR" -> "Para iniciar, faça primeiro um teste MANUAL de 5 segundos na conta DEMO e aguarde o resultado. O aplicativo mostrou os controles abaixo do gráfico."
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

    @Deprecated("Legacy back navigation")
    override fun onBackPressed() {
        if (broker.visibility == View.VISIBLE) showTiger()
        else if (tiger.canGoBack()) tiger.goBack()
        else super.onBackPressed()
    }

    override fun onDestroy() {
        autoTransferApproved = false
        capturedPacket = null
        tiger.destroy()
        broker.destroy()
        super.onDestroy()
    }
}
