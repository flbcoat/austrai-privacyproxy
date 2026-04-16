/**
 * AUSTR.AI — Anonymization Tool (5-Step Pipeline)
 * Features:
 * - 5 steps: Original → Erkennung → Anonymisiert → LLM → Re-hydriert
 * - Click-to-anonymize: select text in Original view → add to deny-list
 * - Click-to-dismiss: click highlighted entity to remove it
 * - Example texts for quick testing
 */

import { get, set, on, toast } from './state.js';
import * as api from './api.js';
import { t, getLang } from './i18n.js';
import { renderMarkdown } from './markdown.js';

const EXAMPLES = {
  email: {
    de: 'Geschäfts-E-Mail',
    text: `Sehr geehrter Herr Dr. Gruber,

bezüglich unserer Besprechung am 15. März möchte ich die Überweisung von 4.500 € bestätigen. Bitte überweisen Sie den Betrag auf IBAN AT48 2011 1820 8120 0100.

Bei Fragen erreichen Sie mich unter +43 660 1234567 oder sabine.leitner@example.at.

Mit freundlichen Grüßen,
Mag. Sabine Leitner
Leitner & Partner GmbH
Mariahilfer Straße 45, 1060 Wien`,
  },
  medical: {
    de: 'Arzt-Befund',
    text: `Patient: Johann Wieser, geb. 12.04.1978
SVNr: 1234 120478
Diagnose: Diabetes mellitus Typ 2 (E11.9)
Medikation: Metformin 1000mg, 2x täglich

Nächster Termin: 22.04.2026 bei Dr. med. Maria Hofmann
Ordination: Währinger Gürtel 18-20, 1090 Wien
Tel: +43 1 40400-0`,
  },
  contract: {
    de: 'Vertragsklausel',
    text: `Zwischen der Alpha Tech Solutions GmbH (FN 123456a), vertreten durch Geschäftsführer Thomas Berger, Kärntner Ring 12, 1010 Wien, und Frau Lisa Maier, wohnhaft in Salzburger Straße 78, 5020 Salzburg, wird folgender Vertrag geschlossen. Die Vergütung beträgt 85.000 € brutto p.a., zahlbar auf Konto IBAN DE89 3704 0044 0532 0130 00 bei der Commerzbank AG.`,
  },
};

const STEPS = [
  { id: 'original', de: 'Original', en: 'Original' },
  { id: 'detection', de: 'Erkennung', en: 'Detection' },
  { id: 'anonymized', de: 'Anonymisiert', en: 'Anonymized' },
  { id: 'llm', de: 'LLM-Antwort', en: 'LLM Response' },
  { id: 'rehydrated', de: 'Re-hydriert', en: 'Rehydrated' },
];

let container;
let state = {
  step: 0,
  inputText: '',
  result: null,
  llmResponse: '',
  rehydrated: '',
  isProcessing: false,
  isStreaming: false,
  dismissedEntities: new Set(),
};

export function init() {
  container = document.getElementById('tool-view');
  if (!container) return;
  render();
}

