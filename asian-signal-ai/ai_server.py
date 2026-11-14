"""API experimental de sinais, somente leitura, para Xtreme Sniper IA.

Iniciar: python asian-signal-ai/ai_server.py
Configurar BULLEX_EMAIL, BULLEX_PASSWORD e XTREME_ACCESS_TOKEN no servidor.
A Bullex usa biblioteca de terceiros e a conexão real NÃO foi validada aqui.
Nenhuma rota envia ordens, mesmo que o worker tenha tal capacidade.
"""
import hmac
import json
import os
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import server as base
from ai_engine import analisar

ACCESS = os.getenv("XTREME_ACCESS_TOKEN", "")
ORIGIN = os.getenv("XTREME_WEB_ORIGIN", "https://asian-signal-ai.onrender.com")
bridge_lock = threading.RLock()
market_cache = {"at": 0, "assets": []}
scan_cache = {}
scan_lock = threading.Lock()


def markets():
    with bridge_lock:
        now = time.time()
        if now - market_cache["at"] < 20 and market_cache["assets"]:
            return market_cache["assets"]
        data = base.call("market", timeout=20, payout=0, strategy="sniper")
        assets = [v for v in data.get("assets", []) if v.get("open") is True and
                  isinstance(v.get("asset"), str)]
        market_cache.update(at=time.time(), assets=assets)
        return assets


def scan(asset, seconds):
    if seconds not in (60, 300):
        raise ValueError("Expiração disponível: M1 ou M5")
    if len(asset) > 45 or not asset:
        raise ValueError("Ativo inválido")
    pair = next((v for v in markets() if v.get("asset") == asset), None)
    if pair is None:
        raise ValueError("Ativo não está disponível no catálogo atual")
    with scan_lock:
        cached = scan_cache.get((asset, seconds))
        if cached and time.time() - cached["at"] < 3:
            return cached["result"]
        with bridge_lock:
            data = base.call("candles", timeout=24, asset=asset)
        raw = data.get("candles", [])
        now = data.get("now", 0)
        if not isinstance(raw, list) or not isinstance(now, (int, float)):
            raise ValueError("Feed não forneceu candles ou relógio válidos")
        if abs(time.time() - now) > 10:
            raise ValueError("Relógio da corretora desatualizado")
        result = analisar(raw, now, periodo=seconds, payout=pair.get("payout"))
        result.update(asset=asset, broker_time=now,
                      source="Bullex PRACTICE (conector não oficial)",
                      connected=True, account_mode="PRACTICE")
        scan_cache[(asset, seconds)] = {"at": time.time(), "result": result}
        return result


class Handler(base.Handler):
    def _cors(self):
        origin = self.headers.get("Origin")
        if origin and origin == ORIGIN:
            self.send_header("Access-Control-Allow-Origin", ORIGIN)
            self.send_header("Vary", "Origin")

    def _json(self, status, payload):
        content = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self._cors()
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "X-Xtreme-Token")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/health", "/api/status"):
            return super().do_GET()
        if path not in ("/api/markets", "/api/scan"):
            return self._json(404, {"error": "Rota não encontrada"})
        if len(ACCESS) < 16:
            return self._json(503, {"error": "Acesso desabilitado: configure XTREME_ACCESS_TOKEN (16+ caracteres)"})
        token = self.headers.get("X-Xtreme-Token", "")
        if not hmac.compare_digest(token, ACCESS):
            return self._json(401, {"error": "Chave de acesso inválida"})
        current = base.snapshot()
        if not (current.get("connected") and current.get("market_data_live")):
            return self._json(503, {"error": "Feed PRACTICE não validado", "detail": current.get("message")})
        try:
            if path == "/api/markets":
                return self._json(200, {"assets": markets(), "orders_enabled": False})
            query = parse_qs(urlparse(self.path).query)
            asset = query.get("asset", [""])[0]
            seconds = int(query.get("seconds", ["60"])[0])
            return self._json(200, scan(asset, seconds))
        except (RuntimeError, ValueError, TypeError) as exc:
            return self._json(422, {"error": str(exc)[:200]})
        except Exception:
            return self._json(503, {"error": "Falha na leitura do feed; nenhuma operação foi enviada"})

    def do_POST(self):
        self._json(403, {"error": "Somente leitura: envio de ordens desabilitado"})


if __name__ == "__main__":
    threading.Thread(target=base.connect_loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", int(os.getenv("PORT", "10000"))), Handler).serve_forever()
