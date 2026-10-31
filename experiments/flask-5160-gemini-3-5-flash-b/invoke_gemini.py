"""Send prompt.md to the Gemini API and save the unmodified response. Key comes from GEMINI_API_KEY."""
import json, os, urllib.request
MODEL = "gemini-3.5-flash"
prompt = open("prompt.md", encoding="utf-8").read()
body = {
    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
    "generationConfig": {"temperature": 0, "topP": 1, "topK": 1, "maxOutputTokens": 16384},
}
req = urllib.request.Request(
    f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
    json.dumps(body).encode(),
    {"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]},
)
raw = urllib.request.urlopen(req, timeout=600).read()
open("output/response.json", "wb").write(raw)
d = json.loads(raw)
cand = d["candidates"][0]
text = "".join(p.get("text", "") for p in cand["content"]["parts"] if not p.get("thought"))
open("output/raw.md", "w", encoding="utf-8", newline="").write(text)
print(cand.get("finishReason"), d.get("usageMetadata"))