function render() {
  const isDE = getLang() === 'de';

  container.innerHTML = `
    <div class="aai-tool">
      <div class="aai-tool-input-section">
        <div class="aai-tool-header">
          <h2>${isDE ? 'Anonymisierungs-Werkzeug' : 'Anonymization Tool'}</h2>
          <p>${isDE ? 'Text einfügen, Anonymisierung prüfen, optional an LLM senden.' : 'Paste text, check anonymization, optionally send to LLM.'}</p>
        </div>

        <div class="aai-tool-examples">
          ${Object.entries(EXAMPLES).map(([key, ex]) =>
            `<button class="aai-chip" data-example="${key}">${ex.de}</button>`
          ).join('')}
        </div>

        <div class="aai-tool-textarea-wrap">
          <textarea class="aai-input aai-tool-textarea" id="tool-text" rows="6" placeholder="${isDE ? 'Text mit personenbezogenen Daten eingeben…' : 'Enter text with personal data…'}">${esc(state.inputText)}</textarea>
          <div class="aai-tool-textarea-footer">
            <span class="aai-tool-char-count" id="tool-char-count">${state.inputText.length} / 5000</span>
            <div class="aai-tool-textarea-actions">
              <button class="aai-btn aai-btn--ghost aai-btn--sm" id="tool-clear">${isDE ? 'Leeren' : 'Clear'}</button>
              <button class="aai-btn aai-btn--primary" id="tool-analyze" ${state.isProcessing ? 'disabled' : ''}>
                ${state.isProcessing ? (isDE ? 'Wird analysiert…' : 'Analyzing…') : (isDE ? 'Analyse starten' : 'Start Analysis')}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="aai-tool-results" id="tool-results" ${state.result ? '' : 'hidden'}>
        <div class="aai-tool-steps">
          ${STEPS.map((s, i) => `
            <button class="aai-tool-step ${i === state.step ? 'active' : ''} ${i <= getMaxStep() ? '' : 'disabled'}" data-step="${i}">
              <span class="aai-tool-step-num">${i + 1}</span>
              <span class="aai-tool-step-label">${isDE ? s.de : s.en}</span>
            </button>
          `).join('')}
        </div>
        <div class="aai-tool-step-content" id="tool-step-content">
          ${renderStepContent()}
        </div>
      </div>
    </div>

    <!-- Floating action popup for text selection -->
    <div id="text-select-popup" class="aai-select-popup" hidden>
      <button class="aai-btn aai-btn--primary aai-btn--sm" id="btn-add-deny">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        Anonymisieren
      </button>
    </div>
  `;

  wireEvents();
}

function getMaxStep() {
  if (state.rehydrated) return 4;
  if (state.llmResponse) return 3;
  if (state.result) return 2;
  return 0;
}

