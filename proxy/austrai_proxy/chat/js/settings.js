/**
 * AUSTR.AI — Settings Page
 * Renders as a full page view (not modal).
 * Provider config, API keys, privacy settings.
 */

import { get, set, on, toast } from './state.js';
import * as api from './api.js';
import { t } from './i18n.js';

const PROVIDER_IDS = ['anthropic', 'openai', 'mistral', 'google', 'ollama'];
const PROVIDER_KEYS = { anthropic: 'pAnthropic', openai: 'pOpenai', mistral: 'pMistral', google: 'pGoogle', ollama: 'pOllama' };

let container;

export function init() {
  container = document.getElementById('settings-view');
  if (!container) return;

  document.getElementById('btn-settings').addEventListener('click', show);
}

export function show() {
  if (window.__aai_showView) window.__aai_showView('settings-view');
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
  const settings = get('settings');
  const providers = get('providers');

  container.innerHTML = `
    <div class="aai-settings-page">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px">
        <h2>${t('settingsTitle')}</h2>
        <button class="aai-btn aai-btn--ghost aai-btn--sm" id="settings-back">← Zurück</button>
      </div>

      <div class="aai-tabs" role="tablist">
        <button class="aai-tab active" data-tab="providers" role="tab">${t('tabProviders')}</button>
        <button class="aai-tab" data-tab="privacy" role="tab">${t('tabPrivacy')}</button>
      </div>

      <!-- Provider Tab -->
      <div class="aai-tab-content active" id="tab-providers">
        ${PROVIDER_IDS.map(pid => {
          const prov = providers[pid] || {};
          const isOllama = pid === 'ollama';
          const configured = prov.configured;
          const statusClass = configured ? 'aai-provider-status--ok' : 'aai-provider-status--none';
          const statusText = configured ? '✓' : '—';
          const keyField = `${pid}_api_key`;
          const maskedKey = settings[keyField] || '';

          return `<div class="aai-provider-card">
            <div class="aai-provider-card-header">
              <span class="aai-provider-name">${t(PROVIDER_KEYS[pid])}</span>
              <span class="aai-provider-status ${statusClass}">${statusText}</span>
            </div>
            ${isOllama ? `
              <div class="aai-field">
                <label>${t('ollamaUrl')}</label>
                <div class="aai-key-row">
                  <input class="aai-input" id="inp-ollama-url" value="${escAttr(settings.ollama_url || 'http://localhost:11434')}" />
                  <button class="aai-btn aai-btn--ghost aai-btn--sm" data-validate="ollama">${t('validate')}</button>
                </div>
              </div>
            ` : `
              <div class="aai-field">
                <label>${t('apiKey')}</label>
                <div class="aai-key-row">
                  <input class="aai-input" type="password" id="inp-key-${pid}" placeholder="${t('apiKeyPh')}" value="${escAttr(maskedKey)}" />
                  <button class="aai-btn aai-btn--ghost aai-btn--sm" data-validate="${pid}">${t('validate')}</button>
                </div>
                <div class="aai-key-status" id="key-status-${pid}" style="margin-top:4px;font-size:12px"></div>
              </div>
            `}
          </div>`;
        }).join('')}

        <div class="aai-field">
          <label>${t('defaultProvider')}</label>
          <select class="aai-select" id="sel-default-provider" style="width:100%">
            ${PROVIDER_IDS.map(pid => `<option value="${pid}" ${settings.default_provider === pid ? 'selected' : ''}>${t(PROVIDER_KEYS[pid])}</option>`).join('')}
          </select>
        </div>

        <div class="aai-field">
          <label>${t('defaultModel')}</label>
          <select class="aai-select" id="sel-default-model" style="width:100%">
            ${renderModelOptions(settings.default_provider || 'anthropic', providers, settings.default_model)}
          </select>
        </div>
      </div>

      <!-- Privacy Tab -->
      <div class="aai-tab-content" id="tab-privacy">
        <div class="aai-field">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" id="chk-confirm-send" ${getConfirmSend() ? 'checked' : ''} style="accent-color:var(--accent);width:16px;height:16px" />
            Anonymisierung vor dem Senden bestätigen
          </label>
          <p style="font-size:12px;color:var(--text-muted);margin-top:4px;margin-left:24px">
            Wenn aktiv, siehst du vor jedem Senden eine Vorschau der Anonymisierung und musst bestätigen.
          </p>
        </div>

        <div class="aai-field">
          <label>${t('threshold')}</label>
          <div class="aai-slider-wrap">
            <span class="aai-slider-label">${t('thresholdLow')}</span>
            <input type="range" min="0.3" max="0.9" step="0.05" value="${settings.confidence_threshold || 0.5}" id="inp-threshold" />
            <span class="aai-slider-label">${t('thresholdHigh')}</span>
            <span class="aai-slider-value" id="threshold-value">${settings.confidence_threshold || 0.5}</span>
          </div>
        </div>

        <div class="aai-field">
          <label>${t('allowList')}</label>
          <div class="aai-tag-list" id="allow-tags">
            ${(settings.allow_list || []).map(term => `<span class="aai-tag">${escHtml(term)}<button class="aai-tag-remove" data-list="allow" data-term="${escAttr(term)}">&times;</button></span>`).join('')}
          </div>
          <div class="aai-tag-input-row">
            <input class="aai-input" id="inp-allow" placeholder="${t('addTerm')}" />
            <button class="aai-btn aai-btn--ghost aai-btn--sm" id="btn-add-allow">+</button>
          </div>
        </div>

        <div class="aai-field">
          <label>${t('denyList')}</label>
          <div class="aai-tag-list" id="deny-tags">
            ${(settings.deny_list || []).map(term => `<span class="aai-tag">${escHtml(term)}<button class="aai-tag-remove" data-list="deny" data-term="${escAttr(term)}">&times;</button></span>`).join('')}
          </div>
          <div class="aai-tag-input-row">
            <input class="aai-input" id="inp-deny" placeholder="${t('addTerm')}" />
            <button class="aai-btn aai-btn--ghost aai-btn--sm" id="btn-add-deny">+</button>
          </div>
        </div>
      </div>

      <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border)">
        <button class="aai-btn aai-btn--ghost aai-btn--sm" id="btn-open-debug" style="color:var(--text-muted);font-size:12px">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          Transparenz-Log öffnen (für Entwickler)
        </button>
      </div>

      <div class="aai-settings-footer">
        <button class="aai-btn aai-btn--ghost" id="settings-cancel">${t('cancel')}</button>
        <button class="aai-btn aai-btn--primary" id="settings-save">${t('save')}</button>
      </div>
    </div>
  `;

  wireEvents();
}

