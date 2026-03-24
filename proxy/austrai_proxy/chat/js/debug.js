/**
 * AUSTR.AI — Debug / Transparency Panel
 * Lets users verify what the proxy actually does:
 * - Test anonymization without sending to LLM
 * - View request log (what the LLM actually received)
 * - Machine-verifiable proof, not LLM promises
 */

import { toast } from './state.js';
import * as api from './api.js';
import { t, getLang } from './i18n.js';

const SVG = {
  eye: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>',
  shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>',
};

let overlay;

export function init() {
  // Create overlay element
  overlay = document.createElement('div');
  overlay.id = 'debug-overlay';
  overlay.className = 'aai-overlay';
  overlay.hidden = true;
  document.body.appendChild(overlay);
}

export function open() {
  overlay.hidden = false;
  render();
}

function close() {
  overlay.hidden = true;
}

async function render() {
  overlay.innerHTML = `
    <div class="aai-modal" style="max-width:720px" role="dialog" aria-label="Privacy Transparency Test">
      <div class="aai-modal-header">
        <h2>${SVG.eye} Privacy Transparency Test</h2>
        <button class="aai-btn aai-btn--ghost aai-btn--icon" id="debug-close">&times;</button>
      </div>
      <div class="aai-modal-body">
        <div class="aai-tabs" role="tablist">
          <button class="aai-tab active" data-tab="test" role="tab">Anonymisierung testen</button>
          <button class="aai-tab" data-tab="log" role="tab">Request-Log</button>
        </div>

        <!-- Test Tab -->
        <div class="aai-tab-content active" id="debug-tab-test">
          <p style="font-size:13px;color:var(--text-secondary);margin-bottom:12px">
            Gib Text mit personenbezogenen Daten ein. Der Proxy anonymisiert ihn — <strong>ohne</strong> etwas an ein LLM zu senden. Du siehst exakt, was ersetzt wird.
          </p>
          <div class="aai-field">
            <textarea class="aai-input" id="debug-input" rows="4" placeholder="z.B.: Dr. Müller wohnt in Wien, seine IBAN ist AT12 3456 7890 1234 5678, Mail: test@example.com" style="font-size:14px;line-height:1.6;resize:vertical"></textarea>
          </div>
          <div style="display:flex;gap:8px;margin-bottom:16px">
            <button class="aai-btn aai-btn--primary" id="debug-run">Anonymisierung testen</button>
          </div>
          <div id="debug-result"></div>
        </div>

        <!-- Log Tab -->
        <div class="aai-tab-content" id="debug-tab-log">
          <p style="font-size:13px;color:var(--text-secondary);margin-bottom:12px">
            Jeder Chat-Request wird hier protokolliert. Du siehst exakt, was der Proxy an das LLM gesendet hat — Original vs. Anonymisiert.
          </p>
          <div style="display:flex;gap:8px;margin-bottom:12px">
            <button class="aai-btn aai-btn--ghost aai-btn--sm" id="debug-refresh">${SVG.refresh} Aktualisieren</button>
            <button class="aai-btn aai-btn--danger aai-btn--sm" id="debug-clear">${SVG.trash} Log leeren</button>
          </div>
          <div id="debug-log-content"></div>
        </div>
      </div>
    </div>
  `;

  wireEvents();
}

function wireEvents() {
  overlay.querySelector('#debug-close').onclick = close;
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

  // Tabs
  overlay.querySelectorAll('.aai-tab').forEach(tab => {
    tab.onclick = () => {
      overlay.querySelectorAll('.aai-tab').forEach(t => t.classList.remove('active'));
      overlay.querySelectorAll('.aai-tab-content').forEach(c => c.classList.remove('active'));
      tab.classList.add('active');
      overlay.querySelector(`#debug-tab-${tab.dataset.tab}`).classList.add('active');
      if (tab.dataset.tab === 'log') loadLog();
    };
  });

  // Test button
  overlay.querySelector('#debug-run').onclick = runTest;

  // Enter in textarea
  overlay.querySelector('#debug-input').onkeydown = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      runTest();
    }
  };

  // Log controls
  overlay.querySelector('#debug-refresh').onclick = loadLog;
  overlay.querySelector('#debug-clear').onclick = async () => {
    await api.debugClear();
    toast('Log geleert', 'info');
    loadLog();
  };
}

async function runTest() {
  const input = overlay.querySelector('#debug-input');
  const resultEl = overlay.querySelector('#debug-result');
  const text = input.value.trim();
  if (!text) return;

  resultEl.innerHTML = '<p style="color:var(--text-muted)">Wird verarbeitet…</p>';

  try {
    const r = await api.debugTest(text);
    resultEl.innerHTML = renderTestResult(r);
  } catch (err) {
    resultEl.innerHTML = `<p style="color:var(--danger)">${esc(err.message)}</p>`;
  }
}

