#!/usr/bin/env python3
"""AUSTR.AI Desktop App — vollwertige Privacy-App mit Website-Design."""

import multiprocessing
import subprocess
import sys
import threading
from pathlib import Path

# CRITICAL: Required for PyInstaller to prevent infinite process spawning
if __name__ == "__main__":
    multiprocessing.freeze_support()

import webview
from webview.menu import Menu, MenuAction, MenuSeparator
from austrai_proxy.core import get_engine

# Pre-init engine (blocks ~15s for GLiNER + SpaCy, then instant)
print("AUSTR.AI Engine wird geladen...", flush=True)
_engine = get_engine(memory_enabled=False)
_engine.anonymize("warmup")
print("Engine bereit!", flush=True)


class API:
    def __init__(self):
        self.mappings = {}
        self.window = None

    def protect(self, text):
        r = _engine.anonymize(text)
        self.mappings = r.mappings
        _clip(r.anonymized_text)
        return {"text": r.anonymized_text, "mappings": r.mappings, "count": len(r.mappings)}

    def protect_file(self, path):
        try:
            from austrai_proxy.core.extractor import extract_from_file
            ex = extract_from_file(path)
            r = _engine.anonymize(ex.text)
            self.mappings = r.mappings
            _clip(r.anonymized_text)
            return {"text": r.anonymized_text, "mappings": r.mappings, "count": len(r.mappings),
                    "file": ex.format, "pages": ex.pages, "chars": len(ex.text)}
        except Exception as e:
            return {"error": str(e)}

    def restore(self, text):
        restored = _engine.rehydrate(text, self.mappings)
        cnt = sum(1 for k in self.mappings if k in text)
        _clip(restored)
        return {"text": restored, "count": cnt}

    def open_file(self):
        if not self.window: return None
        r = self.window.create_file_dialog(webview.OPEN_DIALOG, file_types=(
            "Alle Dateien (*.pdf;*.docx;*.xlsx;*.txt;*.csv;*.png;*.jpg)",))
        return r[0] if r else None

    def proxy_toggle(self):
        from austrai_proxy.config import CONFIG_DIR
        pid_file = CONFIG_DIR / "proxy.pid"
        import os, signal
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 0)
                os.kill(pid, signal.SIGTERM)
                pid_file.unlink(missing_ok=True)
                return {"running": False}
            except ProcessLookupError:
                pid_file.unlink(missing_ok=True)
        subprocess.Popen([sys.executable, "-m", "austrai_proxy", "start", "-b"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import time; time.sleep(2)
        return {"running": self._proxy_running()}

    def proxy_status(self):
        return {"running": self._proxy_running()}

    def paste_clipboard(self):
        try:
            r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
            return r.stdout
        except: return ""

    def _proxy_running(self):
        from austrai_proxy.config import CONFIG_DIR
        pid_file = CONFIG_DIR / "proxy.pid"
        if not pid_file.exists(): return False
        try:
            import os
            os.kill(int(pid_file.read_text().strip()), 0)
            return True
        except: return False


def _clip(text):
    try: subprocess.run(["pbcopy"], input=text.encode(), check=True, timeout=5)
    except: pass


HTML = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {
  --bg:#0f172a; --bg2:#0b1120; --card:#1e293b; --card-hover:#263347;
  --accent:#06b6d4; --accent-lt:#22d3ee; --accent-dk:#0891b2;
  --purple:#8b5cf6; --green:#10b981; --red:#ef4444; --amber:#f59e0b;
  --text:#f1f5f9; --muted:#94a3b8; --dim:#64748b;
  --border:#334155; --border-lt:#475569;
  --sans:'Inter',-apple-system,sans-serif; --mono:'JetBrains Mono',monospace;
  --r:12px; --rs:8px;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:var(--sans);background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased;user-select:none}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(6,182,212,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(6,182,212,.03) 1px,transparent 1px);background-size:40px 40px;pointer-events:none}
body::after{content:'';position:fixed;top:-30%;left:-10%;width:60%;height:60%;background:radial-gradient(ellipse,rgba(6,182,212,.06),transparent 70%);pointer-events:none}

.app{position:relative;z-index:1;max-width:680px;margin:0 auto;padding:20px 28px;min-height:100vh;display:flex;flex-direction:column}

/* Nav */
.nav{display:flex;align-items:center;justify-content:space-between;padding-bottom:14px;border-bottom:1px solid var(--border);margin-bottom:20px}
.brand{display:flex;align-items:center;gap:10px}
.logo{width:34px;height:34px;background:linear-gradient(135deg,var(--accent),var(--purple));border-radius:var(--rs);display:flex;align-items:center;justify-content:center;font-size:17px;box-shadow:0 0 16px rgba(6,182,212,.15)}
.brand-name{font-size:16px;font-weight:700;letter-spacing:.5px}
.brand-sub{font-size:11px;color:var(--dim)}
.proxy{display:flex;align-items:center;gap:7px;padding:5px 12px;border-radius:20px;background:var(--card);border:1px solid var(--border);cursor:pointer;font-size:11px;color:var(--muted);transition:.2s}
.proxy:hover{border-color:var(--border-lt)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--red);transition:.3s}
.dot.on{background:var(--green);box-shadow:0 0 6px rgba(16,185,129,.5)}