function wireEvents() {
  container.querySelector('#settings-back')?.addEventListener('click', back);
  container.querySelector('#settings-cancel')?.addEventListener('click', back);

  // Transparenz-Log (Debug panel)
  container.querySelector('#btn-open-debug')?.addEventListener('click', () => {
    import('./debug.js').then(debug => debug.open());
  });

  // Tabs
  container.querySelectorAll('.aai-tab').forEach(tab => {
    tab.onclick = () => {
      container.querySelectorAll('.aai-tab').forEach(t => t.classList.remove('active'));
      container.querySelectorAll('.aai-tab-content').forEach(c => c.classList.remove('active'));
      tab.classList.add('active');
      container.querySelector(`#tab-${tab.dataset.tab}`).classList.add('active');
    };
  });

  // Confirm-send checkbox
  const chkConfirm = container.querySelector('#chk-confirm-send');
  if (chkConfirm) {
    chkConfirm.onchange = () => setConfirmSend(chkConfirm.checked);
  }

  // Validate
  container.querySelectorAll('[data-validate]').forEach(btn => {
    btn.onclick = async () => {
      const pid = btn.dataset.validate;
      btn.disabled = true; btn.textContent = '…';
      try {
        let result;
        if (pid === 'ollama') {
          result = await api.validateKey('ollama', '', container.querySelector('#inp-ollama-url').value);
        } else {
          result = await api.validateKey(pid, container.querySelector(`#inp-key-${pid}`).value);
        }
        const statusEl = container.querySelector(`#key-status-${pid}`);
        if (statusEl) {
          statusEl.textContent = result.valid ? `✓ ${t('keyValid')}` : `✗ ${result.error || t('keyInvalid')}`;
          statusEl.style.color = result.valid ? 'var(--success)' : 'var(--danger)';
        }
        toast(result.valid ? t('keyValid') : (result.error || t('keyInvalid')), result.valid ? 'success' : 'error');
      } catch (err) { toast(err.message, 'error'); }
      btn.disabled = false; btn.textContent = t('validate');
    };
  });

  // Default provider → update model list
  const selProvider = container.querySelector('#sel-default-provider');
  const selModel = container.querySelector('#sel-default-model');
  if (selProvider) {
    selProvider.onchange = () => {
      selModel.innerHTML = renderModelOptions(selProvider.value, get('providers'), '');
    };
  }

  // Threshold
  const slider = container.querySelector('#inp-threshold');
  const sliderVal = container.querySelector('#threshold-value');
  if (slider) slider.oninput = () => { sliderVal.textContent = slider.value; };

  // Tags
  container.querySelectorAll('.aai-tag-remove').forEach(btn => {
    btn.onclick = () => {
      const list = btn.dataset.list;
      const term = btn.dataset.term;
      const settings = get('settings');
      const key = list === 'allow' ? 'allow_list' : 'deny_list';
      settings[key] = (settings[key] || []).filter(t => t !== term);
      set('settings', { ...settings });
      render();
    };
  });

  const addTag = (listKey, inputId) => {
    const input = container.querySelector(inputId);
    const term = input?.value.trim();
    if (!term) return;
    const settings = get('settings');
    if (!settings[listKey]) settings[listKey] = [];
    if (!settings[listKey].includes(term)) {
      settings[listKey].push(term);
      set('settings', { ...settings });
    }
    if (input) input.value = '';
    render();
  };

  container.querySelector('#btn-add-allow')?.addEventListener('click', () => addTag('allow_list', '#inp-allow'));
  container.querySelector('#btn-add-deny')?.addEventListener('click', () => addTag('deny_list', '#inp-deny'));
  container.querySelector('#inp-allow')?.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); addTag('allow_list', '#inp-allow'); } });
  container.querySelector('#inp-deny')?.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); addTag('deny_list', '#inp-deny'); } });

  // Save
  container.querySelector('#settings-save').onclick = async () => {
    const data = {};
    PROVIDER_IDS.filter(p => p !== 'ollama').forEach(pid => {
      const inp = container.querySelector(`#inp-key-${pid}`);
      if (inp) data[`${pid}_api_key`] = inp.value;
    });
    const ollamaInp = container.querySelector('#inp-ollama-url');
    if (ollamaInp) data.ollama_url = ollamaInp.value;
    data.default_provider = container.querySelector('#sel-default-provider').value;
    data.default_model = container.querySelector('#sel-default-model').value;
    const threshold = container.querySelector('#inp-threshold');
    if (threshold) data.confidence_threshold = parseFloat(threshold.value);
    const settings = get('settings');
    data.allow_list = settings.allow_list || [];
    data.deny_list = settings.deny_list || [];

    try {
      await api.putSettings(data);
      const [newSettings, newProviders] = await Promise.all([api.getSettings(), api.getProviders()]);
      set('settings', newSettings);
      set('providers', newProviders);
      set('provider', newSettings.default_provider || get('provider'));
      set('model', newSettings.default_model || get('model'));
      toast('Gespeichert ✓', 'success');
      back();
    } catch (err) { toast(err.message, 'error'); }
  };
}

function renderModelOptions(providerId, providers, selectedModel) {
  const prov = providers[providerId];
  if (!prov?.models?.length) return '<option value="">—</option>';
  return prov.models.map(m => `<option value="${m.id}" ${m.id === selectedModel ? 'selected' : ''}>${m.name}</option>`).join('');
}

/* ---- Confirm-Send Preference (stored in localStorage) ---- */

export function getConfirmSend() {
  const val = localStorage.getItem('aai_confirm_send');
  return val === null ? true : val === 'true'; // Default: ON
}

export function setConfirmSend(enabled) {
  localStorage.setItem('aai_confirm_send', String(enabled));
}

function escHtml(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
function escAttr(s) { return String(s).replace(/"/g, '&quot;').replace(/'/g, '&#39;'); }
