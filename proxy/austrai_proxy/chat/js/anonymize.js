/**
 * AUSTR.AI — Anonymization Tool (Preact, 5-Step Pipeline)
 *
 * 5 steps: Original → Erkennung → Anonymisiert → LLM → Re-hydriert
 * - Click-to-anonymize: select text in Original/Detection view → add to deny-list
 * - Click-to-dismiss: click highlighted entity to remove it
 * - Example texts for quick testing
 *
 * The previous Vanilla-JS version registered mouseup/mousedown on document
 * without ever cleaning them up (listener leak). The Preact version does
 * the same registration inside useEffect with a cleanup closure.
 */

import { h, render, Fragment } from 'preact';
import { useState, useEffect, useRef } from 'preact/hooks';
import htm from 'htm';
import { signals, toast } from './state.js';
import * as api from './api.js';
import { getLang } from './i18n.js';
import { renderMarkdown } from './markdown.js';

const html = htm.bind(h);

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

const LEVEL_NAMES_DE = { 1: 'Oeffentlich', 2: 'Intern', 3: 'Vertraulich', 4: 'Streng Vertraulich' };
const LEVEL_NAMES_EN = { 1: 'Public', 2: 'Internal', 3: 'Confidential', 4: 'Restricted' };

/* ---- Helpers ---- */

