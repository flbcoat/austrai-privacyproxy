/**
 * AUSTR.AI — Settings Page (Preact)
 * Full-page view: provider config, API keys, privacy settings.
 */

import { h, render, Fragment } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import htm from 'htm';
import { signals, batch, toast } from './state.js';
import * as api from './api.js';
import { t } from './i18n.js';

const html = htm.bind(h);

const PROVIDER_IDS = ['anthropic', 'openai', 'mistral', 'google', 'ollama'];
const PROVIDER_LABEL_KEYS = {
  anthropic: 'pAnthropic', openai: 'pOpenai', mistral: 'pMistral', google: 'pGoogle', ollama: 'pOllama',
};

/* ---- Confirm-Send Preference (stored in localStorage) ----
 * Exported so ChatView can read it for the two-step "Prüfen → Absenden" flow.
 */
export function getConfirmSend() {
  const val = localStorage.getItem('aai_confirm_send');
  return val === null ? true : val === 'true';
}

export function setConfirmSend(enabled) {
  localStorage.setItem('aai_confirm_send', String(enabled));
}

/* ---- Provider Card ---- */

function ProviderCard({ pid, prov, draftKey, onKeyChange, ollamaUrl, onOllamaUrlChange }) {
  const isOllama = pid === 'ollama';
  const configured = prov.configured;
  const statusClass = configured ? 'aai-provider-status--ok' : 'aai-provider-status--none';
  const statusText = configured ? '✓' : '—';

  const [status, setStatus] = useState(null); // {valid, message}
  const [validating, setValidating] = useState(false);

  async function handleValidate() {
    setValidating(true);
    setStatus(null);
    try {
      const result = isOllama
        ? await api.validateKey('ollama', '', ollamaUrl)
        : await api.validateKey(pid, draftKey);
      setStatus({
        valid: result.valid,
        message: result.valid ? t('keyValid') : (result.error || t('keyInvalid')),
      });
      toast(result.valid ? t('keyValid') : (result.error || t('keyInvalid')), result.valid ? 'success' : 'error');
    } catch (err) {
      toast(err.message, 'error');
    }
    setValidating(false);
  }

  return html`
    <div class="aai-provider-card">
      <div class="aai-provider-card-header">
        <span class="aai-provider-name">${t(PROVIDER_LABEL_KEYS[pid])}</span>
        <span class=${`aai-provider-status ${statusClass}`}>${statusText}</span>
      </div>
      ${isOllama ? html`
        <div class="aai-field">
          <label>${t('ollamaUrl')}</label>
          <div class="aai-key-row">
            <input
              class="aai-input"
              value=${ollamaUrl}
              onInput=${(e) => onOllamaUrlChange(e.target.value)}
            />
            <button class="aai-btn aai-btn--ghost aai-btn--sm" onClick=${handleValidate} disabled=${validating}>
              ${validating ? '…' : t('validate')}
            </button>
          </div>
        </div>
      ` : html`
        <div class="aai-field">
          <label>${t('apiKey')}</label>
          <div class="aai-key-row">
            <input
              class="aai-input"
              type="password"
              placeholder=${t('apiKeyPh')}
              value=${draftKey}
              onInput=${(e) => onKeyChange(pid, e.target.value)}
            />
            <button class="aai-btn aai-btn--ghost aai-btn--sm" onClick=${handleValidate} disabled=${validating || !draftKey}>
              ${validating ? '…' : t('validate')}
            </button>
          </div>
          ${status ? html`
            <div
              class="aai-key-status"
              style=${`margin-top:4px;font-size:12px;color:${status.valid ? 'var(--success)' : 'var(--danger)'}`}
            >${status.valid ? '✓' : '✗'} ${status.message}</div>
          ` : null}
        </div>
      `}
    </div>
  `;
}

/* ---- Tag list ---- */

function TagList({ tags, onAdd, onRemove, placeholder }) {
  const [value, setValue] = useState('');

  function handleAdd() {
    const term = value.trim();
    if (!term) return;
    onAdd(term);
    setValue('');
  }

  return html`
    <${Fragment}>
      <div class="aai-tag-list">
        ${tags.map((term) => html`
          <span key=${term} class="aai-tag">
            ${term}
            <button class="aai-tag-remove" onClick=${() => onRemove(term)}>×</button>
          </span>
        `)}
      </div>
      <div class="aai-tag-input-row">
        <input
          class="aai-input"
          placeholder=${placeholder}
          value=${value}
          onInput=${(e) => setValue(e.target.value)}
          onKeyDown=${(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAdd(); } }}
        />
        <button class="aai-btn aai-btn--ghost aai-btn--sm" onClick=${handleAdd}>+</button>
      </div>
    <//>
  `;
}

/* ---- Main Settings View ---- */

