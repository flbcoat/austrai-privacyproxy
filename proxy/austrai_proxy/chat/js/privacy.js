/**
 * AUSTR.AI — Privacy Panel (Right Side)
 * Shows anonymization stats, entity list, allow-list actions.
 */

import { get, set, on, toast } from './state.js';
import * as api from './api.js';
import { t } from './i18n.js';

const SVG_SHIELD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';

let panel, counterEl;

export function init() {
  panel = document.getElementById('privacy-panel');
  counterEl = document.getElementById('privacy-counter');

  document.getElementById('btn-privacy-panel').addEventListener('click', toggle);

  on('privacyPanelOpen', (isOpen) => {
    panel.hidden = !isOpen;
  });

  on('lastMeta', updateCounter);
  on('sessionStats', render);
  on('lastMeta', render);

  render();
}

function toggle() {
  set('privacyPanelOpen', !get('privacyPanelOpen'));
}

function updateCounter() {
  const meta = get('lastMeta');
  const count = meta?.anonymized_count || 0;
  counterEl.textContent = count;
  counterEl.classList.toggle('visible', count > 0);
}

function render() {
  const meta = get('lastMeta');
  const stats = get('sessionStats');
  const settings = get('settings');
  const mappings = meta?.mappings_preview || [];

  panel.innerHTML = `
    <div class="aai-panel-header">
      <h3>${SVG_SHIELD} ${t('privacyPanel')}</h3>
      <button class="aai-btn aai-btn--ghost aai-btn--icon" id="privacy-close">&times;</button>
    </div>

    <div class="aai-stat-grid">
      <div class="aai-stat-card">
        <div class="aai-stat-value">${stats.anonymized}</div>
        <div class="aai-stat-label">${t('privacyBadge', { n: '' }).replace(/\s*$/, '')}</div>
      </div>
      <div class="aai-stat-card">
        <div class="aai-stat-value">${stats.restored}</div>
        <div class="aai-stat-label">${t('privacyRestored', { n: '' }).replace(/\s*$/, '')}</div>
      </div>
    </div>

    ${mappings.length ? `
      <div class="aai-entity-list">
        <h4>${t('entitiesDetected')}</h4>
        ${mappings.map(m => `
          <div class="aai-entity-item">
            <span class="aai-plevel aai-plevel-${m.protection_level || 2}">${m.protection_level || 2}</span>
            <span class="aai-entity-type">${escHtml(m.type || 'ENTITY')}</span>
            <span class="aai-entity-code">${escHtml(m.codename || '')}</span>
            <button class="aai-entity-action" data-dismiss="${escAttr(m.codename || '')}">${t('dismiss')}</button>
            <button class="aai-entity-action" data-allow="${escAttr(m.codename || '')}">${t('allowAdd')}</button>
          </div>
        `).join('')}
      </div>
    ` : ''}

    ${(settings.allow_list?.length) ? `
      <div class="aai-entity-list">
        <h4>${t('allowTitle')}</h4>
        ${settings.allow_list.map(term => `
          <div class="aai-entity-item">
            <span class="aai-entity-code" style="flex:1">${escHtml(term)}</span>
          </div>
        `).join('')}
      </div>
    ` : ''}
  `;

  // Wire events
  panel.querySelector('#privacy-close')?.addEventListener('click', () => set('privacyPanelOpen', false));

  panel.querySelectorAll('[data-dismiss]').forEach(btn => {
    btn.onclick = async () => {
      const term = btn.dataset.dismiss;
      try {
        await api.dismissTerm(term, false);
        toast(t('dismiss') + ' ✓', 'info');
      } catch (err) {
        toast(err.message, 'error');
      }
    };
  });

  panel.querySelectorAll('[data-allow]').forEach(btn => {
    btn.onclick = async () => {
      const term = btn.dataset.allow;
      try {
        const result = await api.addToAllowList(term);
        const settings = get('settings');
        set('settings', { ...settings, allow_list: result.allow_list });
        toast(t('allowAdd') + ' ✓', 'success');
        render();
      } catch (err) {
        toast(err.message, 'error');
      }
    };
  });
}

function escHtml(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function escAttr(s) { return String(s).replace(/"/g, '&quot;'); }
