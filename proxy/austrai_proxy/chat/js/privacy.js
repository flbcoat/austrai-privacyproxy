/**
 * AUSTR.AI — Privacy Panel (Preact)
 * Right-side panel: anonymization stats, entity list, allow-list actions.
 * Reacts to lastMeta, sessionStats, settings signals.
 */

import { h, render, Fragment } from 'preact';
import { useEffect } from 'preact/hooks';
import htm from 'htm';
import { signals, toast } from './state.js';
import * as api from './api.js';
import { t } from './i18n.js';

const html = htm.bind(h);

const SVG_SHIELD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';

function EntityRow({ entity }) {
  async function handleDismiss() {
    try {
      await api.dismissTerm(entity.codename, false);
      toast(t('dismiss') + ' ✓', 'info');
    } catch (err) { toast(err.message, 'error'); }
  }

  async function handleAllow() {
    try {
      const result = await api.addToAllowList(entity.codename);
      signals.settings.value = { ...signals.settings.value, allow_list: result.allow_list };
      toast(t('allowAdd') + ' ✓', 'success');
    } catch (err) { toast(err.message, 'error'); }
  }

  const level = entity.protection_level || 2;

  return html`
    <div class="aai-entity-item">
      <span class=${`aai-plevel aai-plevel-${level}`}>${level}</span>
      <span class="aai-entity-type">${entity.type || 'ENTITY'}</span>
      <span class="aai-entity-code">${entity.codename || ''}</span>
      <button class="aai-entity-action" onClick=${handleDismiss}>${t('dismiss')}</button>
      <button class="aai-entity-action" onClick=${handleAllow}>${t('allowAdd')}</button>
    </div>
  `;
}

function PrivacyPanel() {
  const meta = signals.lastMeta.value;
  const stats = signals.sessionStats.value;
  const settings = signals.settings.value;
  const mappings = meta?.mappings_preview || [];
  const allowList = settings.allow_list || [];

  // anonymized/restored labels: strip the trailing "{n}" placeholder from i18n templates
  const labelAnon = t('privacyBadge', { n: '' }).replace(/\s*$/, '');
  const labelRestored = t('privacyRestored', { n: '' }).replace(/\s*$/, '');

  return html`
    <${Fragment}>
      <div class="aai-panel-header">
        <h3><span dangerouslySetInnerHTML=${{ __html: SVG_SHIELD }} /> ${t('privacyPanel')}</h3>
        <button class="aai-btn aai-btn--ghost aai-btn--icon" onClick=${() => signals.privacyPanelOpen.value = false}>×</button>
      </div>

      <div class="aai-stat-grid">
        <div class="aai-stat-card">
          <div class="aai-stat-value">${stats.anonymized}</div>
          <div class="aai-stat-label">${labelAnon}</div>
        </div>
        <div class="aai-stat-card">
          <div class="aai-stat-value">${stats.restored}</div>
          <div class="aai-stat-label">${labelRestored}</div>
        </div>
      </div>

      ${mappings.length ? html`
        <div class="aai-entity-list">
          <h4>${t('entitiesDetected')}</h4>
          ${mappings.map((m, i) => html`<${EntityRow} key=${m.codename || i} entity=${m} />`)}
        </div>
      ` : null}

      ${allowList.length ? html`
        <div class="aai-entity-list">
          <h4>${t('allowTitle')}</h4>
          ${allowList.map((term) => html`
            <div key=${term} class="aai-entity-item">
              <span class="aai-entity-code" style="flex:1">${term}</span>
            </div>
          `)}
        </div>
      ` : null}
    <//>
  `;
}

/* ---- Init ---- */

export function init() {
  const panel = document.getElementById('privacy-panel');
  const counterEl = document.getElementById('privacy-counter');
  const toggleBtn = document.getElementById('btn-privacy-panel');
  if (!panel || !counterEl || !toggleBtn) return;

  // Panel visibility — reactively toggle the `hidden` attribute on the
  // static <aside id="privacy-panel">. The element itself stays outside
  // of Preact's render tree; only its contents are managed by Preact.
  const unsubVisible = signals.privacyPanelOpen.subscribe((isOpen) => {
    panel.hidden = !isOpen;
  });

  // Header counter badge (outside of the panel's render scope)
  const unsubCounter = signals.lastMeta.subscribe((meta) => {
    const count = meta?.anonymized_count || 0;
    counterEl.textContent = String(count);
    counterEl.classList.toggle('visible', count > 0);
  });

  toggleBtn.addEventListener('click', () => {
    signals.privacyPanelOpen.value = !signals.privacyPanelOpen.value;
  });

  render(html`<${PrivacyPanel} />`, panel);

  // Return cleanup for completeness; init() is called once on boot so this
  // unsubscribe will never fire in practice, but it keeps the contract clean
  // for future hot-reload scenarios.
  return () => { unsubVisible(); unsubCounter(); };
}