function renderStepContent() {
  const r = state.result;
  const isDE = getLang() === 'de';
  if (!r) return '';

  switch (state.step) {
    case 0: // Original — with click-to-anonymize
      return `
        <div class="aai-tool-pane">
          <div class="aai-tool-pane-header">
            ${isDE
              ? 'Originaltext — <strong>markiere einen Begriff</strong> um ihn zur Deny-List hinzuzufügen'
              : 'Original text — <strong>select a term</strong> to add it to the deny list'}
          </div>
          <div class="aai-tool-pane-body aai-tool-text-display aai-tool-selectable" id="tool-original-text">${esc(r.original)}</div>
        </div>`;

    case 1: // Detection — click to dismiss, with protection level badges
      return `
        <div class="aai-tool-pane">
          <div class="aai-tool-pane-header">
            ${isDE
              ? `${r.entity_count - state.dismissedEntities.size} Entität(en) erkannt — klicke auf eine Markierung um sie zu entfernen`
              : `${r.entity_count - state.dismissedEntities.size} entity/entities detected — click a highlight to remove it`}
            ${r.doc_type && r.doc_type !== 'general' ? `<span class="aai-doc-type-badge aai-doc-type-${r.doc_type}">${r.doc_type === 'medical' ? (isDE ? 'Medizinisch' : 'Medical') : (isDE ? 'Rechtlich' : 'Legal')}</span>` : ''}
          </div>
          <div class="aai-tool-pane-body aai-tool-text-display aai-tool-selectable" id="tool-detect-text">${highlightEntities(r.original, r.entities)}</div>
          <div class="aai-tool-entity-legend">
            ${r.entities.filter(e => !state.dismissedEntities.has(e.original)).map(e => `
              <span class="aai-tool-entity-tag" data-dismiss="${escAttr(e.original)}">
                <span class="aai-plevel aai-plevel-${e.protection_level || 2}" title="${esc(e.protection_label || 'Intern')}">${e.protection_level || 2}</span>
                <span class="aai-entity-type">${esc(e.type)}</span>
                ${esc(e.original)}
                <span class="aai-tool-entity-x">&times;</span>
              </span>
            `).join('')}
            ${state.dismissedEntities.size ? `<span style="font-size:11px;color:var(--text-muted);padding:4px">${state.dismissedEntities.size} entfernt</span>` : ''}
          </div>
          ${r.session_info ? renderVaultInfo(r.session_info, isDE) : ''}
        </div>`;

    case 2: // Anonymized
      return `
        <div class="aai-tool-pane">
          <div class="aai-tool-pane-header" style="color:var(--accent)">
            ${isDE ? 'Nur dieser Text wird an das LLM gesendet' : 'Only this text is sent to the LLM'}
          </div>
          <div class="aai-tool-pane-body aai-tool-text-display">${highlightCodenames(esc(r.anonymized))}</div>
          ${r.entities.length ? `
            <div class="aai-tool-mapping-table">
              <table class="aai-table">
                <thead><tr><th>${isDE ? 'Stufe' : 'Level'}</th><th>Original</th><th></th><th>Codename</th></tr></thead>
                <tbody>
                  ${r.entities.filter(e => !state.dismissedEntities.has(e.original)).map(e => `
                    <tr>
                      <td><span class="aai-plevel aai-plevel-${e.protection_level || 2}">${e.protection_level || 2}</span></td>
                      <td style="color:var(--danger)">${esc(e.original)}</td>
                      <td style="color:var(--text-muted)">→</td>
                      <td style="color:var(--accent);font-family:var(--mono)">${esc(e.codename)}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          ` : ''}
          <div style="padding:12px 16px;display:flex;gap:8px">
            <button class="aai-btn aai-btn--primary" id="tool-send-llm" ${state.isStreaming ? 'disabled' : ''}>
              ${state.isStreaming ? (isDE ? 'KI verarbeitet…' : 'AI processing…') : (isDE ? 'An LLM senden' : 'Send to LLM')}
            </button>
          </div>
        </div>`;

    case 3: // LLM Response
      return `
        <div class="aai-tool-pane">
          <div class="aai-tool-pane-header">${isDE ? 'Antwort der KI' : 'AI response'}</div>
          <div class="aai-tool-pane-body">
            ${state.isStreaming
              ? `<div class="aai-typing"><div class="aai-typing-dot"></div><div class="aai-typing-dot"></div><div class="aai-typing-dot"></div></div>`
              : `<div class="aai-msg-text">${renderMarkdown(state.llmResponse)}</div>`}
          </div>
        </div>`;

    case 4: // Rehydrated
      return `
        <div class="aai-tool-pane">
          <div class="aai-tool-pane-header" style="color:var(--success)">
            ${isDE
              ? 'Fertig — Originaldaten lokal wiederhergestellt'
              : 'Done — original data restored locally'}
          </div>
          <div class="aai-tool-pane-body">
            <div class="aai-msg-text">${renderMarkdown(state.rehydrated)}</div>
          </div>
        </div>`;

    default: return '';
  }
}

function wireEvents() {
  // Examples
  container.querySelectorAll('[data-example]').forEach(btn => {
    btn.onclick = () => {
      const ex = EXAMPLES[btn.dataset.example];
      if (ex) {
        state.inputText = ex.text;
        const textarea = container.querySelector('#tool-text');
        if (textarea) textarea.value = ex.text;
        updateCharCount();
      }
    };
  });

  // Textarea
  const textarea = container.querySelector('#tool-text');
  if (textarea) {
    textarea.oninput = () => { state.inputText = textarea.value; updateCharCount(); };
  }

  // Clear
  container.querySelector('#tool-clear')?.addEventListener('click', () => {
    state = { step: 0, inputText: '', result: null, llmResponse: '', rehydrated: '', isProcessing: false, isStreaming: false, dismissedEntities: new Set() };
    render();
  });

  // Analyze
  container.querySelector('#tool-analyze')?.addEventListener('click', analyze);

  // Steps
  container.querySelectorAll('.aai-tool-step:not(.disabled)').forEach(btn => {
    btn.onclick = () => { state.step = parseInt(btn.dataset.step); updateStepContent(); };
  });

  // Dismiss entities
  container.querySelectorAll('[data-dismiss]').forEach(btn => {
    btn.onclick = () => { state.dismissedEntities.add(btn.dataset.dismiss); updateStepContent(); };
  });

  // Send to LLM
  container.querySelector('#tool-send-llm')?.addEventListener('click', sendToLLM);

  // ---- Click-to-Anonymize (text selection) ----
  setupTextSelection();
}

/* ---- Click-to-Anonymize: floating popup on text selection ---- */

function setupTextSelection() {
  const popup = document.getElementById('text-select-popup');
  if (!popup) return;

  // Listen for mouseup on selectable text areas
  document.addEventListener('mouseup', (e) => {
    const selectable = e.target.closest('.aai-tool-selectable');
    if (!selectable) { popup.hidden = true; return; }

    const selection = window.getSelection();
    const selectedText = selection.toString().trim();

    if (selectedText.length < 2 || selectedText.length > 200) {
      popup.hidden = true;
      return;
    }

    // Position popup near the selection
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    popup.style.position = 'fixed';
    popup.style.left = `${rect.left + rect.width / 2}px`;
    popup.style.top = `${rect.top - 40}px`;
    popup.style.transform = 'translateX(-50%)';
    popup.hidden = false;

    // Wire the "Anonymisieren" button
    const addBtn = popup.querySelector('#btn-add-deny');
    addBtn.onclick = async () => {
      popup.hidden = true;
      try {
        // Add to deny-list via settings API
        const settings = get('settings');
        const denyList = [...(settings.deny_list || [])];
        if (!denyList.includes(selectedText)) {
          denyList.push(selectedText);
          await api.putSettings({ deny_list: denyList });
          settings.deny_list = denyList;
          set('settings', { ...settings });
        }
        toast(`"${selectedText}" → Deny-List hinzugefügt`, 'success');

        // Re-run analysis with updated deny-list
        window.getSelection().removeAllRanges();
        await analyze();
      } catch (err) {
        toast(err.message, 'error');
      }
    };
  });

  // Hide popup on click elsewhere
  document.addEventListener('mousedown', (e) => {
    if (!e.target.closest('.aai-select-popup')) {
      popup.hidden = true;
    }
  });
}

function updateCharCount() {
  const el = container.querySelector('#tool-char-count');
  if (el) el.textContent = `${state.inputText.length} / 5000`;
}

function updateStepContent() {
  const contentEl = container.querySelector('#tool-step-content');
  if (contentEl) contentEl.innerHTML = renderStepContent();

  container.querySelectorAll('.aai-tool-step').forEach((btn, i) => {
    btn.classList.toggle('active', i === state.step);
    btn.classList.toggle('disabled', i > getMaxStep());
  });

  // Re-wire content-specific events
  container.querySelectorAll('[data-dismiss]').forEach(btn => {
    btn.onclick = () => { state.dismissedEntities.add(btn.dataset.dismiss); updateStepContent(); };
  });
  container.querySelector('#tool-send-llm')?.addEventListener('click', sendToLLM);
}

async function analyze() {
  const text = state.inputText.trim();
  if (!text) return;

  state.isProcessing = true;
  state.result = null;
  state.llmResponse = '';
  state.rehydrated = '';
  state.dismissedEntities = new Set();
  render();

  try {
    const result = await api.debugTest(text);
    state.result = result;
    state.isProcessing = false;
    state.step = 1;
    const resultsEl = container.querySelector('#tool-results');
    if (resultsEl) resultsEl.hidden = false;
    render();
  } catch (err) {
    state.isProcessing = false;
    toast(err.message, 'error');
    render();
  }
}

async function sendToLLM() {
  if (state.isStreaming || !state.result) return;

  const provider = get('provider');
  const model = get('model');
  if (!provider || !model) {
    toast('Bitte zuerst einen KI-Anbieter konfigurieren (Einstellungen)', 'error');
    return;
  }

  state.isStreaming = true;
  state.llmResponse = '';
  state.rehydrated = '';
  state.step = 3;
  updateStepContent();

  api.streamMessage(
    { message: state.inputText, provider, model, history: [], system_prompt: '' },
    {
      onMeta() {},
      onToken(content) {
        if (content) {
          state.llmResponse += content;
          if (state.step === 3) {
            const body = container.querySelector('.aai-tool-pane-body');
            if (body) body.innerHTML = `<div class="aai-msg-text">${renderMarkdown(state.llmResponse)}</div>`;
          }
        }
      },
      onDone(data) {
        if (data.full_response) {
          state.rehydrated = data.full_response;
          state.llmResponse = data.full_response;
        }
        state.isStreaming = false;
        state.step = 4;
        render();
      },
      onError(error) {
        state.isStreaming = false;
        toast(error, 'error');
        updateStepContent();
      },
      onComplete() { state.isStreaming = false; },
    }
  );
}

/* ---- Highlighting ---- */

function highlightEntities(text, entities) {
  let html = esc(text);
  const sorted = [...entities]
    .filter(e => !state.dismissedEntities.has(e.original))
    .sort((a, b) => b.original.length - a.original.length);

  for (const e of sorted) {
    const escaped = esc(e.original);
    const typeClass = getTypeColor(e.type);
    html = html.replaceAll(escaped,
      `<mark class="aai-tool-highlight ${typeClass}" data-dismiss="${escAttr(e.original)}" title="Klicken zum Entfernen: ${esc(e.type)}">${escaped}</mark>`
    );
  }
  return html;
}

function highlightCodenames(html) {
  return html.replace(/\[([A-Z_]+_\d+)\]/g, '<span class="aai-anon-highlight">[$1]</span>');
}

function getTypeColor(type) {
  if (type.includes('PERSON')) return 'hl-person';
  if (type.includes('IBAN') || type.includes('CREDIT')) return 'hl-finance';
  if (type.includes('PHONE') || type.includes('EMAIL')) return 'hl-contact';
  if (type.includes('LOCATION') || type.includes('ADDRESS')) return 'hl-location';
  if (type.includes('DATE')) return 'hl-date';
  return 'hl-other';
}

/* ---- Vault Info / TTL Display ---- */

const LEVEL_NAMES_DE = { 1: 'Oeffentlich', 2: 'Intern', 3: 'Vertraulich', 4: 'Streng Vertraulich' };
const LEVEL_NAMES_EN = { 1: 'Public', 2: 'Internal', 3: 'Confidential', 4: 'Restricted' };

function renderVaultInfo(info, isDE) {
  if (!info || !info.levels) return '';
  const names = isDE ? LEVEL_NAMES_DE : LEVEL_NAMES_EN;
  const rows = Object.values(info.levels).map(lv => {
    const remaining = lv.remaining_seconds;
    const mins = Math.floor(remaining / 60);
    const secs = remaining % 60;
    const timeStr = remaining > 0 ? `${mins}:${String(secs).padStart(2, '0')}` : (isDE ? 'Abgelaufen' : 'Expired');
    const cls = lv.expired ? 'aai-vault-expired' : (remaining < 120 ? 'aai-vault-warning' : '');
    return `
      <div class="aai-vault-row ${cls}">
        <span class="aai-plevel aai-plevel-${lv.protection_level}">${lv.protection_level}</span>
        <span class="aai-vault-label">${names[lv.protection_level] || '?'}</span>
        <span class="aai-vault-timer">${timeStr}</span>
      </div>`;
  }).join('');

  return `
    <div class="aai-vault-info">
      <div class="aai-vault-header">${isDE ? 'Vault-Status' : 'Vault Status'}</div>
      ${rows}
    </div>`;
}

function esc(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function escAttr(s) { return String(s || '').replace(/"/g, '&quot;'); }
