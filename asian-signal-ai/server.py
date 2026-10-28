import os, json, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

def status():
    return {"service":"asian-signal-api","ok":True,"mode":"PRACTICE_ONLY","connected":False,
            "market_data_live":False,"orders_enabled":False,"radar_progress":0,
            "wins":0,"losses":0,"remaining_seconds":None,
            "message":"Aguardando autenticação autorizada e verificação do feed real da Bullex",
            "timestamp":int(time.time())}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path not in ('/','/health','/api/status'):
            self.send_error(404); return
        body=json.dumps(status(),ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin','https://asian-signal-ai.onrender.com')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        self.send_error(403,"Execução de ordens indisponível sem autenticação PRACTICE validada")

if __name__=='__main__':
    ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','10000'))),Handler).serve_forever()
