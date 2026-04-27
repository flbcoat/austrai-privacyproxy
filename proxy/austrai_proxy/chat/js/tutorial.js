/**
 * AUSTR.AI — Help & Tutorial Page (Preact)
 *
 * Zwei Abschnitte, beide als Accordion:
 *   1. Tutorial — die wichtigsten Funktionen Schritt für Schritt erklärt,
 *      inkl. Live-Demo, die den lokalen /debug/test Endpoint aufruft.
 *   2. FAQ — häufige Fragen zu Privatsphäre, Erkennung, Lizenz, Providern.
 *
 * Alle Strings kommen aus i18n.js und reagieren reaktiv auf Sprachwechsel
 * (die Komponente liest signals.language.value, d.h. Preact-Signals re-rendern
 * die gesamte View bei einem setLang()-Aufruf automatisch).
 */

import { h, render, Fragment } from 'preact';
import { useState } from 'preact/hooks';
import htm from 'htm';
import { signals } from './state.js';
import * as api from './api.js';
import { t } from './i18n.js';

const html = htm.bind(h);

const TUTORIAL_HELP_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';

function highlightAnon(text) {
  return String(text || '').replace(
    /\[([A-Z_]+_\d+)\]/g,
    '<span style="background:var(--accent-subtle);color:var(--accent);padding:1px 4px;border-radius:3px;font-family:var(--mono);font-size:12px">[$1]</span>',
  );
}

/* ---- Accordion step ---- */

function Step({ num, title, open, onToggle, children }) {
  // Keyboard-Support: Enter/Space togglen genauso wie Mausklick. Ohne das
  // waren die Accordion-Header nicht keyboard-erreichbar.
  function onHeaderKey(e) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onToggle();
    }
  }
  return html`
    <div class=${`aai-tutorial-step${open ? ' open' : ''}`}>
      <div
        class="aai-tutorial-step-header"
        role="button"
        tabIndex="0"
        aria-expanded=${open ? 'true' : 'false'}
        onClick=${onToggle}
        onKeyDown=${onHeaderKey}
      >
        ${num ? html`<span class="aai-tutorial-step-num">${num}</span>` : null}
        <span class="aai-tutorial-step-title">${title}</span>
        <span class="aai-tutorial-step-arrow" aria-hidden="true">▼</span>
      </div>
      <div class="aai-tutorial-step-body">${children}</div>
    </div>
  `;
}

/* ---- Live demo result ---- */

function DemoResult({ result }) {
  if (!result.is_changed) {
    return html`
      <div class="aai-tut-result-box" style="border-color:var(--success)">
        <strong style="color:var(--success)">✓ ${t('tutDemoNone')}</strong>
        <p style="font-size:13px;color:var(--text-muted);margin-top:4px">${t('tutDemoNoneHint')}</p>
      </div>
    `;
  }

  return html`
    <div class="aai-tut-result-box">
      <strong style="color:var(--accent)">🛡 ${t('tutDemoAnonymized', { n: result.entity_count })}</strong>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0">
        <div>
          <div style="font-size:10px;font-weight:600;text-transform:uppercase;color:var(--text-muted);margin-bottom:4px">${t('tutDemoOrig')}</div>
          <div class="aai-tut-text-box">${result.original}</div>
        </div>
        <div>
          <div style="font-size:10px;font-weight:600;text-transform:uppercase;color:var(--accent);margin-bottom:4px">${t('tutDemoSeen')}</div>
          <div
            class="aai-tut-text-box"
            style="border-color:var(--accent-border)"
            dangerouslySetInnerHTML=${{ __html: highlightAnon(result.anonymized) }}
          />
        </div>
      </div>

      <div style="font-size:10px;font-weight:600;text-transform:uppercase;color:var(--text-muted);margin-bottom:6px">${t('tutDemoReplacements')}</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px">
        ${result.entities.map((e, i) => html`
          <span key=${i} style="display:inline-flex;align-items:center;gap:4px;background:var(--bg-sidebar);border-radius:var(--r-full);padding:3px 10px;font-size:12px">
            <span style="font-size:9px;font-weight:600;text-transform:uppercase;background:var(--accent-subtle);color:var(--accent);padding:1px 5px;border-radius:3px">${e.type}</span>
            <span style="color:var(--danger);text-decoration:line-through">${e.original}</span>
            ${' → '}
            <span style="color:var(--accent);font-family:var(--mono);font-size:11px">${e.codename}</span>
          </span>
        `)}
      </div>
    </div>
  `;
}