/* Tabs */
.tabs{display:flex;gap:0;border-bottom:1px solid var(--border);margin-bottom:18px}
.tab{flex:1;padding:9px 0;border:none;background:none;color:var(--dim);font-family:var(--sans);font-size:12px;font-weight:500;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;transition:.2s}
.tab:hover{color:var(--muted)}
.tab.on{color:var(--accent);border-bottom-color:var(--accent);font-weight:600}

/* Panels */
.panel{display:none;animation:fadeIn .25s ease}
.panel.on{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}

/* Section styling */
.sec-label{font-family:var(--mono);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:1.5px;color:var(--accent);margin-bottom:6px}
.sec-title{font-size:18px;font-weight:700;margin-bottom:5px}
.sec-desc{font-size:13px;color:var(--muted);line-height:1.5;margin-bottom:16px}

/* Input tabs (Text / Datei) */
.itabs{display:flex;gap:0;margin-bottom:12px;border-bottom:1px solid var(--border)}
.itab{padding:7px 14px;border:none;background:none;font-family:var(--sans);font-size:13px;font-weight:500;color:var(--dim);cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;transition:.2s}
.itab:hover{color:var(--muted)}
.itab.on{color:var(--accent);border-bottom-color:var(--accent)}
.imode{display:none}.imode.on{display:block}

/* Examples */
.examples{display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap}
.ex-label{font-size:11px;color:var(--dim);padding-top:3px}
.ex-btn{padding:4px 10px;border-radius:6px;font-size:11px;font-family:var(--sans);background:var(--card);border:1px solid var(--border);color:var(--muted);cursor:pointer;transition:.2s}
.ex-btn:hover{border-color:var(--accent);color:var(--accent)}

/* Textarea */
textarea{width:100%;height:150px;background:var(--bg2);border:1px solid var(--border);border-radius:var(--rs);color:var(--text);font-family:var(--mono);font-size:13px;line-height:1.6;padding:12px 14px;resize:vertical;outline:none;transition:.2s;user-select:text}
textarea::placeholder{color:var(--dim);font-family:var(--sans)}
textarea:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(6,182,212,.08)}

/* Dropzone */
.dropzone{border:2px dashed var(--border);border-radius:var(--r);padding:36px 20px;text-align:center;cursor:pointer;transition:.2s;background:var(--bg2)}
.dropzone:hover{border-color:var(--accent);background:rgba(6,182,212,.04)}
.dz-icon{font-size:32px;margin-bottom:6px}
.dz-text{font-size:14px;font-weight:600}
.dz-sub{font-size:12px;color:var(--muted);margin-top:3px}
.dz-link{color:var(--accent);cursor:pointer;text-decoration:underline}
.dz-fmt{font-size:10px;color:var(--dim);margin-top:6px}
.file-card{display:flex;align-items:center;gap:12px;padding:12px;background:var(--card);border:1px solid var(--border);border-radius:var(--rs)}
.file-card .name{font-size:13px;font-weight:600;flex:1}
.file-card .meta{font-size:11px;color:var(--dim)}
.file-card .rm{background:none;border:none;color:var(--dim);font-size:16px;cursor:pointer;padding:2px 6px}
.file-card .rm:hover{color:var(--red)}

