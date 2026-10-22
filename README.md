# Xtreme Analista

Independent read-only Bullex research app. No order dispatch. Start with gunicorn app:app --workers 1 --threads 8 --timeout 180 --bind 0.0.0.0:$PORT. Build: pip install -r requirements.txt && python bootstrap.py && python -m unittest test_analyst -v.

Configure SESSION_SECRET, ANALYST_GATEWAY, ANALYST_GATEWAY_KEY in Render. Never commit credentials. Broker login is required to load each account's research; passwords stay in broker worker memory. Results compare closed candle prices and are theoretical, not broker trades. Five fixed rule families, four horizons, up to 5000 retained observations. Free Render services may sleep; reconnect after restart. No guaranteed overnight run or automatically invented strategies.
