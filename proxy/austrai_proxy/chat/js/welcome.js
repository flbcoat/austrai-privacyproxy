/**
 * AUSTR.AI — Welcome Screen (Preact)
 * Hero, tool cards, suggestion chips.
 * "Text anonymisieren" → switches to Werkzeuge view.
 * "Dokument anonymisieren" → opens file picker.
 */

import { h, render } from 'preact';
import htm from 'htm';
import { signals } from './state.js';
import { t } from './i18n.js';

const html = htm.bind(h);

// Static SVGs — rendered as trusted HTML (no user input involved)
const SVG_SHIELD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';
const SVG_DOC = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>';
const SVG_IMG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>';
const SVG_TEXT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V5a2 2 0 00-2-2z"/><line x1="9" y1="7" x2="15" y2="7"/><line x1="9" y1="11" x2="15" y2="11"/><line x1="9" y1="15" x2="12" y2="15"/></svg>';
const SVG_EXCEL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/></svg>';

function Svg({ src }) {
  return html`<span dangerouslySetInnerHTML=${{ __html: src }} />`;
}

function handleToolClick(tool) {
  if (tool === 'text-anon') {
    // Simulate clicking the "Werkzeuge" sidebar nav button
    const toolBtn = document.querySelector('.aai-sidebar-nav-btn[data-mode="tools"]');
    if (toolBtn) toolBtn.click();
    return;
  }

  const fileInput = document.getElementById('file-input');
  if (tool === 'excel') {
    fileInput.accept = '.xlsx,.csv,.xls';
    fileInput.dataset.mode = 'attach';
  } else if (tool === 'redact') {
    fileInput.accept = '.png,.jpg,.jpeg,.tiff,.bmp,.webp,.pdf';
    fileInput.dataset.mode = tool;
  } else {
    fileInput.accept = '.pdf,.docx,.xlsx,.txt,.csv,.png,.jpg,.jpeg,.mp3,.wav,.m4a';
    fileInput.dataset.mode = tool;
  }
  fileInput.click();
}

function handleChipClick(text) {
  const msgInput = document.getElementById('msg-input');
  if (!msgInput) return;
  msgInput.value = text;
  msgInput.focus();
  msgInput.dispatchEvent(
    new CustomEvent('chip-submit', { detail: text, bubbles: true })
  );
}

function WelcomeView() {
  const isDE = signals.language.value === 'de';

  return html`
    <div class="aai-welcome">
      <div class="aai-welcome-hero">
        <div class="aai-welcome-shield"><${Svg} src=${SVG_SHIELD} /></div>
        <h1>${t('welcomeTitle')}</h1>
        <p>${t('welcomeSub')}</p>
      </div>

      <div class="aai-welcome-tools" style="grid-template-columns: repeat(2, 1fr)">
        <div class="aai-tool-card" onClick=${() => handleToolClick('text-anon')}>
          <div class="aai-tool-card-icon aai-tool-card-icon--text"><${Svg} src=${SVG_TEXT} /></div>
          <h3>${isDE ? 'Text anonymisieren' : 'Anonymize Text'}</h3>
          <p>${isDE ? 'Text einfügen und Schritt für Schritt anonymisieren' : 'Paste text and anonymize step by step'}</p>
        </div>
        <div class="aai-tool-card" onClick=${() => handleToolClick('excel')}>
          <div class="aai-tool-card-icon" style="background:rgba(217,119,6,0.08);color:#D97706">
            <${Svg} src=${SVG_EXCEL} />
          </div>
          <h3>${isDE ? 'Excel analysieren' : 'Analyze Excel'}</h3>
          <p>${isDE ? 'Tabellen hochladen — alle Begriffe werden anonymisiert, Zahlen bleiben erhalten' : 'Upload spreadsheets — all terms anonymized, numbers preserved'}</p>
        </div>
        <div class="aai-tool-card" onClick=${() => handleToolClick('anonymize')}>
          <div class="aai-tool-card-icon aai-tool-card-icon--doc"><${Svg} src=${SVG_DOC} /></div>
          <h3>${t('toolAnonymize')}</h3>
          <p>${t('toolAnonymizeDesc')}</p>
        </div>
        <div class="aai-tool-card" onClick=${() => handleToolClick('redact')}>
          <div class="aai-tool-card-icon aai-tool-card-icon--img"><${Svg} src=${SVG_IMG} /></div>
          <h3>${t('toolRedact')}</h3>
          <p>${t('toolRedactDesc')}</p>
        </div>
      </div>

      <div class="aai-welcome-chips">
        <button class="aai-chip" onClick=${() => handleChipClick(t('chipExplain'))}>${t('chipExplain')}</button>
        <button class="aai-chip" onClick=${() => handleChipClick(t('chipAnalyze'))}>${t('chipAnalyze')}</button>
        <button class="aai-chip" onClick=${() => handleChipClick(t('chipPrivacy'))}>${t('chipPrivacy')}</button>
      </div>
    </div>
  `;
}

export function init() {
  const container = document.getElementById('welcome-view');
  if (!container) return;
  render(html`<${WelcomeView} />`, container);
}
