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
    private var probeSupported = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WebView.setWebContentsDebuggingEnabled(false)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(10, 15, 19))
        }
        val header = TextView(this).apply {
            text = "XTREME TIGER  •  POCKET DEMO  •  EXPERIMENTAL"
            textSize = 14f
            setTextColor(Color.rgb(193, 238, 116))
            setPadding(18, 20, 18, 10)
        }
        status = TextView(this).apply {
            text = "Teste Android. Nenhuma sessão da corretora conectada."
            textSize = 12f
            setTextColor(Color.WHITE)
            setPadding(18, 8, 18, 14)
        }
        val controls = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(10, 0, 10, 8)
        }
        val openTiger = Button(this).apply {
            text = "1. Abrir Xtreme Tiger / Fazer login"
            setOnClickListener { showTiger() }
        }
        val openBroker = Button(this).apply {
            text = "2. Testar login Pocket Option DEMO"
            setOnClickListener { confirmBeforeOpeningBroker() }
        }
        transferButton = Button(this).apply {
            text = "3. Enviar sessão DEMO ao Xtreme"
            isEnabled = false
            setOnClickListener { confirmTransfer() }
        }
        val discard = Button(this).apply {
            text = "Descartar sessão / Limpar navegador interno"
            setOnClickListener { clearExperimentalSession() }
        }
        controls.addView(openTiger)
        controls.addView(openBroker)
        controls.addView(transferButton)
        controls.addView(discard)
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
                    status.text = "Mensagem DEMO identificada no navegador interno. Ainda NÃO está conectada. Faça login no Xtreme e confirme o envio."
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
            .setTitle("Teste assistido — somente DEMO")
            .setMessage("A corretora abrirá em um navegador interno SEPARADO do Chrome. Você poderá precisar entrar novamente na Pocket Option e selecionar DEMO. O protótipo tentará detectar apenas a mensagem de sessão DEMO. Não lemos nem salvamos sua senha. O método não é oficial e pode falhar ou ser bloqueado pela corretora. Continuar?")
            .setNegativeButton("Cancelar", null)
            .setPositiveButton("Continuar") { _, _ ->
                capturedPacket = null
                transferButton.isEnabled = false
                broker.visibility = View.VISIBLE
                tiger.visibility = View.GONE
                broker.loadUrl(brokerUrl)
                status.text = "Abra a conta DEMO na Pocket Option. Aguardando sessão; nenhuma conexão foi estabelecida."
            }.show()
    }

    private fun confirmTransfer() {
        val packet = capturedPacket ?: return
        if (DemoAuthPacket.validate(packet) == null) {
            capturedPacket = null
            transferButton.isEnabled = false
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
            // Result is NOT broker authentication confirmation.
            status.text = when (result) {
                "\"ENVIO_SOLICITADO\"" -> "Envio solicitado. Confira no Xtreme se a CONTA DEMO foi confirmada pelo servidor."
                "\"LOGIN_NECESSARIO\"" -> "Entre primeiro no Xtreme Tiger e repita o teste. Sessão descartada."
                else -> "Não foi possível acessar o formulário. Sessão descartada."
            }
            capturedPacket = null
            transferButton.isEnabled = false
            broker.loadUrl("about:blank")
        }
    }

    private fun clearExperimentalSession() {
        capturedPacket = null
        transferButton.isEnabled = false
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
        capturedPacket = null
        tiger.destroy()
        broker.destroy()
        super.onDestroy()
    }
}