function LiveDemo() {
  const [demoText, setDemoText] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function runDemo() {
    const trimmed = demoText.trim();
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

  return html`
    <${Fragment}>
      <p style="margin-bottom:10px">${t('tutDemoIntro')}</p>
      <div style="display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap">
        <button class="aai-chip aai-tut-example" onClick=${() => setDemoText(t('tutDemoExampleText'))}>${t('tutDemoExampleBtn')}</button>
      </div>
      <textarea
        class="aai-input"
        rows="3"
        placeholder=${t('tutDemoPlaceholder')}
        style="font-size:14px;line-height:1.6;resize:vertical;margin-bottom:8px"
        value=${demoText}
        onInput=${(e) => setDemoText(e.target.value)}
      ></textarea>
      <button class="aai-btn aai-btn--primary aai-btn--sm" onClick=${runDemo} disabled=${loading}>
        ${loading ? t('tutDemoLoading') : t('tutDemoButton')}
      </button>
      <div style="margin-top:12px">
        ${error ? html`<p style="color:var(--danger);font-size:13px">${error}</p>` : null}
        ${result ? html`<${DemoResult} result=${result} />` : null}
      </div>
    <//>
  `;
}

/* ---- FAQ ---- */

const FAQ_KEYS = [
  ['faqQ1', 'faqA1'],
  ['faqQ2', 'faqA2'],
  ['faqQ3', 'faqA3'],
  ['faqQ4', 'faqA4'],
  ['faqQ5', 'faqA5'],
  ['faqQ6', 'faqA6'],
  ['faqQ7', 'faqA7'],
  ['faqQ8', 'faqA8'],
  ['faqQ9', 'faqA9'],
  ['faqQ10', 'faqA10'],
];

function FaqSection() {
  const [openFaq, setOpenFaq] = useState(-1);
  return html`
    <${Fragment}>
      ${FAQ_KEYS.map(([qKey, aKey], i) => html`
        <${Step}
          key=${qKey}
          num=${null}
          title=${t(qKey)}
          open=${openFaq === i}
          onToggle=${() => setOpenFaq(openFaq === i ? -1 : i)}
        >
          <p style="font-size:14px;line-height:1.65">${t(aKey)}</p>
        <//>
      `)}
    <//>
  `;
}

/* ---- Tutorial View ---- */

function TutorialView({ onBack }) {
  // Subscribe reaktiv auf language-Wechsel — so rendert alles neu wenn
  // der User in den Einstellungen DE↔EN umschaltet.
  const lang = signals.language.value; // eslint-disable-line no-unused-vars

  const [openStep, setOpenStep] = useState(0);
  const toggle = (i) => setOpenStep(openStep === i ? -1 : i);

  return html`
    <div class="aai-tutorial">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
        <h2>${t('tutTitle')}</h2>
        <button class="aai-btn aai-btn--ghost aai-btn--sm" onClick=${onBack}>${t('tutBack')}</button>
      </div>
      <p>${t('tutIntro')}</p>

      <${Step} num="1" title=${t('tutSectionHow')} open=${openStep === 0} onToggle=${() => toggle(0)}>
        <div class="aai-tutorial-visual" style="padding:20px;text-align:center">
          <div style="display:flex;align-items:center;justify-content:center;gap:8px;flex-wrap:wrap;margin-bottom:16px">
            <div class="aai-tut-box aai-tut-box--danger">Dr. Müller<br/>IBAN AT48 2011…</div>
            <div class="aai-tut-arrow">→</div>
            <div class="aai-tut-box aai-tut-box--accent">[PERSON_1]<br/>[AT_IBAN_1]</div>
            <div class="aai-tut-arrow">→ AI →</div>
            <div class="aai-tut-box aai-tut-box--success">Dr. Müller<br/>IBAN AT48 2011…</div>
          </div>
          <p style="color:var(--text-muted);font-size:13px">${t('tutHowFlow')}</p>
        </div>
        <p style="font-size:14px;line-height:1.65;margin-top:10px">${t('tutHowBody1')}</p>
        <p style="font-size:14px;line-height:1.65;margin-top:8px">${t('tutHowBody2')}</p>
      <//>

      <${Step} num="2" title=${t('tutSectionChat')} open=${openStep === 1} onToggle=${() => toggle(1)}>
        <p style="font-size:14px;line-height:1.65">${t('tutChatBody')}</p>
        <p style="font-size:14px;line-height:1.65;margin-top:8px">💡 ${t('tutChatPreview')}</p>
        <p style="font-size:14px;line-height:1.65;margin-top:8px">✏️ ${t('tutChatRename')}</p>
      <//>

      <${Step} num="3" title=${t('tutSectionAttach')} open=${openStep === 2} onToggle=${() => toggle(2)}>
        <p style="font-size:14px;line-height:1.65">${t('tutAttachBody')}</p>
        <ul style="font-size:14px;line-height:1.7;padding-left:20px;margin-top:8px">
          <li><strong>📎</strong> ${t('tutAttachOpt1')}</li>
          <li style="margin-top:6px"><strong>🔒</strong> ${t('tutAttachOpt2')}</li>
        </ul>
        <p style="font-size:14px;line-height:1.65;margin-top:10px;color:var(--text-muted)">${t('tutAttachDrag')}</p>
      <//>

      <${Step} num="4" title=${t('tutSectionRedact')} open=${openStep === 3} onToggle=${() => toggle(3)}>
        <p style="font-size:14px;line-height:1.65">${t('tutRedactBody')}</p>
        <ul style="font-size:14px;line-height:1.7;padding-left:20px;margin-top:8px">
          <li>${t('tutRedactPath1')}</li>
          <li style="margin-top:6px">${t('tutRedactPath2')}</li>
        </ul>
        <p style="font-size:13px;margin-top:10px;color:var(--text-muted)">${t('tutRedactFormats')}</p>
      <//>

      <${Step} num="5" title=${t('tutSectionToolsTab')} open=${openStep === 4} onToggle=${() => toggle(4)}>
        <p style="font-size:14px;line-height:1.65">${t('tutToolsTabBody')}</p>
        <ul style="font-size:14px;line-height:1.7;padding-left:20px;margin-top:8px">
          <li>${t('tutToolsCard1')}</li>
          <li>${t('tutToolsCard2')}</li>
          <li>${t('tutToolsCard3')}</li>
          <li>${t('tutToolsCard4')}</li>
        </ul>
        <p style="font-size:14px;line-height:1.65;margin-top:10px;color:var(--text-muted)">${t('tutToolsTabNote')}</p>
      <//>

      <${Step} num="6" title=${t('tutSectionSettings')} open=${openStep === 5} onToggle=${() => toggle(5)}>
        <p style="font-size:14px;line-height:1.65">${t('tutSettingsBody')}</p>
        <ul style="font-size:14px;line-height:1.7;padding-left:20px;margin-top:8px">
          <li>${t('tutSettingsProvider')}</li>
          <li style="margin-top:6px">${t('tutSettingsAllow')}</li>
          <li style="margin-top:6px">${t('tutSettingsDeny')}</li>
          <li style="margin-top:6px">${t('tutSettingsThreshold')}</li>
          <li style="margin-top:6px">${t('tutSettingsLang')}</li>
        </ul>
      <//>

      <${Step} num="7" title=${t('tutSectionDemo')} open=${openStep === 6} onToggle=${() => toggle(6)}>
        <${LiveDemo} />
      <//>

      <h3 style="margin-top:32px;margin-bottom:8px">${t('tutSectionFaq')}</h3>
      <${FaqSection} />
    </div>
  `;
}

/* ---- Navigation helpers ---- */

function goBack() {
  const mode = document.querySelector('.aai-sidebar-nav-btn.active')?.dataset.mode;
  if (mode === 'tools') {
    if (window.__aai_showView) window.__aai_showView('tool-view');
  } else {
    const viewId = signals.currentConversationId.value ? 'chat-view' : 'welcome-view';
    if (window.__aai_showView) window.__aai_showView(viewId);
  }
}

/* ---- Exports ---- */

let container;

export function init() {
  container = document.getElementById('tutorial-view');
  if (!container) return;

  // Inject a "Help & Tutorial" button into the sidebar footer. The label is
  // set reactively below (subscribe to signals.language) so it switches
  // languages without a reload.
  const footer = document.querySelector('.aai-sidebar-footer');
  if (footer && !document.getElementById('btn-tutorial')) {
    const btn = document.createElement('button');
    btn.id = 'btn-tutorial';
    btn.className = 'aai-btn aai-btn--ghost';
    btn.style.cssText = 'width:100%;justify-content:flex-start';
    const updateLabel = () => {
      btn.innerHTML = `${TUTORIAL_HELP_ICON}<span>${t('helpTutorial')}</span>`;
    };
    updateLabel();
    signals.language.subscribe(updateLabel);
    btn.addEventListener('click', show);
    footer.insertBefore(btn, footer.firstChild);
  }
}

export function show() {
  if (!container) return;
  if (window.__aai_showView) window.__aai_showView('tutorial-view');
  render(html`<${TutorialView} onBack=${goBack} />`, container);
}
