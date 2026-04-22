/**
 * AUSTR.AI — Debug / Transparency Panel (Preact)
 * Machine-verifiable proof of what the proxy actually sends to LLMs.
 * - Test anonymization without sending to LLM
 * - View request log
 */

import { h, render, Fragment } from 'preact';
import { useState, useEffect, useRef } from 'preact/hooks';
import htm from 'htm';
import { toast } from './state.js';
import * as api from './api.js';

const html = htm.bind(h);

const SVG_EYE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
const SVG_SHIELD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';
const SVG_TRASH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>';
const SVG_REFRESH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>';

function highlightAnonymized(text) {
  return String(text || '').replace(
    /\[([A-Z_]+_\d+)\]/g,
    '<span style="background:var(--accent-bg);color:var(--accent);padding:1px 4px;border-radius:3px;font-family:var(--font-mono);font-size:12px">[$1]</span>',
  );
}

function esc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ---- Test Tab ---- */

function TestResult({ result }) {
  const statusColor = result.is_changed ? 'var(--accent)' : 'var(--success)';
  const bgColor = result.is_changed ? 'var(--accent-bg)' : 'var(--success-bg)';
  const statusText = result.is_changed
    ? `${result.entity_count} Entität(en) erkannt und anonymisiert`
    : 'Keine personenbezogenen Daten erkannt';

  return html`
    <${Fragment}>
      <div
        class="aai-debug-status"
        style=${`padding:8px 12px;border-radius:var(--radius-md);background:${bgColor};color:${statusColor};font-size:13px;font-weight:600;margin-bottom:12px`}
      >
        <span dangerouslySetInnerHTML=${{ __html: SVG_SHIELD }} /> ${statusText}
      </div>

      <div class="aai-upload-diff">
        <div class="aai-upload-pane">
          <div class="aai-upload-pane-label">Original (deine Eingabe)</div>
          <div style="white-space:pre-wrap;word-break:break-word">${result.original}</div>
        </div>
        <div class="aai-upload-pane">
          <div class="aai-upload-pane-label" style="color:var(--accent)">Anonymisiert (was das LLM sehen würde)</div>
          <div
            style="white-space:pre-wrap;word-break:break-word"
            dangerouslySetInnerHTML=${{ __html: highlightAnonymized(esc(result.anonymized)) }}
          />
        </div>
      </div>

      ${result.entities.length ? html`
        <div style="margin-top:12px">
          <div class="aai-upload-pane-label">Ersetzungen (Mapping-Tabelle)</div>
          <table class="aai-table" style="margin-top:4px">
            <thead><tr><th>Typ</th><th>Original</th><th>Ersetzt durch</th></tr></thead>
            <tbody>
              ${result.entities.map((e, i) => html`
                <tr key=${i}>
                  <td><span class="aai-entity-type">${e.type}</span></td>
                  <td style="font-family:var(--font-mono);font-size:12px;color:var(--danger)">${e.original}</td>
                  <td style="font-family:var(--font-mono);font-size:12px;color:var(--accent)">${e.codename}</td>
                </tr>
              `)}
            </tbody>
          </table>
        </div>
      ` : null}

      <div style="margin-top:12px;font-size:11px;color:var(--text-muted)">
        Schwelle: ${result.confidence_threshold} &nbsp;|&nbsp;
        Allow-List: ${result.allow_list?.length || 0} Begriffe &nbsp;|&nbsp;
        Deny-List: ${result.deny_list?.length || 0} Begriffe
      </div>
    <//>
  `;
}

function TestTab() {
  const [text, setText] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function runTest() {
    const trimmed = text.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      const r = await api.debugTest(trimmed);
      setResult(r);
    } catch (err) {
      setError(err.message);
      setResult(null);
    }
    setLoading(false);
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      runTest();
    }
  }

  return html`
    <div class="aai-tab-content active">
      <p style="font-size:13px;color:var(--text-secondary);margin-bottom:12px">
        Gib Text mit personenbezogenen Daten ein. Der Proxy anonymisiert ihn — <strong>ohne</strong> etwas an ein LLM zu senden. Du siehst exakt, was ersetzt wird.
      </p>
      <div class="aai-field">
        <textarea
          class="aai-input"
          rows="4"
          placeholder="z.B.: Dr. Müller wohnt in Wien, seine IBAN ist AT12 3456 7890 1234 5678, Mail: test@example.com"
          style="font-size:14px;line-height:1.6;resize:vertical"
          value=${text}
          onInput=${(e) => setText(e.target.value)}
          onKeyDown=${handleKeyDown}
        ></textarea>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:16px">
        <button class="aai-btn aai-btn--primary" onClick=${runTest} disabled=${loading}>
          ${loading ? 'Wird verarbeitet…' : 'Anonymisierung testen'}
        </button>
      </div>
      ${error ? html`<p style="color:var(--danger)">${error}</p>` : null}
      ${result ? html`<${TestResult} result=${result} />` : null}
    </div>
  `;
}

/* ---- Log Tab ---- */

