# Signal Focus Pocket Option — Serviço separado

Este branch é exclusivo do Signal Focus, aplicativo de **monitoramento e alertas**, distinto dos demais bots no Render. O código completo está no pacote `signal-focus-payload.b64`, um arquivo ZIP codificado em base64, que é extraído durante o build. Também há uma versão para baixar na conversa do ChatGPT.

## Segurança e limites

- `PO_SSID` (sessão DEMO Pocket Option) deve ser adicionado **somente** em Render > Environment, nunca ao GitHub, ao navegador ou ao chat.
- `APP_ACCESS_PIN` (PIN forte) também deve ser adicionado em Environment.
- `PO_ALLOW_REAL_ACCOUNT=0` impede conta real.
- Cliente comunitário WebSocket **não oficial**; pode falhar ou ser bloqueado; sem garantias de uptime, precisão ou resultados.
- Aplicativo **somente leitura**. Nenhuma ordem é enviada.
- A tela principal apresenta exclusivamente BUY/SELL confirmado no fechamento de candles reais, ou radar com estado de conexão. Gráfico e ajustes ficam em seção técnica oculta por padrão.

## Build / Start

Build: `python -c "import base64,zipfile,io;zipfile.ZipFile(io.BytesIO(base64.b64decode(open('signal-focus-payload.b64').read()))).extractall('.')" && pip install -r signal-focus/requirements.txt`
Start: `cd signal-focus && python server.py`