/* Buttons */
.btn{display:block;width:100%;padding:12px;border:none;border-radius:var(--rs);font-family:var(--sans);font-size:14px;font-weight:600;cursor:pointer;margin-top:12px;transition:.2s;text-align:center}
.btn:hover{transform:translateY(-1px)}
.btn:active{transform:translateY(0)}
.btn:disabled{opacity:.4;cursor:default;transform:none}
.btn-a{background:linear-gradient(135deg,var(--accent-dk),var(--accent));color:white;box-shadow:0 0 20px rgba(6,182,212,.1)}
.btn-a:hover{box-shadow:0 0 28px rgba(6,182,212,.18)}
.btn-g{background:linear-gradient(135deg,#059669,var(--green));color:white}
.btn-o{background:transparent;color:var(--muted);border:1px solid var(--border);margin-top:8px}
.btn-o:hover{border-color:var(--border-lt);color:var(--text)}
.btn-row{display:flex;gap:8px;margin-top:12px}
.btn-row .btn{flex:1;margin-top:0}

/* Result */
.result{margin-top:14px;padding:14px;background:var(--bg2);border:1px solid var(--border);border-radius:var(--rs);font-family:var(--mono);font-size:13px;line-height:1.6;white-space:pre-wrap;word-break:break-word;max-height:220px;overflow-y:auto;user-select:text}
.map-card{margin-top:10px;padding:12px;background:var(--card);border:1px solid var(--border);border-radius:var(--rs)}
.map-head{font-size:12px;font-weight:600;margin-bottom:8px;display:flex;align-items:center;gap:6px}
.map-head .ico{color:var(--green)}
.m-row{display:flex;align-items:center;gap:8px;padding:4px 6px;font-size:12px;font-family:var(--mono);border-radius:4px;transition:.15s}
.m-row:hover{background:rgba(239,68,68,.08)}
.m-old{color:var(--red);text-decoration:line-through;opacity:.7}
.m-arr{color:var(--dim)}
.m-new{color:var(--green)}

/* Toast */
.toast{padding:8px 14px;border-radius:var(--rs);font-size:12px;font-weight:500;margin-bottom:14px;display:none}
.toast.show{display:block;animation:fadeIn .2s}
.toast.info{background:rgba(6,182,212,.08);color:var(--accent-lt);border:1px solid rgba(6,182,212,.12)}
.toast.ok{background:rgba(16,185,129,.08);color:var(--green);border:1px solid rgba(16,185,129,.12)}
.toast.err{background:rgba(239,68,68,.08);color:var(--red);border:1px solid rgba(239,68,68,.12)}

/* Options */
.opt-toggle{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--dim);cursor:pointer;margin:10px 0 0;padding:4px 0;transition:.2s}
.opt-toggle:hover{color:var(--muted)}
.opt-toggle .arr{font-size:9px;transition:.2s}
.opt-toggle.open .arr{transform:rotate(90deg)}
.opt-panel{display:none;margin-top:10px}
.opt-panel.open{display:block;animation:fadeIn .2s}
.opt-label{font-size:11px;font-weight:600;color:var(--muted);margin-bottom:3px}
.opt-hint{font-weight:400;color:var(--dim)}
.opt-input{width:100%;padding:8px 10px;background:var(--bg2);border:1px solid var(--border);border-radius:var(--rs);color:var(--text);font-family:var(--mono);font-size:12px;outline:none;resize:vertical}
.opt-input:focus{border-color:var(--accent)}

.footer{margin-top:auto;padding:14px 0 4px;border-top:1px solid var(--border);text-align:center;font-size:10px;color:var(--dim)}

::-webkit-scrollbar{width:5px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:var(--dim);border-radius:3px}
</style></head><body>
<div class="app">
  <div class="nav">
    <div class="brand"><div class="logo">🛡</div><div><div class="brand-name">AUSTR.AI</div><div class="brand-sub">Privacy Firewall</div></div></div>
    <div class="proxy" onclick="proxyToggle()"><div class="dot" id="dot"></div><span id="pLabel">…</span></div>
  </div>

  <div id="toast" class="toast"></div>

  <div class="tabs">
    <button class="tab on" onclick="go('input')">1 Eingabe</button>
    <button class="tab" onclick="go('result')">2 Geschützt</button>
    <button class="tab" onclick="go('deanon')">3 Deanonymisieren</button>
    <button class="tab" onclick="go('done')">4 Fertig</button>
  </div>

  <!-- 1: INPUT -->
  <div class="panel on" id="p-input">
    <div class="sec-label">Schritt 1</div>
    <div class="sec-title">Daten eingeben</div>
    <div class="sec-desc">Text eingeben oder Datei hochladen. Sensible Daten werden automatisch erkannt — alles lokal.</div>
    <div class="itabs">
      <button class="itab on" onclick="setMode('text')">Text</button>
      <button class="itab" onclick="setMode('file')">Datei</button>
    </div>
    <div class="imode on" id="m-text">
      <div class="examples">
        <span class="ex-label">Beispiele:</span>
        <button class="ex-btn" onclick="loadEx(0)">Geschäfts-E-Mail</button>
        <button class="ex-btn" onclick="loadEx(1)">Arzt-Befund</button>
        <button class="ex-btn" onclick="loadEx(2)">Passwort &amp; API Key</button>
      </div>
      <textarea id="input" placeholder="Text mit sensiblen Daten eingeben..."></textarea>
    </div>
    <div class="imode" id="m-file">
      <div class="dropzone" id="dz" onclick="openFile()">
        <div class="dz-icon">📄</div>
        <div class="dz-text">Datei hierher ziehen</div>
        <div class="dz-sub">oder <span class="dz-link">Datei wählen</span></div>
        <div class="dz-fmt">PDF, DOCX, XLSX, TXT, CSV, PNG, JPG</div>
      </div>
      <div class="file-card" id="fcard" style="display:none">
        <span style="font-size:22px">📄</span>
        <div style="flex:1"><div class="name" id="fname"></div><div class="meta" id="fmeta"></div></div>
        <button class="rm" onclick="clearFile()">✕</button>
      </div>
    </div>
    <div class="opt-toggle" onclick="this.classList.toggle('open');document.getElementById('opts').classList.toggle('open')">
      <span class="arr">▶</span> Optionale Einstellungen
    </div>
    <div class="opt-panel" id="opts">
      <div class="opt-label">Zusätzliche Begriffe <span class="opt-hint">(einer pro Zeile)</span></div>
      <textarea class="opt-input" id="deny" rows="2" placeholder="z.B.&#10;Firmenname&#10;Projektname"></textarea>
    </div>
    <button class="btn btn-a" id="btnA" onclick="anonymize()">🔒 Anonymisieren</button>
  </div>

  <!-- 2: RESULT -->
  <div class="panel" id="p-result">
    <div class="sec-label">Schritt 2</div>
    <div class="sec-title">Geschützter Text</div>
    <div class="sec-desc">Kopiere den Text und füge ihn in ChatGPT, Claude oder ein anderes KI-Tool ein.</div>
    <div class="result" id="anonText"></div>
    <div class="map-card" id="mapCard">
      <div class="map-head"><span class="ico">🔒</span><span id="mapCount"></span></div>
      <div id="mapList"></div>
    </div>
    <button class="btn btn-a" onclick="copyAnon()">📋 Text kopieren</button>
    <button class="btn btn-g" onclick="go('deanon')" style="margin-top:8px">→ KI-Antwort deanonymisieren</button>
  </div>

  <!-- 3: DEANON -->
  <div class="panel" id="p-deanon">
    <div class="sec-label">Schritt 3</div>
    <div class="sec-title">KI-Antwort deanonymisieren</div>
    <div class="sec-desc">Füge die KI-Antwort ein. Codenames werden durch deine echten Daten ersetzt.</div>
    <textarea id="aiResp" placeholder="KI-Antwort hier einfügen..."></textarea>
    <button class="btn btn-o" onclick="pasteAI()" style="margin-top:8px">📋 Aus Zwischenablage einfügen</button>
    <button class="btn btn-g" onclick="deanonymize()">🔓 Deanonymisieren</button>
  </div>

  <!-- 4: DONE -->
  <div class="panel" id="p-done">
    <div class="sec-label">Fertig</div>
    <div class="sec-title">Wiederhergestellte Antwort</div>
    <div class="sec-desc">Die KI-Antwort mit deinen echten Daten.</div>
    <div class="result" id="resText"></div>
    <div class="btn-row">
      <button class="btn btn-a" onclick="copyRes()">📋 Kopieren</button>
      <button class="btn btn-o" onclick="reset()">↻ Neuer Text</button>
    </div>
  </div>

  <div class="footer">AUSTR.AI v1.0 — Alles läuft lokal auf deinem Rechner</div>
</div>

<script>
const EX=[
  "Sehr geehrter Herr Thomas Gruber,\n\nich sende Ihnen die Rechnung der Innovatech Solutions GmbH (UID: ATU12345678).\nBitte überweisen Sie EUR 15.000 auf IBAN AT48 3200 0000 1234 5678.\n\nBei Fragen: +43 1 234 5678\n\nMit freundlichen Grüßen,\nMaria Steinbauer",
  "Patient: Sabine Müller, geb. 15.03.1985\nDiagnose: Diabetes mellitus Typ 2\nMedikament: Metformin 500mg\nBefund: HbA1c erhöht auf 8,2%.\nTherapieanpassung empfohlen.",
  "Mein Passwort ist SuperSecret123! und der API Key ist sk-ant-api03-abcdefghijklmnopqrstuvwxyz.\nServer-IP: 192.168.1.100\nDatenbank: postgres://admin:geheim@db.intern:5432/prod"
];
let mode='text', filePath=null, lastResult=null;

function loadEx(n){document.getElementById('input').value=EX[n];setMode('text')}
function go(p){
  document.querySelectorAll('.panel').forEach(e=>e.classList.remove('on'));
  document.getElementById('p-'+p).classList.add('on');
  const order=['input','result','deanon','done'];
  document.querySelectorAll('.tab').forEach((t,i)=>t.classList.toggle('on',order[i]===p));
}
function setMode(m){
  mode=m;
  document.querySelectorAll('.itab').forEach((t,i)=>t.classList.toggle('on',['text','file'][i]===m));
  document.querySelectorAll('.imode').forEach(e=>e.classList.remove('on'));
  document.getElementById('m-'+m).classList.add('on');
}
function toast(msg,type){const t=document.getElementById('toast');t.textContent=msg;t.className='toast show '+(type||'info');if(type==='ok')setTimeout(()=>t.className='toast',4000)}
function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}

