"""Private Supabase Edge gateway for Pulse Lab. Only the Render server has the key.

No service_role credentials are stored in this app or exposed to browser clients.
"""
import json,os,urllib.request,urllib.error,logging

LOG=logging.getLogger("pulse.store")

class PulseStore:
    def __init__(self):
        self.url=os.environ.get("PULSE_LAB_STORE_URL","").strip()
        self.token=os.environ.get("PULSE_LAB_STORE_TOKEN","").strip()
        self.configured=self.url.startswith("https://") and len(self.token)>=48
    def call(self,op,**params):
        if not self.configured:
            raise RuntimeError("Persistência não configurada.")
        data=json.dumps({"op":op,**params},separators=(",",":"),ensure_ascii=False).encode("utf-8")
        request=urllib.request.Request(self.url,data=data,headers={
            "Content-Type":"application/json","X-Pulse-Lab-Key":self.token,
            "User-Agent":"PulseSignalLab/3"},method="POST")
        with urllib.request.urlopen(request,timeout=13) as response:
            obj=json.load(response)
        if not isinstance(obj,dict) or obj.get("error"):
            raise RuntimeError("Resposta de persistência inválida")
        return obj
    def health(self):
        return self.call("health").get("ok") is True
    def load(self,max_records=4000):
        events=[];models=[];offset=0
        while offset<max_records:
            result=self.call("load",offset=offset)
            if not isinstance(result.get("records"),list):
                raise RuntimeError("Resposta de leitura inválida")
            events+=result["records"]
            if offset==0:models=result.get("models",[])
            offset=result.get("next_offset")
            if offset is None:break
            if not isinstance(offset,int) or offset<=0:break
        return events[:max_records],models
    def save(self,events,models):
        if not events and not models:return
        if len(events)>180 or len(models)>20:
            raise ValueError("Lote de persistência acima do limite")
        result=self.call("save",records=events,models=models)
        if result.get("ok") is not True:raise RuntimeError("Falha na confirmação da persistência")
        return result
