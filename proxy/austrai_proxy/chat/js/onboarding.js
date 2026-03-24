/**
 * AUSTR.AI — Onboarding Wizard
 * 5-step setup: welcome, provider, key, privacy, ready.
 */

import { get, set, toast } from './state.js';
import * as api from './api.js';
import { t } from './i18n.js';

const PROVIDER_IDS = ['anthropic', 'openai', 'mistral', 'google', 'ollama'];
const PROVIDER_KEYS = { anthropic: 'pAnthropic', openai: 'pOpenai', mistral: 'pMistral', google: 'pGoogle', ollama: 'pOllama' };

const SVG_SHIELD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';
const SVG_CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>';

let overlay, step = 0;
let selectedProvider = 'ollama';
let keyValue = '';
let ollamaUrl = 'http://localhost:11434';
let threshold = 0.5;

export function init() {
  overlay = document.getElementById('onboarding-overlay');
}

export function show() {
  step = 0;
  selectedProvider = 'ollama';
  keyValue = '';
  threshold = 0.5;
  overlay.hidden = false;
  render();
}

function render() {
  const totalSteps = 5;

  overlay.innerHTML = `
    <div class="aai-onboarding" role="dialog" aria-label="${t('obTitle')}">
      <div class="aai-ob-progress">
        ${Array.from({ length: totalSteps }, (_, i) =>
          `<div class="aai-ob-dot ${i < step ? 'done' : ''} ${i === step ? 'current' : ''}"></div>`
        ).join('')}
      </div>

      ${renderStep(step)}

      <div class="aai-ob-footer">
        <span class="aai-ob-step-label">${t('step')} ${step + 1} ${t('of')} ${totalSteps}</span>
        <div class="aai-ob-buttons">
          ${step > 0 ? `<button class="aai-btn aai-btn--ghost" id="ob-back">${t('back')}</button>` : `<button class="aai-btn aai-btn--ghost" id="ob-skip">${t('skip')}</button>`}
          ${step < totalSteps - 1
            ? `<button class="aai-btn aai-btn--primary" id="ob-next">${t('next')}</button>`
            : `<button class="aai-btn aai-btn--primary" id="ob-finish">${t('finish')}</button>`
          }
        </div>
      </div>
    </div>
  `;

  wireEvents();
}

function renderStep(s) {
  switch (s) {
    case 0: return `
      <div class="aai-ob-step active">
        <div class="aai-ob-icon">${SVG_SHIELD}</div>
        <h2>${t('ob1Title')}</h2>
        <p>${t('ob1Text')}</p>
      </div>`;

    case 1: return `
      <div class="aai-ob-step active">
        <h2>${t('ob2Title')}</h2>
        <p>${t('ob2Text')}</p>
        <div class="aai-ob-provider-grid">
          ${PROVIDER_IDS.filter(p => p !== 'ollama').map(pid =>
            `<div class="aai-ob-provider ${selectedProvider === pid ? 'selected' : ''}" data-provider="${pid}">${t(PROVIDER_KEYS[pid])}</div>`
          ).join('')}
          <div class="aai-ob-provider aai-ob-provider-local ${selectedProvider === 'ollama' ? 'selected' : ''}" data-provider="ollama">${t(PROVIDER_KEYS.ollama)}</div>
        </div>
      </div>`;

    case 2: return `
      <div class="aai-ob-step active">
        <h2>${t('ob3Title')}</h2>
        <p>${t('ob3Text')}</p>
        ${selectedProvider === 'ollama' ? `
          <div class="aai-field">
            <label>${t('ollamaUrl')}</label>
            <div class="aai-key-row">
              <input class="aai-input" id="ob-ollama-url" value="${ollamaUrl}" />
              <button class="aai-btn aai-btn--ghost aai-btn--sm" id="ob-validate">${t('validate')}</button>
            </div>
            <div id="ob-key-status" style="margin-top:6px;font-size:13px"></div>
          </div>
        ` : `
          <div class="aai-field">
            <label>${t('apiKey')} — ${t(PROVIDER_KEYS[selectedProvider])}</label>
            <div class="aai-key-row">
              <input class="aai-input" type="password" id="ob-api-key" placeholder="${t('apiKeyPh')}" value="${keyValue}" />
              <button class="aai-btn aai-btn--ghost aai-btn--sm" id="ob-validate">${t('validate')}</button>
            </div>
            <div id="ob-key-status" style="margin-top:6px;font-size:13px"></div>
          </div>
        `}
      </div>`;

    case 3: return `
      <div class="aai-ob-step active">
        <h2>${t('ob4Title')}</h2>
        <p>${t('ob4Text')}</p>
        <div class="aai-field" style="margin-top:8px">
          <label>${t('threshold')}</label>
          <div class="aai-slider-wrap">
            <span class="aai-slider-label">${t('thresholdLow')}</span>
            <input type="range" min="0.3" max="0.9" step="0.05" value="${threshold}" id="ob-threshold" />
            <span class="aai-slider-label">${t('thresholdHigh')}</span>
            <span class="aai-slider-value" id="ob-threshold-val">${threshold}</span>
          </div>
        </div>
      </div>`;

    case 4: return `
      <div class="aai-ob-step active">
        <div class="aai-ob-icon">${SVG_CHECK}</div>
        <h2>${t('ob5Title')}</h2>
        <p>${t('ob5Text')}</p>
      </div>`;

    default: return '';
  }
}