function esc(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function escAttr(s) { return String(s || '').replace(/"/g, '&quot;'); }

function getTypeColor(type) {
  if (type.includes('PERSON')) return 'hl-person';
  if (type.includes('IBAN') || type.includes('CREDIT')) return 'hl-finance';
  if (type.includes('PHONE') || type.includes('EMAIL')) return 'hl-contact';
  if (type.includes('LOCATION') || type.includes('ADDRESS')) return 'hl-location';
  if (type.includes('DATE')) return 'hl-date';
  return 'hl-other';
}

function highlightEntitiesHtml(text, entities, dismissedSet) {
  // Sort by length desc so longer matches don't get clobbered by shorter ones
  let outHtml = esc(text);
  const active = entities.filter((e) => !dismissedSet.has(e.original))
    .sort((a, b) => b.original.length - a.original.length);
  for (const e of active) {
    const escaped = esc(e.original);
    const typeClass = getTypeColor(e.type);
    outHtml = outHtml.replaceAll(
      escaped,
      `<mark class="aai-tool-highlight ${typeClass}" data-dismiss="${escAttr(e.original)}" title="Klicken zum Entfernen: ${esc(e.type)}">${escaped}</mark>`,
    );
  }
  return outHtml;
}

function highlightCodenamesHtml(htmlText) {
  return htmlText.replace(/\[([A-Z_]+_\d+)\]/g, '<span class="aai-anon-highlight">[$1]</span>');
}

/* ---- Vault TTL info ---- */

function VaultInfo({ info, isDE }) {
  if (!info || !info.levels) return null;
  const names = isDE ? LEVEL_NAMES_DE : LEVEL_NAMES_EN;
  return html`
    <div class="aai-vault-info">
      <div class="aai-vault-header">${isDE ? 'Vault-Status' : 'Vault Status'}</div>
      ${Object.values(info.levels).map((lv, i) => {
        const remaining = lv.remaining_seconds;
        const mins = Math.floor(remaining / 60);
        const secs = remaining % 60;
        const timeStr = remaining > 0 ? `${mins}:${String(secs).padStart(2, '0')}` : (isDE ? 'Abgelaufen' : 'Expired');
        const cls = lv.expired ? 'aai-vault-expired' : (remaining < 120 ? 'aai-vault-warning' : '');
        return html`
          <div key=${i} class=${`aai-vault-row ${cls}`}>
            <span class=${`aai-plevel aai-plevel-${lv.protection_level}`}>${lv.protection_level}</span>
            <span class="aai-vault-label">${names[lv.protection_level] || '?'}</span>
            <span class="aai-vault-timer">${timeStr}</span>
          </div>
        `;
      })}
    </div>
  `;
}

/* ---- Step panes ---- */

function OriginalPane({ result, isDE }) {
  return html`
    <div class="aai-tool-pane">
      <div
        class="aai-tool-pane-header"
        dangerouslySetInnerHTML=${{ __html: isDE
          ? 'Originaltext — <strong>markiere einen Begriff</strong> um ihn zur Deny-List hinzuzufügen'
          : 'Original text — <strong>select a term</strong> to add it to the deny list' }}
      />
      <div class="aai-tool-pane-body aai-tool-text-display aai-tool-selectable">${result.original}</div>
    </div>
  `;
}

function DetectionPane({ result, dismissed, onDismiss, isDE }) {
  const remaining = result.entity_count - dismissed.size;
  const activeEntities = result.entities.filter((e) => !dismissed.has(e.original));

  const headerText = isDE
    ? `${remaining} Entität(en) erkannt — klicke auf eine Markierung um sie zu entfernen`
    : `${remaining} entity/entities detected — click a highlight to remove it`;

  function handlePaneClick(e) {
    const markEl = e.target.closest('mark[data-dismiss]');
    if (markEl) onDismiss(markEl.dataset.dismiss);
  }

  return html`
    <div class="aai-tool-pane">
      <div class="aai-tool-pane-header">
        ${headerText}
        ${result.doc_type && result.doc_type !== 'general' ? html`
          <span class=${`aai-doc-type-badge aai-doc-type-${result.doc_type}`}>
            ${result.doc_type === 'medical' ? (isDE ? 'Medizinisch' : 'Medical') : (isDE ? 'Rechtlich' : 'Legal')}
          </span>
        ` : null}
      </div>
      <div
        class="aai-tool-pane-body aai-tool-text-display aai-tool-selectable"
        onClick=${handlePaneClick}
        dangerouslySetInnerHTML=${{ __html: highlightEntitiesHtml(result.original, result.entities, dismissed) }}
      />
      <div class="aai-tool-entity-legend">
        ${activeEntities.map((e, i) => html`
          <span key=${i} class="aai-tool-entity-tag" onClick=${() => onDismiss(e.original)}>
            <span class=${`aai-plevel aai-plevel-${e.protection_level || 2}`} title=${e.protection_label || 'Intern'}>${e.protection_level || 2}</span>
            <span class="aai-entity-type">${e.type}</span>
            ${e.original}
            <span class="aai-tool-entity-x">×</span>
          </span>
        `)}
        ${dismissed.size ? html`
          <span style="font-size:11px;color:var(--text-muted);padding:4px">${dismissed.size} entfernt</span>
        ` : null}
      </div>
      ${result.session_info ? html`<${VaultInfo} info=${result.session_info} isDE=${isDE} />` : null}
    </div>
  `;
}

function AnonymizedPane({ result, dismissed, onSendToLLM, isStreaming, isDE }) {
  const activeEntities = result.entities.filter((e) => !dismissed.has(e.original));

  return html`
    <div class="aai-tool-pane">
      <div class="aai-tool-pane-header" style="color:var(--accent)">
        ${isDE ? 'Nur dieser Text wird an das LLM gesendet' : 'Only this text is sent to the LLM'}
      </div>
      <div
        class="aai-tool-pane-body aai-tool-text-display"
        dangerouslySetInnerHTML=${{ __html: highlightCodenamesHtml(esc(result.anonymized)) }}
      />
      ${activeEntities.length ? html`
        <div class="aai-tool-mapping-table">
          <table class="aai-table">
            <thead>
              <tr>
                <th>${isDE ? 'Stufe' : 'Level'}</th>
                <th>Original</th>
                <th></th>
                <th>Codename</th>
              </tr>
            </thead>
            <tbody>
              ${activeEntities.map((e, i) => html`
                <tr key=${i}>
                  <td><span class=${`aai-plevel aai-plevel-${e.protection_level || 2}`}>${e.protection_level || 2}</span></td>
                  <td style="color:var(--danger)">${e.original}</td>
                  <td style="color:var(--text-muted)">→</td>
                  <td style="color:var(--accent);font-family:var(--mono)">${e.codename}</td>
                </tr>
              `)}
            </tbody>
          </table>
        </div>
      ` : null}
      <div style="padding:12px 16px;display:flex;gap:8px">
        <button class="aai-btn aai-btn--primary" onClick=${onSendToLLM} disabled=${isStreaming}>
          ${isStreaming ? (isDE ? 'KI verarbeitet…' : 'AI processing…') : (isDE ? 'An LLM senden' : 'Send to LLM')}
        </button>
      </div>
    </div>
  `;
}

function LlmPane({ response, isStreaming, isDE }) {
  return html`
    <div class="aai-tool-pane">
      <div class="aai-tool-pane-header">${isDE ? 'Antwort der KI' : 'AI response'}</div>
      <div class="aai-tool-pane-body">
        ${isStreaming && !response ? html`
          <div class="aai-typing">
            <div class="aai-typing-dot"></div>
            <div class="aai-typing-dot"></div>
            <div class="aai-typing-dot"></div>
          </div>
        ` : html`
          <div class="aai-msg-text" dangerouslySetInnerHTML=${{ __html: renderMarkdown(response) }} />
        `}
      </div>
    </div>
  `;
}

function RehydratedPane({ text, isDE }) {
  return html`
    <div class="aai-tool-pane">
      <div class="aai-tool-pane-header" style="color:var(--success)">
        ${isDE ? 'Fertig — Originaldaten lokal wiederhergestellt' : 'Done — original data restored locally'}
      </div>
      <div class="aai-tool-pane-body">
        <div class="aai-msg-text" dangerouslySetInnerHTML=${{ __html: renderMarkdown(text) }} />
      </div>
    </div>
  `;
}

/* ---- Text-selection floating popup ---- */

function SelectionPopup({ onAnonymize }) {
  const [visible, setVisible] = useState(false);
  const [pos, setPos] = useState({ left: 0, top: 0 });
  const [selectedText, setSelectedText] = useState('');

  useEffect(() => {
    function onMouseUp(e) {
      const selectable = e.target.closest('.aai-tool-selectable');
      if (!selectable) { setVisible(false); return; }

      const selection = window.getSelection();
      const text = selection.toString().trim();

      if (text.length < 2 || text.length > 200) { setVisible(false); return; }

      const range = selection.getRangeAt(0);
      const rect = range.getBoundingClientRect();
      setPos({
        left: rect.left + rect.width / 2,
        top: rect.top - 40,
      });
      setSelectedText(text);
      setVisible(true);
    }

    function onMouseDown(e) {
      if (!e.target.closest('.aai-select-popup')) {
        setVisible(false);
      }
    }

    document.addEventListener('mouseup', onMouseUp);
    document.addEventListener('mousedown', onMouseDown);
    return () => {
      document.removeEventListener('mouseup', onMouseUp);
      document.removeEventListener('mousedown', onMouseDown);
    };
  }, []);

  async function handleClick() {
    const text = selectedText;
    setVisible(false);
    window.getSelection().removeAllRanges();
    onAnonymize(text);
  }

  if (!visible) return null;

  return html`
    <div
      class="aai-select-popup"
      style=${`position:fixed;left:${pos.left}px;top:${pos.top}px;transform:translateX(-50%);z-index:9999`}
    >
      <button class="aai-btn aai-btn--primary aai-btn--sm" onClick=${handleClick}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
        Anonymisieren
      </button>
    </div>
  `;
}

/* ---- Main View ---- */

function AnonymizeView() {
  const [step, setStep] = useState(0);
  const [inputText, setInputText] = useState('');
  const [result, setResult] = useState(null);
  const [llmResponse, setLlmResponse] = useState('');
  const [rehydrated, setRehydrated] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [dismissed, setDismissed] = useState(new Set());

  // Mutable ref for the streaming callbacks — they need to read/write latest
  // state without stale closures.
  const stateRef = useRef({});
  stateRef.current = { step, inputText, llmResponse, rehydrated };

  const isDE = getLang() === 'de';

  function getMaxStep() {
    if (rehydrated) return 4;
    if (llmResponse) return 3;
    if (result) return 2;
    return 0;
  }

  function handleExample(key) {
    const ex = EXAMPLES[key];
    if (ex) setInputText(ex.text);
  }

  function handleClear() {
    setStep(0);
    setInputText('');
    setResult(null);
    setLlmResponse('');
    setRehydrated('');
    setIsProcessing(false);
    setIsStreaming(false);
    setDismissed(new Set());
  }

  function handleDismiss(term) {
    const next = new Set(dismissed);
    next.add(term);
    setDismissed(next);
  }

  async function runAnalysis(overrideText) {
    const text = (overrideText ?? inputText).trim();
    if (!text) return;

    setIsProcessing(true);
    setResult(null);
    setLlmResponse('');
    setRehydrated('');
    setDismissed(new Set());

    try {
      const r = await api.debugTest(text);
      setResult(r);
      setStep(1);
    } catch (err) {
      toast(err.message, 'error');
    }
    setIsProcessing(false);
  }

  async function handleAnonymizeSelection(selectedText) {
    try {
      const settings = signals.settings.value;
      const denyList = [...(settings.deny_list || [])];
      if (!denyList.includes(selectedText)) {
        denyList.push(selectedText);
        await api.putSettings({ deny_list: denyList });
        signals.settings.value = { ...settings, deny_list: denyList };
      }
      toast(`"${selectedText}" → Deny-List hinzugefügt`, 'success');
      await runAnalysis();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  function sendToLLM() {
    if (isStreaming || !result) return;

    const provider = signals.provider.value;
    const model = signals.model.value;
    if (!provider || !model) {
      toast('Bitte zuerst einen KI-Anbieter konfigurieren (Einstellungen)', 'error');
      return;
    }

    setIsStreaming(true);
    setLlmResponse('');
    setRehydrated('');
    setStep(3);

    let accumulated = '';
    api.streamMessage(
      { message: inputText, provider, model, history: [], system_prompt: '' },
      {
        onMeta() {},
        onToken(content) {
          if (content) {
            accumulated += content;
            setLlmResponse(accumulated);
          }
        },
        onDone(data) {
          if (data.full_response) {
            setRehydrated(data.full_response);
            setLlmResponse(data.full_response);
          }
          setIsStreaming(false);
          setStep(4);
        },
        onError(err) {
          setIsStreaming(false);
          toast(err, 'error');
        },
        onComplete() { setIsStreaming(false); },
      },
    );
  }

  const maxStep = getMaxStep();

  return html`
    <${Fragment}>
      <div class="aai-tool">
        <div class="aai-tool-input-section">
          <div class="aai-tool-header">
            <h2>${isDE ? 'Anonymisierungs-Werkzeug' : 'Anonymization Tool'}</h2>
            <p>${isDE ? 'Text einfügen, Anonymisierung prüfen, optional an LLM senden.' : 'Paste text, check anonymization, optionally send to LLM.'}</p>
          </div>

          <div class="aai-tool-examples">
            ${Object.entries(EXAMPLES).map(([key, ex]) => html`
              <button key=${key} class="aai-chip" onClick=${() => handleExample(key)}>${ex.de}</button>
            `)}
          </div>

          <div class="aai-tool-textarea-wrap">
            <textarea
              class="aai-input aai-tool-textarea"
              rows="6"
              placeholder=${isDE ? 'Text mit personenbezogenen Daten eingeben…' : 'Enter text with personal data…'}
              value=${inputText}
              onInput=${(e) => setInputText(e.target.value)}
            ></textarea>
            <div class="aai-tool-textarea-footer">
              <span class="aai-tool-char-count">${inputText.length} / 5000</span>
              <div class="aai-tool-textarea-actions">
                <button class="aai-btn aai-btn--ghost aai-btn--sm" onClick=${handleClear}>${isDE ? 'Leeren' : 'Clear'}</button>
                <button class="aai-btn aai-btn--primary" onClick=${() => runAnalysis()} disabled=${isProcessing}>
                  ${isProcessing ? (isDE ? 'Wird analysiert…' : 'Analyzing…') : (isDE ? 'Analyse starten' : 'Start Analysis')}
                </button>
              </div>
            </div>
          </div>
        </div>

        <div class="aai-tool-results" hidden=${!result}>
          <div class="aai-tool-steps">
            ${STEPS.map((s, i) => html`
              <button
                key=${s.id}
                class=${`aai-tool-step${i === step ? ' active' : ''}${i > maxStep ? ' disabled' : ''}`}
                onClick=${() => { if (i <= maxStep) setStep(i); }}
              >
                <span class="aai-tool-step-num">${i + 1}</span>
                <span class="aai-tool-step-label">${isDE ? s.de : s.en}</span>
              </button>
            `)}
          </div>
          <div class="aai-tool-step-content">
            ${result && step === 0 ? html`<${OriginalPane} result=${result} isDE=${isDE} />` : null}
            ${result && step === 1 ? html`<${DetectionPane} result=${result} dismissed=${dismissed} onDismiss=${handleDismiss} isDE=${isDE} />` : null}
            ${result && step === 2 ? html`<${AnonymizedPane} result=${result} dismissed=${dismissed} onSendToLLM=${sendToLLM} isStreaming=${isStreaming} isDE=${isDE} />` : null}
            ${step === 3 ? html`<${LlmPane} response=${llmResponse} isStreaming=${isStreaming} isDE=${isDE} />` : null}
            ${step === 4 ? html`<${RehydratedPane} text=${rehydrated} isDE=${isDE} />` : null}
          </div>
        </div>
      </div>

      <${SelectionPopup} onAnonymize=${handleAnonymizeSelection} />
    <//>
  `;
}

/* ---- Exports ---- */

let container;

export function init() {
  container = document.getElementById('tool-view');
  if (!container) return;
  render(html`<${AnonymizeView} />`, container);
}