function LogEntry({ entry }) {
  const date = new Date(entry.timestamp * 1000);
  const timeStr = date.toLocaleTimeString('de-AT', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const piiClass = entry.pii_removed ? 'var(--accent)' : 'var(--success)';
  const piiLabel = entry.pii_removed ? `${entry.entity_count} PII entfernt` : 'Keine PII';

  const mappings = entry.mappings || {};

  return html`
    <details class="aai-debug-entry" style="margin-bottom:8px;background:var(--bg-secondary);border-radius:var(--radius-md);border:1px solid var(--border)">
      <summary style="padding:10px 14px;cursor:pointer;display:flex;align-items:center;gap:8px;font-size:13px">
        <span style="color:var(--text-muted);min-width:65px">${timeStr}</span>
        <span style="color:var(--text-secondary)">${entry.provider}/${entry.model}</span>
        <span style=${`margin-left:auto;color:${piiClass};font-weight:600;font-size:12px`}>${piiLabel}</span>
      </summary>
      <div style="padding:0 14px 14px">
        <div class="aai-upload-diff" style="margin-bottom:8px">
          <div class="aai-upload-pane">
            <div class="aai-upload-pane-label">Original (User-Input)</div>
            <div style="white-space:pre-wrap;word-break:break-word;font-size:13px">${entry.original_message?.slice(0, 500) || ''}</div>
          </div>
          <div class="aai-upload-pane">
            <div class="aai-upload-pane-label" style="color:var(--accent)">Anonymisiert (an LLM gesendet)</div>
            <div
              style="white-space:pre-wrap;word-break:break-word;font-size:13px"
              dangerouslySetInnerHTML=${{ __html: highlightAnonymized(esc(entry.anonymized_message?.slice(0, 500) || '')) }}
            />
          </div>
        </div>

        ${Object.keys(mappings).length ? html`
          <div style="margin-top:8px">
            <div class="aai-upload-pane-label">Mappings</div>
            <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">
              ${Object.entries(mappings).map(([code, orig]) => html`
                <span key=${code} class="aai-tag">
                  <span style="color:var(--danger)">${orig}</span>
                  ${' → '}
                  <span style="color:var(--accent)">${code}</span>
                </span>
              `)}
            </div>
          </div>
        ` : null}

        <details style="margin-top:8px">
          <summary style="font-size:11px;color:var(--text-muted);cursor:pointer">Vollständiger API-Request anzeigen</summary>
          <pre class="aai-codeblock" style="margin-top:4px"><code style="font-size:11px">${JSON.stringify(entry.api_body_messages, null, 2)}</code></pre>
        </details>
      </div>
    </details>
  `;
}

function LogTab({ active }) {
  const [entries, setEntries] = useState(null); // null = not loaded yet
  const [error, setError] = useState(null);

  async function loadLog() {
    setError(null);
    try {
      const data = await api.debugLog(20);
      setEntries(data.entries);
    } catch (err) { setError(err.message); }
  }

  async function clearLog() {
    await api.debugClear();
    toast('Log geleert', 'info');
    loadLog();
  }

  useEffect(() => { if (active) loadLog(); }, [active]);

  return html`
    <div class=${`aai-tab-content${active ? ' active' : ''}`}>
      <p style="font-size:13px;color:var(--text-secondary);margin-bottom:12px">
        Jeder Chat-Request wird hier protokolliert. Du siehst exakt, was der Proxy an das LLM gesendet hat — Original vs. Anonymisiert.
      </p>
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <button class="aai-btn aai-btn--ghost aai-btn--sm" onClick=${loadLog}>
          <span dangerouslySetInnerHTML=${{ __html: SVG_REFRESH }} /> Aktualisieren
        </button>
        <button class="aai-btn aai-btn--danger aai-btn--sm" onClick=${clearLog}>
          <span dangerouslySetInnerHTML=${{ __html: SVG_TRASH }} /> Log leeren
        </button>
      </div>
      ${error ? html`<p style="color:var(--danger)">${error}</p>` : null}
      ${entries === null ? html`<p style="color:var(--text-muted)">Wird geladen…</p>` : null}
      ${entries !== null && entries.length === 0 ? html`
        <p style="color:var(--text-muted)">Noch keine Requests protokolliert. Sende eine Chat-Nachricht und sieh dann hier nach.</p>
      ` : null}
      ${entries !== null && entries.length > 0 ? entries.map((e, i) => html`<${LogEntry} key=${i} entry=${e} />`) : null}
    </div>
  `;
}

/* ---- Root Component ---- */

function DebugOverlayView({ onClose }) {
  const [tab, setTab] = useState('test');

  function handleBackdropClick(e) {
    if (e.target === e.currentTarget) onClose();
  }

  return html`
    <div onClick=${handleBackdropClick} style="width:100%;height:100%;display:flex;align-items:center;justify-content:center">
      <div class="aai-modal" style="max-width:720px" role="dialog" aria-label="Privacy Transparency Test">
        <div class="aai-modal-header">
          <h2><span dangerouslySetInnerHTML=${{ __html: SVG_EYE }} /> Privacy Transparency Test</h2>
          <button class="aai-btn aai-btn--ghost aai-btn--icon" onClick=${onClose}>×</button>
        </div>
        <div class="aai-modal-body">
          <div class="aai-tabs" role="tablist">
            <button class=${`aai-tab${tab === 'test' ? ' active' : ''}`} role="tab" onClick=${() => setTab('test')}>
              Anonymisierung testen
            </button>
            <button class=${`aai-tab${tab === 'log' ? ' active' : ''}`} role="tab" onClick=${() => setTab('log')}>
              Request-Log
            </button>
          </div>
          ${tab === 'test' ? html`<${TestTab} />` : null}
          ${tab === 'log' ? html`<${LogTab} active=${true} />` : null}
        </div>
      </div>
    </div>
  `;
}

/* ---- Exports ---- */

let overlay;

export function init() {
  overlay = document.createElement('div');
  overlay.id = 'debug-overlay';
  overlay.className = 'aai-overlay';
  overlay.hidden = true;
  document.body.appendChild(overlay);
}

export function open() {
  if (!overlay) return;
  overlay.hidden = false;
  render(
    html`<${DebugOverlayView} onClose=${close} />`,
    overlay,
  );
}

function close() {
  if (!overlay) return;
  overlay.hidden = true;
  render(null, overlay);
}