function wireEvents() {
  // Navigation
  overlay.querySelector('#ob-back')?.addEventListener('click', () => { step--; render(); });
  overlay.querySelector('#ob-next')?.addEventListener('click', () => {
    collectStepData();
    step++;
    render();
  });
  overlay.querySelector('#ob-skip')?.addEventListener('click', finish);
  overlay.querySelector('#ob-finish')?.addEventListener('click', finish);

  // Provider selection (step 1)
  overlay.querySelectorAll('.aai-ob-provider').forEach(el => {
    el.addEventListener('click', () => {
      selectedProvider = el.dataset.provider;
      render();
    });
  });

  // Validate button (step 2)
  overlay.querySelector('#ob-validate')?.addEventListener('click', async () => {
    const btn = overlay.querySelector('#ob-validate');
    const statusEl = overlay.querySelector('#ob-key-status');
    btn.disabled = true;
    btn.textContent = '…';

    try {
      let result;
      if (selectedProvider === 'ollama') {
        ollamaUrl = overlay.querySelector('#ob-ollama-url')?.value || ollamaUrl;
        result = await api.validateKey('ollama', '', ollamaUrl);
      } else {
        keyValue = overlay.querySelector('#ob-api-key')?.value || '';
        result = await api.validateKey(selectedProvider, keyValue);
      }
      if (statusEl) {
        statusEl.textContent = result.valid ? `✓ ${t('keyValid')}` : `✗ ${result.error || t('keyInvalid')}`;
        statusEl.style.color = result.valid ? 'var(--success)' : 'var(--danger)';
      }
    } catch (err) {
      if (statusEl) { statusEl.textContent = err.message; statusEl.style.color = 'var(--danger)'; }
    }

    btn.disabled = false;
    btn.textContent = t('validate');
  });

  // Threshold slider (step 3)
  const slider = overlay.querySelector('#ob-threshold');
  const sliderVal = overlay.querySelector('#ob-threshold-val');
  if (slider) {
    slider.oninput = () => {
      threshold = parseFloat(slider.value);
      if (sliderVal) sliderVal.textContent = threshold;
    };
  }
}

function collectStepData() {
  if (step === 2) {
    if (selectedProvider === 'ollama') {
      ollamaUrl = overlay.querySelector('#ob-ollama-url')?.value || ollamaUrl;
    } else {
      keyValue = overlay.querySelector('#ob-api-key')?.value || keyValue;
    }
  }
  if (step === 3) {
    const slider = overlay.querySelector('#ob-threshold');
    if (slider) threshold = parseFloat(slider.value);
  }
}

async function finish() {
  collectStepData();

  // Save settings
  const data = {
    default_provider: selectedProvider,
    confidence_threshold: threshold,
    ollama_url: ollamaUrl,
  };

  if (selectedProvider !== 'ollama' && keyValue) {
    data[`${selectedProvider}_api_key`] = keyValue;
  }

  // Pick default model
  const providers = get('providers');
  const prov = providers[selectedProvider];
  if (prov?.models?.length) {
    data.default_model = prov.models[0].id;
  }

  try {
    await api.putSettings(data);
    const [newSettings, newProviders] = await Promise.all([api.getSettings(), api.getProviders()]);
    set('settings', newSettings);
    set('providers', newProviders);
    set('provider', selectedProvider);
    set('model', data.default_model || '');
    set('onboardingDone', true);
    overlay.hidden = true;
    toast(t('ob5Title'), 'success');
  } catch (err) {
    toast(err.message, 'error');
  }
}