async function openFile(){
  const p=await window.pywebview.api.open_file();
  if(p){filePath=p;document.getElementById('fname').textContent=p.split('/').pop();document.getElementById('fmeta').textContent='Bereit';document.getElementById('fcard').style.display='flex';document.getElementById('dz').style.display='none'}
}
function clearFile(){filePath=null;document.getElementById('fcard').style.display='none';document.getElementById('dz').style.display='block'}

async function anonymize(){
  const btn=document.getElementById('btnA');
  btn.textContent='⏳ Analysiere...';btn.disabled=true;
  toast('Analysiere lokal...','info');
  try{
    let r;
    if(mode==='file'&&filePath){r=await window.pywebview.api.protect_file(filePath);if(r.error){toast(r.error,'err');btn.textContent='🔒 Anonymisieren';btn.disabled=false;return}}
    else{const t=document.getElementById('input').value.trim();if(!t){btn.textContent='🔒 Anonymisieren';btn.disabled=false;return}r=await window.pywebview.api.protect(t)}
    lastResult=r;
    document.getElementById('anonText').textContent=r.text;
    document.getElementById('mapCount').textContent=r.count+' sensible Begriffe geschützt — klicke × um falsche Erkennungen zu entfernen';
    renderMappings(r);
    toast(r.count+' Begriffe geschützt. In Zwischenablage kopiert!','ok');
    go('result');
  }catch(e){toast('Fehler: '+e,'err')}
  btn.textContent='🔒 Anonymisieren';btn.disabled=false;
}