function renderTestResult(r) {
  const statusColor = r.is_changed ? 'var(--accent)' : 'var(--success)';
  const statusText = r.is_changed
    ? `${r.entity_count} Entität(en) erkannt und anonymisiert`
    : 'Keine personenbezogenen Daten erkannt';

  return `
    <div class="aai-debug-status" style="padding:8px 12px;border-radius:var(--radius-md);background:${r.is_changed ? 'var(--accent-bg)' : 'var(--success-bg)'};color:${statusColor};font-size:13px;font-weight:600;margin-bottom:12px">
      ${SVG.shield} ${statusText}
    </div>

    <div class="aai-upload-diff">
      <div class="aai-upload-pane">
        <div class="aai-upload-pane-label">Original (deine Eingabe)</div>
        <div style="white-space:pre-wrap;word-break:break-word">${esc(r.original)}</div>
      </div>
      <div class="aai-upload-pane">
        <div class="aai-upload-pane-label" style="color:var(--accent)">Anonymisiert (was das LLM sehen würde)</div>
        <div style="white-space:pre-wrap;word-break:break-word">${highlightAnonymized(esc(r.anonymized))}</div>
      </div>
    </div>

    ${r.entities.length ? `
      <div style="margin-top:12px">
        <div class="aai-upload-pane-label">Ersetzungen (Mapping-Tabelle)</div>
        <table class="aai-table" style="margin-top:4px">
          <thead><tr><th>Typ</th><th>Original</th><th>Ersetzt durch</th></tr></thead>
          <tbody>
            ${r.entities.map(e => `
              <tr>
                <td><span class="aai-entity-type">${esc(e.type)}</span></td>
                <td style="font-family:var(--font-mono);font-size:12px;color:var(--danger)">${esc(e.original)}</td>
                <td style="font-family:var(--font-mono);font-size:12px;color:var(--accent)">${esc(e.codename)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    ` : ''}

    <div style="margin-top:12px;font-size:11px;color:var(--text-muted)">
      Schwelle: ${r.confidence_threshold} &nbsp;|&nbsp;
      Allow-List: ${r.allow_list?.length || 0} Begriffe &nbsp;|&nbsp;
      Deny-List: ${r.deny_list?.length || 0} Begriffe
    </div>
  `;
}

function highlightAnonymized(text) {
  // Highlight [PLACEHOLDER_N] patterns
  return text.replace(/\[([A-Z_]+_\d+)\]/g, '<span style="background:var(--accent-bg);color:var(--accent);padding:1px 4px;border-radius:3px;font-family:var(--font-mono);font-size:12px">[$1]</span>');
}

async function loadLog() {
  const container = overlay.querySelector('#debug-log-content');
  container.innerHTML = '<p style="color:var(--text-muted)">Wird geladen…</p>';

  try {
    const data = await api.debugLog(20);
    if (!data.entries.length) {
      container.innerHTML = '<p style="color:var(--text-muted)">Noch keine Requests protokolliert. Sende eine Chat-Nachricht und sieh dann hier nach.</p>';
      return;
    }
    container.innerHTML = data.entries.map(renderLogEntry).join('');
  } catch (err) {
    container.innerHTML = `<p style="color:var(--danger)">${esc(err.message)}</p>`;
  }
}

function renderLogEntry(entry) {
  const date = new Date(entry.timestamp * 1000);
  const timeStr = date.toLocaleTimeString('de-AT', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const piiClass = entry.pii_removed ? 'var(--accent)' : 'var(--success)';
  const piiLabel = entry.pii_removed
    ? `${entry.entity_count} PII entfernt`
    : 'Keine PII';

  return `
    <details class="aai-debug-entry" style="margin-bottom:8px;background:var(--bg-secondary);border-radius:var(--radius-md);border:1px solid var(--border)">
      <summary style="padding:10px 14px;cursor:pointer;display:flex;align-items:center;gap:8px;font-size:13px">
        <span style="color:var(--text-muted);min-width:65px">${timeStr}</span>
        <span style="color:var(--text-secondary)">${esc(entry.provider)}/${esc(entry.model)}</span>
        <span style="margin-left:auto;color:${piiClass};font-weight:600;font-size:12px">${piiLabel}</span>
      </summary>
      <div style="padding:0 14px 14px">
        <div class="aai-upload-diff" style="margin-bottom:8px">
          <div class="aai-upload-pane">
            <div class="aai-upload-pane-label">Original (User-Input)</div>
            <div style="white-space:pre-wrap;word-break:break-word;font-size:13px">${esc(entry.original_message?.slice(0, 500) || '')}</div>
          </div>
          <div class="aai-upload-pane">
            <div class="aai-upload-pane-label" style="color:var(--accent)">Anonymisiert (an LLM gesendet)</div>
            <div style="white-space:pre-wrap;word-break:break-word;font-size:13px">${highlightAnonymized(esc(entry.anonymized_message?.slice(0, 500) || ''))}</div>
          </div>
        </div>

        ${Object.keys(entry.mappings || {}).length ? `
          <div style="margin-top:8px">
            <div class="aai-upload-pane-label">Mappings</div>
            <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">
              ${Object.entries(entry.mappings).map(([code, orig]) =>
                `<span class="aai-tag"><span style="color:var(--danger)">${esc(orig)}</span> → <span style="color:var(--accent)">${esc(code)}</span></span>`
              ).join('')}
            </div>
          </div>
        ` : ''}

        <details style="margin-top:8px">
          <summary style="font-size:11px;color:var(--text-muted);cursor:pointer">Vollständiger API-Request anzeigen</summary>
          <pre class="aai-codeblock" style="margin-top:4px"><code style="font-size:11px">${esc(JSON.stringify(entry.api_body_messages, null, 2))}</code></pre>
        </details>
      </div>
    </details>
  `;
}

function esc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
