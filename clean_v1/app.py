import json,os
from wsgiref.simple_server import make_server
from urllib.parse import urlparse
HTML='''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Xtreme Bot Pro</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#071021;color:#eaf3ff;font:16px system-ui,sans-serif}main{max-width:740px;margin:auto;padding:20px 14px}header{padding:20px 0 26px;display:flex;justify-content:space-between;align-items:center}h1{font-size:25px;letter-spacing:-1px;margin:0}h1 b{color:#72a9ff}p{color:#9bafc9;line-height:1.6}.pill{font-size:12px;color:#28dfab;background:#103f37;border-radius:30px;padding:9px 12px;font-weight:800}.card{background:#111e33;border:1px solid #2a3e5c;border-radius:18px;padding:20px;margin-bottom:16px}h2{font-size:17px;margin:0 0 16px}.state{padding:16px;background:#172b43;border-radius:13px;font-weight:700}.muted{font-size:13px;color:#97abc5}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.metric{background:#1a2b45;border-radius:12px;padding:16px}.metric strong{font-size:25px;display:block;margin-top:10px}.btn{border:0;border-radius:12px;padding:15px;color:#08231c;background:#19d99e;font-size:16px;font-weight:800;width:100%;margin-top:10px}.btn:disabled{background:#31445c;color:#8ea1b9}.outline{background:#1c3557;color:#c8dcfa}label{font-size:13px;color:#a4b5cf}input{background:#1b2c45;color:white;border:1px solid #425775;border-radius:10px;padding:13px;width:100%;font-size:16px;margin:6px 0 14px}@media(max-width:420px){main{padding:12px}header{padding:13px 0 22px}.card{padding:16px}}
</style></head><body><main><header><div><h1>ϟ Xtreme <b>Bot Pro</b></h1><p style="margin:3px 0">Painel de execução · versão limpa</p></div><span class="pill">DEMO</span></header><section class="card"><h2>Conexão Bullex</h2><div class="state" id="state">● Desconectado</div><p class="muted">Sem conexão com a corretora nesta versão. Nenhuma operação será enviada.</p><button class="btn outline" disabled>Conectar conta PRACTICE · integração pendente</button></section><section class="card"><h2>Execução</h2><div class="grid"><div><label>Entrada (US$)</label><input value="2" type="number" min="1" readonly></div><div><label>Payout mínimo (%)</label><input value="80" type="number" readonly></div><div><label>Stop loss (US$)</label><input value="10" readonly></div><div><label>Stop win (US$)</label><input value="20" readonly></div></div><button class="btn" disabled>Iniciar robô · não conectado</button><button class="btn outline" disabled>Parar robô</button><p class="muted">Nenhuma estratégia instalada e nenhuma ordem automática habilitada.</p></section><section class="card"><h2>Placar</h2><div class="grid"><div class="metric">WIN<strong>0</strong></div><div class="metric">LOSS<strong>0</strong></div><div class="metric">Operações<strong>0</strong></div><div class="metric">Resultado<strong>0,00</strong></div></div></section></main></body></html>'''
def app(environ,start_response):
    path=urlparse(environ.get('PATH_INFO','/')).path
    if path=='/health':
        data=json.dumps({'ok':True,'broker_connected':False,'orders_enabled':False}).encode()
        start_response('200 OK',[('Content-Type','application/json'),('Content-Length',str(len(data)))])
    elif path=='/':
        data=HTML.encode()
        start_response('200 OK',[('Content-Type','text/html; charset=utf-8'),('Content-Length',str(len(data))),('Cache-Control','no-store')])
    else:
        data=b'Not found'
        start_response('404 Not Found',[('Content-Type','text/plain'),('Content-Length',str(len(data)))])
    return [data]
if __name__=='__main__':
    make_server('0.0.0.0',int(os.environ.get('PORT','10000')),app).serve_forever()