async function deanonymize(){
  const t=document.getElementById('aiResp').value.trim();if(!t)return;
  try{const r=await window.pywebview.api.restore(t);document.getElementById('resText').textContent=r.text;toast(r.count+' Begriffe wiederhergestellt. Kopiert!','ok');go('done')}
  catch(e){toast('Fehler: '+e,'err')}
}

function renderMappings(r){
  const ml=document.getElementById('mapList');
  ml.innerHTML=Object.entries(r.mappings).map(([k,v])=>
    '<div class="m-row" style="cursor:pointer" title="Klicken um diese Erkennung zu entfernen" onclick="removeMapping(\''+esc(k).replace(/'/g,"\\'")+'\',\''+esc(v).replace(/'/g,"\\'")+'\')"><span class="m-old">'+esc(v)+'</span><span class="m-arr">→</span><span class="m-new">'+esc(k)+'</span><span style="color:var(--error);opacity:0.5;margin-left:auto;font-size:14px"> ×</span></div>'
  ).join('');
}

function removeMapping(codename,original){
  if(!lastResult)return;
  // Remove from mappings
  const newMappings={};
  for(const[k,v] of Object.entries(lastResult.mappings)){
    if(k!==codename)newMappings[k]=v;
  }
  // Rebuild anonymized text: replace codename back with original
  let newText=lastResult.text;
  newText=newText.split(codename).join(original);
  lastResult.mappings=newMappings;
  lastResult.text=newText;
  lastResult.count=Object.keys(newMappings).length;
  // Update display
  document.getElementById('anonText').textContent=newText;
  document.getElementById('mapCount').textContent=lastResult.count+' sensible Begriffe geschützt';
  renderMappings(lastResult);
  // Copy updated text
  navigator.clipboard.writeText(newText).catch(()=>{});
  toast('"'+original+'" wiederhergestellt','ok');
}

function copyAnon(){navigator.clipboard.writeText(document.getElementById('anonText').textContent);toast('Kopiert!','ok')}
function copyRes(){navigator.clipboard.writeText(document.getElementById('resText').textContent);toast('Kopiert!','ok')}
function reset(){document.getElementById('input').value='';document.getElementById('aiResp').value='';clearFile();go('input')}

async function pasteAI(){try{const t=await window.pywebview.api.paste_clipboard();if(t)document.getElementById("aiResp").value=t;toast("Eingefügt!","ok")}catch(e){}}

async function proxyToggle(){document.getElementById('pLabel').textContent='…';try{await window.pywebview.api.proxy_toggle()}catch(e){}setTimeout(checkProxy,1500)}
async function checkProxy(){try{const s=await window.pywebview.api.proxy_status();document.getElementById('dot').classList.toggle('on',s.running);document.getElementById('pLabel').textContent=s.running?'Proxy aktiv':'Proxy aus'}catch(e){}}

window.addEventListener('pywebviewready',()=>{checkProxy();setInterval(checkProxy,8000)});
</script>
</body></html>"""

window = webview.create_window("AUSTR.AI", html=HTML, js_api=API(), width=720, height=820,
                               min_size=(520, 600), background_color="#0f172a")
API().window = window  # won't work for file dialog, fix below

def main():
    api = API()
    w = webview.create_window("AUSTR.AI", html=HTML, js_api=api, width=720, height=820,
                              min_size=(520, 600), background_color="#0f172a")
    api.window = w
    webview.start()

if __name__ == "__main__":
    main()
