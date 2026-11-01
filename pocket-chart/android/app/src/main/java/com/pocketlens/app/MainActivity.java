package com.pocketlens.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewFeature;
import androidx.webkit.WebMessageCompat;
import org.json.JSONArray;
import org.json.JSONObject;
import java.nio.charset.StandardCharsets;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.util.Collections;

public final class MainActivity extends Activity {
    private WebView portal, broker;
    private LinearLayout root, bar;
    private TextView info;
    private boolean brokerVisible = false, transferring = false, destroyed = false;
    private long attempt = 0;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE);
        root = new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setBackgroundColor(Color.rgb(11,15,23));
        root.setOnApplyWindowInsetsListener((v,insets)-> {v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());return insets;});
        bar = new LinearLayout(this); bar.setPadding(12,6,12,6); bar.setOrientation(LinearLayout.VERTICAL); bar.setVisibility(View.GONE);
        info = new TextView(this); info.setTextColor(Color.rgb(228,234,243)); info.setPadding(12,8,12,8);
        Button back = new Button(this); back.setText("← Voltar ao analisador"); back.setOnClickListener(v -> showPortal());
        bar.addView(info); bar.addView(back); root.addView(bar);
        portal = createWebView(false); broker = createWebView(true);
        root.addView(portal,new LinearLayout.LayoutParams(-1,0,1)); root.addView(broker,new LinearLayout.LayoutParams(-1,0,1));
        broker.setVisibility(View.GONE); setContentView(root);
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER) || !WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)) {
            new AlertDialog.Builder(this).setTitle("Atualize o Android System WebView")
                .setMessage("Esta versão do WebView não permite iniciar a conexão integrada. Atualize Android System WebView e Chrome pela Play Store e abra novamente.")
                .setPositiveButton("Fechar",(d,w)->finish()).setCancelable(false).show();return;
        }
        WebViewCompat.addWebMessageListener(portal,"PocketLensNative",Collections.singleton(WebPolicy.PORTAL),(view,message,origin,main,reply)-> {
            if (!main || message.getType()!=WebMessageCompat.TYPE_STRING || !WebPolicy.allowed(origin.toString(),false)) return;
            String command=message.getData();
            if ("connect".equals(command)) openBroker();
            else if ("connected".equals(command)) {transferring=false;showPortal();}
            else if ("failed".equals(command)) {transferring=false;info.setText("A conexão de leitura não foi confirmada. Confira a sessão demo ou tente novamente.");}
            else if ("logout".equals(command) || "disconnect".equals(command)) clearBroker();
        });
        WebViewCompat.addWebMessageListener(broker,"PocketLensSession",WebPolicy.BROKER_ORIGINS,(view,message,origin,main,reply)-> {
            if (!main || message.getType()!=WebMessageCompat.TYPE_STRING || !brokerVisible || !WebPolicy.allowed(origin.toString(),true)) return;
            handleBrokerMessage(message.getData());
        });
        try {
            ByteArrayOutputStream bytes=new ByteArrayOutputStream();
            try(InputStream input=getAssets().open("session-bridge.js")) {byte[] buffer=new byte[4096];int n;while((n=input.read(buffer))!=-1)bytes.write(buffer,0,n);}
            String script=new String(bytes.toByteArray(),StandardCharsets.UTF_8);
            WebViewCompat.addDocumentStartJavaScript(broker,script,WebPolicy.BROKER_ORIGINS);
            portal.loadUrl(WebPolicy.PORTAL + "/");
        } catch (Exception ignored) {info.setText("Não foi possível iniciar a conexão integrada.");bar.setVisibility(View.VISIBLE);}
    }

    private WebView createWebView(boolean isBroker) {
        WebView view=new WebView(this); view.setBackgroundColor(Color.rgb(11,15,23));
        WebSettings s=view.getSettings();s.setJavaScriptEnabled(true);s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);s.setAllowContentAccess(false);s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setJavaScriptCanOpenWindowsAutomatically(false);s.setSupportMultipleWindows(false);
        s.setMediaPlaybackRequiresUserGesture(true);s.setSafeBrowsingEnabled(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(view,false);
        view.setWebChromeClient(new WebChromeClient());
        view.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest request){
                if (!request.isForMainFrame()) return false;
                if (WebPolicy.allowed(request.getUrl().toString(),isBroker)) return false;
                if (isBroker) info.setText("Link externo não aberto. Entre por e-mail na página oficial e selecione a conta DEMO.");
                return true;
            }
            @Override public void onPageFinished(WebView v,String url){
                if (isBroker && WebPolicy.allowed(url,true) && brokerVisible && !transferring)
                    info.setText("Pocket Option oficial · entre na sua conta e selecione DEMO. O retorno ocorrerá após confirmar a conexão de leitura.");
            }
        });
        return view;
    }

    private void openBroker(){
        attempt++;transferring=false;brokerVisible=true;portal.setVisibility(View.GONE);broker.setVisibility(View.VISIBLE);bar.setVisibility(View.VISIBLE);
        info.setText("Entrando na Pocket Option oficial. Selecione a conta demonstrativa.");
        broker.loadUrl("https://m.pocketoption.com/pt/login/");
    }

    private void handleBrokerMessage(String raw){
        if (raw==null || raw.length()>22000) return;
        try {
            JSONObject envelope=new JSONObject(raw);
            if ("real".equals(envelope.optString("type"))) {
                attempt++;transferring=false;info.setText("Conta real detectada. Selecione a conta DEMO para analisar.");
                portal.evaluateJavascript("window.pocketNativeDisconnect && window.pocketNativeDisconnect()",null);return;
            }
            if (!"demo".equals(envelope.optString("type")) || transferring) return;
            String packet=envelope.getString("packet");
            JSONArray event=new JSONArray(packet.startsWith("42")?packet.substring(2):packet);
            JSONObject auth=event.getJSONObject(1);
            if (!"auth".equals(event.getString(0)) || !(auth.get("isDemo") instanceof Number) || auth.getInt("isDemo")!=1
                || auth.getLong("uid")<=0 || auth.getString("session").length()<10 || auth.getString("session").length()>16000) return;
            if (!WebPolicy.allowed(portal.getUrl(),false)) return;
            transferring=true;final long ticket=++attempt;
            info.setText("Sessão DEMO detectada. Validando a conexão do analisador…");
            // JSONObject.quote keeps the packet data from becoming JavaScript code. Never log or store the session.
            portal.evaluateJavascript("window.pocketNativeSession && window.pocketNativeSession("+JSONObject.quote(packet)+")",null);
            root.postDelayed(()->{if(!destroyed && ticket==attempt && transferring){transferring=false;info.setText("A leitura ainda não foi confirmada. Volte ao analisador para conferir a mensagem ou reconecte.");}},35000);
        } catch (Exception ignored) { /* Never print broker packets or credentials. */ }
    }

    private void showPortal(){
        brokerVisible=false;broker.setVisibility(View.GONE);bar.setVisibility(View.GONE);portal.setVisibility(View.VISIBLE);
        // The broker view stays in memory. Authentication is never persisted by the native bridge.
    }
    private void clearBroker(){attempt++;transferring=false;broker.stopLoading();broker.loadUrl("about:blank");showPortal();}
    @Override public void onBackPressed(){if(brokerVisible){showPortal();}else{super.onBackPressed();}}
    @Override protected void onDestroy(){destroyed=true;attempt++;if(portal!=null){portal.stopLoading();portal.destroy();}if(broker!=null){broker.stopLoading();broker.destroy();}super.onDestroy();}
}