function SettingsView({ onClose }) {
  const settings = signals.settings.value;
  const providers = signals.providers.value;

  const [tab, setTab] = useState('providers');
  const [draftKeys, setDraftKeys] = useState(() => {
    const out = {};
    for (const pid of PROVIDER_IDS) {
      if (pid === 'ollama') continue;
      out[pid] = settings[`${pid}_api_key`] || '';
    }
    return out;
  });
  const [ollamaUrl, setOllamaUrl] = useState(settings.ollama_url || 'http://localhost:11434');
  const [defaultProvider, setDefaultProvider] = useState(settings.default_provider || 'anthropic');
  const [defaultModel, setDefaultModel] = useState(settings.default_model || '');
  const [threshold, setThreshold] = useState(settings.confidence_threshold ?? 0.5);
  const [allowList, setAllowList] = useState(settings.allow_list || []);
  const [denyList, setDenyList] = useState(settings.deny_list || []);
  const [confirmSend, setConfirmSendLocal] = useState(getConfirmSend());

  function handleKeyChange(pid, value) {
    setDraftKeys({ ...draftKeys, [pid]: value });
  }

  const availableModels = providers[defaultProvider]?.models || [];

  async function handleSave() {
    const data = {
      default_provider: defaultProvider,
      default_model: defaultModel,
      ollama_url: ollamaUrl,
      confidence_threshold: parseFloat(threshold),
      allow_list: allowList,
      deny_list: denyList,
    };
    for (const pid of PROVIDER_IDS) {
      if (pid === 'ollama') continue;
      if (draftKeys[pid] !== undefined) data[`${pid}_api_key`] = draftKeys[pid];
    }

    try {
      await api.putSettings(data);
      const [newSettings, newProviders] = await Promise.all([api.getSettings(), api.getProviders()]);
      batch({
        settings: newSettings,
        providers: newProviders,
        provider: newSettings.default_provider || signals.provider.value,
        model: newSettings.default_model || signals.model.value,
      });
      toast('Gespeichert ✓', 'success');
      onClose();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  function openDebugPanel() {
    import('./debug.js').then((debug) => debug.open());
  }

  function handleConfirmSendToggle(checked) {
    setConfirmSend(checked);
    setConfirmSendLocal(checked);
  }

  return html`
    <div class="aai-settings-page">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px">
        <h2>${t('settingsTitle')}</h2>
        <button class="aai-btn aai-btn--ghost aai-btn--sm" onClick=${onClose}>← Zurück</button>
      </div>

      <div class="aai-tabs" role="tablist">
        <button class=${`aai-tab${tab === 'providers' ? ' active' : ''}`} role="tab" onClick=${() => setTab('providers')}>
          ${t('tabProviders')}
        </button>
        <button class=${`aai-tab${tab === 'privacy' ? ' active' : ''}`} role="tab" onClick=${() => setTab('privacy')}>
          ${t('tabPrivacy')}
        </button>
      </div>

      ${tab === 'providers' ? html`
        <div class="aai-tab-content active">
          ${PROVIDER_IDS.map((pid) => html`
            <${ProviderCard}
              key=${pid}
              pid=${pid}
              prov=${providers[pid] || {}}
              draftKey=${draftKeys[pid] || ''}
              onKeyChange=${handleKeyChange}
              ollamaUrl=${ollamaUrl}
              onOllamaUrlChange=${setOllamaUrl}
            />
          `)}

          <div class="aai-field">
            <label>${t('defaultProvider')}</label>
            <select
              class="aai-select"
              style="width:100%"
              value=${defaultProvider}
              onChange=${(e) => { setDefaultProvider(e.target.value); setDefaultModel(''); }}
            >
              ${PROVIDER_IDS.map((pid) => html`
                <option key=${pid} value=${pid}>${t(PROVIDER_LABEL_KEYS[pid])}</option>
              `)}
            </select>
          </div>

          <div class="aai-field">
            <label>${t('defaultModel')}</label>
            <select
              class="aai-select"
              style="width:100%"
              value=${defaultModel}
              onChange=${(e) => setDefaultModel(e.target.value)}
            >
              ${availableModels.length === 0
                ? html`<option value="">—</option>`
                : availableModels.map((m) => html`<option key=${m.id} value=${m.id}>${m.name}</option>`)}
            </select>
          </div>
        </div>
      ` : null}

      ${tab === 'privacy' ? html`
        <div class="aai-tab-content active">
          <div class="aai-field">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
              <input
                type="checkbox"
                style="accent-color:var(--accent);width:16px;height:16px"
                checked=${confirmSend}
                onChange=${(e) => handleConfirmSendToggle(e.target.checked)}
              />
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
              <input
                type="range"
                min="0.3"
                max="0.9"
                step="0.05"
                value=${threshold}
                onInput=${(e) => setThreshold(e.target.value)}
              />
              <span class="aai-slider-label">${t('thresholdHigh')}</span>
              <span class="aai-slider-value">${threshold}</span>
            </div>
          </div>

          <div class="aai-field">
            <label>${t('allowList')}</label>
            <${TagList}
              tags=${allowList}
              placeholder=${t('addTerm')}
              onAdd=${(term) => { if (!allowList.includes(term)) setAllowList([...allowList, term]); }}
              onRemove=${(term) => setAllowList(allowList.filter((x) => x !== term))}
            />
          </div>

          <div class="aai-field">
            <label>${t('denyList')}</label>
            <${TagList}
              tags=${denyList}
              placeholder=${t('addTerm')}
              onAdd=${(term) => { if (!denyList.includes(term)) setDenyList([...denyList, term]); }}
              onRemove=${(term) => setDenyList(denyList.filter((x) => x !== term))}
            />
          </div>
        </div>
      ` : null}

      <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border)">
        <button class="aai-btn aai-btn--ghost aai-btn--sm" onClick=${openDebugPanel} style="color:var(--text-muted);font-size:12px">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          Transparenz-Log öffnen (für Entwickler)
        </button>
      </div>

      <div class="aai-settings-footer">
        <button class="aai-btn aai-btn--ghost" onClick=${onClose}>${t('cancel')}</button>
        <button class="aai-btn aai-btn--primary" onClick=${handleSave}>${t('save')}</button>
      </div>
    </div>
  `;
}

/* ---- Navigation ---- */

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
  container = document.getElementById('settings-view');
  if (!container) return;
  const settingsBtn = document.getElementById('btn-settings');
  if (settingsBtn) settingsBtn.addEventListener('click', show);
}

export function show() {
  if (!container) return;
  if (window.__aai_showView) window.__aai_showView('settings-view');
  render(html`<${SettingsView} onClose=${goBack} />`, container);
}
