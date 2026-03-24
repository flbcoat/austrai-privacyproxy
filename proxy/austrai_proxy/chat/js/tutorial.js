/**
 * AUSTR.AI — Interactive Tutorial Page
 * Click-to-expand steps with live mini-demos.
 * Always accessible from sidebar.
 */

import { get, set, toast } from './state.js';
import * as api from './api.js';
import { getLang } from './i18n.js';

let container;

export function init() {
  container = document.getElementById('tutorial-view');
  if (!container) return;

  // Add tutorial button to sidebar footer
  const footer = document.querySelector('.aai-sidebar-footer');
  if (footer && !document.getElementById('btn-tutorial')) {
    const btn = document.createElement('button');
    btn.id = 'btn-tutorial';
    btn.className = 'aai-btn aai-btn--ghost';
    btn.style.cssText = 'width:100%;justify-content:flex-start';
    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg><span>Hilfe & Tutorial</span>`;
    btn.addEventListener('click', show);
    footer.insertBefore(btn, footer.firstChild);
  }
}

export function show() {
  if (window.__aai_showView) window.__aai_showView('tutorial-view');
  render();
}

function back() {
  const mode = document.querySelector('.aai-sidebar-nav-btn.active')?.dataset.mode;
  if (mode === 'tools') {
    if (window.__aai_showView) window.__aai_showView('tool-view');
  } else {
    const viewId = get('currentConversationId') ? 'chat-view' : 'welcome-view';
    if (window.__aai_showView) window.__aai_showView(viewId);
  }
}

function render() {
  container.innerHTML = `
    <div class="aai-tutorial">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
        <h2>Hilfe & Tutorial</h2>
        <button class="aai-btn aai-btn--ghost aai-btn--sm" id="tutorial-back">← Zurück</button>
      </div>
      <p>Klicke auf ein Thema um es zu öffnen. Dieses Tutorial ist jederzeit über die Sidebar erreichbar.</p>

      <!-- Step 1: Was ist AUSTR.AI -->
      <div class="aai-tutorial-step open" data-step="0">
        <div class="aai-tutorial-step-header">
          <span class="aai-tutorial-step-num">1</span>
          <span class="aai-tutorial-step-title">So funktioniert AUSTR.AI</span>
          <span class="aai-tutorial-step-arrow">▼</span>
        </div>
        <div class="aai-tutorial-step-body">
          <div class="aai-tutorial-visual" style="padding:20px;text-align:center">
            <div style="display:flex;align-items:center;justify-content:center;gap:8px;flex-wrap:wrap;margin-bottom:16px">
              <div class="aai-tut-box aai-tut-box--danger">Dr. Müller<br>IBAN AT48 2011...</div>
              <div class="aai-tut-arrow">→</div>
              <div class="aai-tut-box aai-tut-box--accent">[PERSON_1]<br>[AT_IBAN_1]</div>
              <div class="aai-tut-arrow">→ KI →</div>
              <div class="aai-tut-box aai-tut-box--success">Dr. Müller<br>IBAN AT48 2011...</div>
            </div>
            <p style="color:var(--text-muted);font-size:13px">Deine Daten werden <strong>lokal</strong> anonymisiert. Die KI sieht nur Platzhalter. Die Antwort wird automatisch wiederhergestellt.</p>
          </div>
        </div>
      </div>

      <!-- Step 2: Live-Demo -->
      <div class="aai-tutorial-step" data-step="1">
        <div class="aai-tutorial-step-header">
          <span class="aai-tutorial-step-num">2</span>
          <span class="aai-tutorial-step-title">Probier es aus — Live-Demo</span>
          <span class="aai-tutorial-step-arrow">▼</span>
        </div>
        <div class="aai-tutorial-step-body">
          <p style="margin-bottom:10px">Gib Text mit persönlichen Daten ein und sieh was passiert:</p>
          <div style="display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap">
            <button class="aai-chip aai-tut-example" data-text="Dr. Müller wohnt in der Mariahilfer Straße 45, 1060 Wien. Seine IBAN ist AT48 2011 1820 8120 0100 und seine Mail ist mueller@example.at">Beispiel laden</button>
          </div>
          <textarea class="aai-input" id="tut-demo-input" rows="3" placeholder="Text mit Namen, Adressen, IBANs, E-Mails eingeben…" style="font-size:14px;line-height:1.6;resize:vertical;margin-bottom:8px"></textarea>
          <button class="aai-btn aai-btn--primary aai-btn--sm" id="tut-demo-run">Anonymisieren</button>
          <div id="tut-demo-result" style="margin-top:12px"></div>
        </div>
      </div>

      <!-- Step 3: Chat -->
      <div class="aai-tutorial-step" data-step="2">
        <div class="aai-tutorial-step-header">
          <span class="aai-tutorial-step-num">3</span>
          <span class="aai-tutorial-step-title">Chat mit Privacy-Schutz</span>
          <span class="aai-tutorial-step-arrow">▼</span>
        </div>
        <div class="aai-tutorial-step-body">
          <div class="aai-tutorial-visual" style="padding:16px">
            <div style="display:flex;flex-direction:column;gap:10px">
              <div style="display:flex;gap:8px;align-items:start">
                <div class="aai-tut-avatar" style="background:var(--bg-active)">Du</div>
                <div>
                  <div style="font-size:14px">Schreibe eine Antwort an Dr. Müller…</div>
                  <div style="display:flex;gap:4px;margin-top:4px">
                    <span class="aai-tut-badge">🛡 1 Begriff anonymisiert</span>
                    <span class="aai-tut-entity">PERSON → [PERSON_1]</span>
                  </div>
                </div>
              </div>
              <div style="display:flex;gap:8px;align-items:start">
                <div class="aai-tut-avatar" style="background:var(--accent);color:white">KI</div>
                <div style="font-size:14px;color:var(--text-secondary)">Sehr geehrter Dr. Müller, …</div>
              </div>
            </div>
          </div>
          <p style="margin-top:10px;font-size:13px">Wechsle links auf <strong>Chat</strong>, wähle ein Modell, und chatte los. Unter jeder Nachricht siehst du, welche Daten geschützt wurden.</p>
          <p style="font-size:13px;margin-top:4px">💡 <strong>Tipp:</strong> Klicke auf das <strong>Auge-Symbol</strong> neben dem Senden-Button für eine Vorschau bevor die Nachricht rausgeht.</p>
        </div>
      </div>

      <!-- Step 4: Werkzeuge -->
      <div class="aai-tutorial-step" data-step="3">
        <div class="aai-tutorial-step-header">
          <span class="aai-tutorial-step-num">4</span>
          <span class="aai-tutorial-step-title">Werkzeuge: Manuell anonymisieren</span>
          <span class="aai-tutorial-step-arrow">▼</span>
        </div>
        <div class="aai-tutorial-step-body">
          <div class="aai-tutorial-visual" style="padding:16px">
            <div style="display:flex;gap:3px;margin-bottom:12px">
              <span class="aai-tut-step-pill active">1 Original</span>
              <span class="aai-tut-step-pill active">2 Erkennung</span>
              <span class="aai-tut-step-pill active">3 Anonymisiert</span>
              <span class="aai-tut-step-pill">4 LLM</span>
              <span class="aai-tut-step-pill">5 Re-hydriert</span>
            </div>
            <p style="font-size:13px;color:var(--text-secondary)">Schritt für Schritt siehst du, was passiert: Text eingeben → Entitäten erkennen → Anonymisieren → optional an LLM senden → Antwort wiederherstellen.</p>
          </div>
          <p style="margin-top:8px;font-size:13px">Wechsle links auf <strong>Werkzeuge</strong>. Dort kannst du Texte anonymisieren, Entitäten entfernen und die Mapping-Tabelle einsehen — ohne etwas an eine KI zu senden.</p>
        </div>
      </div>

      <!-- Step 5: Einstellungen -->
      <div class="aai-tutorial-step" data-step="4">
        <div class="aai-tutorial-step-header">
          <span class="aai-tutorial-step-num">5</span>
          <span class="aai-tutorial-step-title">Einstellungen & KI-Anbieter</span>
          <span class="aai-tutorial-step-arrow">▼</span>
        </div>
        <div class="aai-tutorial-step-body">
          <div class="aai-tutorial-visual" style="padding:16px">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
              <div class="aai-tut-setting-card">
                <strong>Ollama</strong><br><span style="font-size:12px;color:var(--text-muted)">Komplett lokal, kein API-Key</span>
              </div>
              <div class="aai-tut-setting-card">
                <strong>Claude / GPT</strong><br><span style="font-size:12px;color:var(--text-muted)">Cloud, API-Key nötig</span>
              </div>
            </div>
          </div>
          <p style="margin-top:8px;font-size:13px">Klicke unten links auf <strong>Einstellungen</strong>. Dort konfigurierst du deinen KI-Anbieter, die Erkennungs-Schwelle und die Allow-/Deny-Listen.</p>
          <p style="font-size:13px;margin-top:4px">💡 <strong>Für maximale Privatsphäre</strong> nutze Ollama — dann verlassen keine Daten deinen Rechner.</p>
        </div>
      </div>

      <!-- Step 6: Kontrolle -->
      <div class="aai-tutorial-step" data-step="5">
        <div class="aai-tutorial-step-header">
          <span class="aai-tutorial-step-num">6</span>
          <span class="aai-tutorial-step-title">Du hast die volle Kontrolle</span>
          <span class="aai-tutorial-step-arrow">▼</span>
        </div>
        <div class="aai-tutorial-step-body">
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px">
            <div class="aai-tut-control-card">
              <strong>✓ Bestätigungsschritt</strong>
              <p>Jede Nachricht zeigt dir die Anonymisierung <em>bevor</em> sie gesendet wird.</p>
            </div>
            <div class="aai-tut-control-card">
              <strong>✓ Allow-List</strong>
              <p>Begriffe die nie anonymisiert werden sollen.</p>
            </div>
            <div class="aai-tut-control-card">
              <strong>✓ Transparenz-Log</strong>
              <p>Prüfe jederzeit, was wirklich ans LLM ging.</p>
            </div>
            <div class="aai-tut-control-card">
              <strong>✓ Verschlüsselt</strong>
              <p>Gespräche lokal mit AES gespeichert.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  wireEvents();
}

function wireEvents() {
  container.querySelector('#tutorial-back')?.addEventListener('click', back);

  // Accordion
  container.querySelectorAll('.aai-tutorial-step-header').forEach(header => {
    header.addEventListener('click', () => {
      header.closest('.aai-tutorial-step').classList.toggle('open');
    });
  });

  // Live demo: example button
  container.querySelectorAll('.aai-tut-example').forEach(btn => {
    btn.addEventListener('click', () => {
      const input = container.querySelector('#tut-demo-input');
      if (input) input.value = btn.dataset.text;
    });
  });

  // Live demo: run
  container.querySelector('#tut-demo-run')?.addEventListener('click', async () => {
    const input = container.querySelector('#tut-demo-input');
    const resultEl = container.querySelector('#tut-demo-result');
    const text = input?.value.trim();
    if (!text || !resultEl) return;

    resultEl.innerHTML = '<p style="color:var(--text-muted);font-size:13px">Wird analysiert…</p>';

    try {
      const r = await api.debugTest(text);
      resultEl.innerHTML = renderDemoResult(r);
    } catch (err) {
      resultEl.innerHTML = `<p style="color:var(--danger);font-size:13px">Fehler: ${esc(err.message)}</p>`;
    }
  });
}

function renderDemoResult(r) {
  if (!r.is_changed) {
    return `<div class="aai-tut-result-box" style="border-color:var(--success)">
      <strong style="color:var(--success)">✓ Keine personenbezogenen Daten erkannt</strong>
      <p style="font-size:13px;color:var(--text-muted);margin-top:4px">Dieser Text würde unverändert an die KI gehen.</p>
    </div>`;
  }

  return `
    <div class="aai-tut-result-box">
      <strong style="color:var(--accent)">🛡 ${r.entity_count} Begriff(e) anonymisiert</strong>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0">
        <div>
          <div style="font-size:10px;font-weight:600;text-transform:uppercase;color:var(--text-muted);margin-bottom:4px">Dein Text</div>
          <div class="aai-tut-text-box">${esc(r.original)}</div>
        </div>
        <div>
          <div style="font-size:10px;font-weight:600;text-transform:uppercase;color:var(--accent);margin-bottom:4px">Was die KI sieht</div>
          <div class="aai-tut-text-box" style="border-color:var(--accent-border)">${highlightAnon(esc(r.anonymized))}</div>
        </div>
      </div>

      <div style="font-size:10px;font-weight:600;text-transform:uppercase;color:var(--text-muted);margin-bottom:6px">Ersetzungen</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px">
        ${r.entities.map(e => `
          <span style="display:inline-flex;align-items:center;gap:4px;background:var(--bg-sidebar);border-radius:var(--r-full);padding:3px 10px;font-size:12px">
            <span style="font-size:9px;font-weight:600;text-transform:uppercase;background:var(--accent-subtle);color:var(--accent);padding:1px 5px;border-radius:3px">${esc(e.type)}</span>
            <span style="color:var(--danger);text-decoration:line-through">${esc(e.original)}</span>
            → <span style="color:var(--accent);font-family:var(--mono);font-size:11px">${esc(e.codename)}</span>
          </span>
        `).join('')}
      </div>
    </div>
  `;
}

function highlightAnon(text) {
  return text.replace(/\[([A-Z_]+_\d+)\]/g, '<span style="background:var(--accent-subtle);color:var(--accent);padding:1px 4px;border-radius:3px;font-family:var(--mono);font-size:12px">[$1]</span>');
}

function esc(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
