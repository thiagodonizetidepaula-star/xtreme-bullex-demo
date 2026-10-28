"""Conector de observação da Bullex (experimental). Sem envio de ordens.

Requer bullexapi de terceiros, credenciais no servidor e conformidade com regras locais.
Nunca use senha no frontend nem publique cookies.
"""
import os
import time

class FeedUnavailable(RuntimeError):
    pass

class BullexReadOnlyFeed:
    def __init__(self, client=None):
        self.client = client

    def connect_practice(self):
        if self.client is None:
            if not os.getenv("BULLEX_EMAIL") or not os.getenv("BULLEX_PASSWORD"):
                raise FeedUnavailable("Credenciais de servidor não configuradas")
            try:
                from bullexapi.stable_api import Bullex
            except ImportError as exc:
                raise FeedUnavailable("Biblioteca externa não instalada") from exc
            self.client = Bullex(os.environ["BULLEX_EMAIL"], os.environ["BULLEX_PASSWORD"])
        ok, reason = self.client.connect()
        if not ok:
            raise FeedUnavailable("Falha ao autenticar: " + str(reason))
        self.client.change_balance("PRACTICE")
        if self.client.get_balance_mode() != "PRACTICE":
            raise FeedUnavailable("Proteção: conta prática não confirmada")
        return True

    def market_snapshot(self, active: str, interval: int = 60):
        if interval not in (60, 300):
            raise ValueError("Use M1 ou M5")
        if not self.client or not self.client.check_connect():
            raise FeedUnavailable("Feed desconectado")
        if self.client.get_balance_mode() != "PRACTICE":
            raise FeedUnavailable("A conta não está em PRACTICE")
        now = int(time.time())
        try:
            candles = self.client.get_candles(active, interval, 120, now)
            payout = self.client.get_digital_payout(active)
        except Exception as exc:
            raise FeedUnavailable("Falha de leitura do mercado") from exc
        if not isinstance(candles, (list, tuple)) or len(candles) < 40:
            raise FeedUnavailable("Candles insuficientes")
        if payout is None:
            raise FeedUnavailable("Payout indisponível")
        return {"asset": active, "period_seconds": interval, "received_at": now,
                "candles": candles, "payout": payout, "source": "Bullex (biblioteca não oficial)",
                "account_mode": "PRACTICE", "orders_enabled": False}
