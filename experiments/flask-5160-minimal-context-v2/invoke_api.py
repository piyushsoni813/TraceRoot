import json, urllib.request, sys
prompt = open("prompt.md", encoding="utf-8").read()
body = {"messages":[{"role":"user","content":prompt}],"temperature":0,"top_p":1,"top_k":1,"min_p":0,"max_tokens":1024,"stream":False}
req = urllib.request.Request("http://127.0.0.1:8091/v1/chat/completions", json.dumps(body).encode(), {"Content-Type":"application/json"})
raw = urllib.request.urlopen(req, timeout=600).read()
open("output/response.json","wb").write(raw)
d = json.loads(raw)
open("output/raw.md","w",encoding="utf-8",newline="").write(d["choices"][0]["message"]["content"])
print(d["choices"][0]["finish_reason"], d.get("usage"))
