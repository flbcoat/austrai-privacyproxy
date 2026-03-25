/**
 * AUSTR.AI — Onboarding (First Run)
 * DAU-proof: assumes ZERO technical knowledge.
 * 3 steps: Welcome → Provider → Ready.
 * No jargon, big buttons, clear visuals.
 */

import { get, set, toast } from './state.js';
import * as api from './api.js';
import { getLang } from './i18n.js';

const SVG_SHIELD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';
const SVG_CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>';

let overlay, step = 0;
let selectedProvider = '';
let keyValue = '';
let ollamaUrl = 'http://localhost:11434';
let providers = {};

export function init() {
  overlay = document.getElementById('onboarding-overlay');
}

export async function show() {
  step = 0;
  selectedProvider = '';
  keyValue = '';
  overlay.hidden = false;

  // Load providers to check what's available
  try {
    providers = await api.getProviders();
    // Auto-select if Ollama is running
    if (providers.ollama?.configured && providers.ollama.models?.length) {
      selectedProvider = 'ollama';
    }
  } catch { providers = {}; }

  render();
}

function render() {
  const isDE = getLang() === 'de';

  overlay.innerHTML = `
    <div class="aai-onboarding">
      <div class="aai-ob-progress">
        <div class="aai-ob-dot ${step >= 0 ? 'current' : ''}"></div>
        <div class="aai-ob-dot ${step >= 1 ? 'current' : ''}"></div>
        <div class="aai-ob-dot ${step >= 2 ? 'current' : ''}"></div>
      </div>

      ${step === 0 ? renderWelcome(isDE) : ''}
      ${step === 1 ? renderProvider(isDE) : ''}
      ${step === 2 ? renderReady(isDE) : ''}

      <div class="aai-ob-footer">
        <span class="aai-ob-step-label">${step + 1} / 3</span>
        <div class="aai-ob-buttons">
          ${step > 0 ? `<button class="aai-btn aai-btn--ghost" id="ob-back">${isDE ? 'Zurück' : 'Back'}</button>` : ''}
          ${step < 2
            ? `<button class="aai-btn aai-btn--primary" id="ob-next">${isDE ? 'Weiter' : 'Next'}</button>`
            : `<button class="aai-btn aai-btn--primary aai-btn--lg" id="ob-finish">${isDE ? 'Loslegen' : 'Get started'}</button>`
          }
        </div>
      </div>
    </div>
  `;

  wireEvents();
}

function renderWelcome(isDE) {
  return `
    <div class="aai-ob-step active">
      <div class="aai-ob-icon">${SVG_SHIELD}</div>
      <h2>${isDE ? 'Willkommen bei AUSTR.AI' : 'Welcome to AUSTR.AI'}</h2>
      <p style="font-size:15px;line-height:1.7;color:var(--text-secondary)">
        ${isDE
          ? 'AUSTR.AI schützt deine Daten wenn du mit einer KI chattest. Namen, Adressen, Bankdaten — alles wird automatisch anonymisiert bevor es die KI sieht.'
          : 'AUSTR.AI protects your data when you chat with AI. Names, addresses, bank details — everything is automatically anonymized before the AI sees it.'}
      </p>
      <div style="background:var(--bg-sidebar);border-radius:var(--r-lg);padding:16px;margin-top:12px;text-align:center">
        <div style="display:flex;align-items:center;justify-content:center;gap:8px;flex-wrap:wrap;font-size:13px">
          <span style="background:var(--danger-subtle);color:var(--danger);padding:4px 10px;border-radius:var(--r-md)">Dr. Müller, IBAN AT48...</span>
          <span style="color:var(--text-muted)">→</span>
          <span style="background:var(--accent-subtle);color:var(--accent);padding:4px 10px;border-radius:var(--r-md);font-family:var(--mono)">[PERSON_1], [IBAN_1]</span>
          <span style="color:var(--text-muted)">→ KI →</span>
          <span style="background:var(--success-subtle);color:var(--success);padding:4px 10px;border-radius:var(--r-md)">Dr. Müller, IBAN AT48...</span>
        </div>
      </div>
    </div>`;
}

function renderProvider(isDE) {
  const ollamaAvailable = providers.ollama?.configured && providers.ollama.models?.length > 0;
  const ollamaRunning = providers.ollama?.configured;

  return `
    <div class="aai-ob-step active">
      <h2>${isDE ? 'Welche KI möchtest du nutzen?' : 'Which AI would you like to use?'}</h2>
      <p style="color:var(--text-secondary);font-size:14px;margin-bottom:12px">
        ${isDE ? 'Du kannst das jederzeit in den Einstellungen ändern.' : 'You can change this anytime in settings.'}
      </p>

      <div class="aai-ob-provider-grid">
        <!-- Ollama (local) -->
        <div class="aai-ob-provider aai-ob-provider-local ${selectedProvider === 'ollama' ? 'selected' : ''}" data-provider="ollama">
          <strong>${isDE ? '🏠 Ollama — Komplett lokal' : '🏠 Ollama — Fully local'}</strong>
          <p style="font-size:12px;color:var(--text-muted);margin-top:4px">
            ${ollamaAvailable
              ? (isDE ? '✓ Ollama läuft, Modelle verfügbar' : '✓ Ollama running, models available')
              : ollamaRunning
                ? (isDE ? '⚠ Ollama läuft, aber kein Modell installiert' : '⚠ Ollama running, but no model installed')
                : (isDE ? 'Kostenlos, keine Daten verlassen deinen Rechner' : 'Free, no data leaves your computer')}
          </p>
        </div>

        <!-- Cloud providers -->
        <div class="aai-ob-provider ${selectedProvider === 'anthropic' ? 'selected' : ''}" data-provider="anthropic">
          <strong>Claude</strong>
          <p style="font-size:11px;color:var(--text-muted);margin-top:2px">Anthropic · API-Key</p>
        </div>
        <div class="aai-ob-provider ${selectedProvider === 'openai' ? 'selected' : ''}" data-provider="openai">
          <strong>ChatGPT</strong>
          <p style="font-size:11px;color:var(--text-muted);margin-top:2px">OpenAI · API-Key</p>
        </div>
        <div class="aai-ob-provider ${selectedProvider === 'mistral' ? 'selected' : ''}" data-provider="mistral">
          <strong>Mistral</strong>
          <p style="font-size:11px;color:var(--text-muted);margin-top:2px">EU-Server · API-Key</p>
        </div>
        <div class="aai-ob-provider ${selectedProvider === 'google' ? 'selected' : ''}" data-provider="google">
          <strong>Gemini</strong>
          <p style="font-size:11px;color:var(--text-muted);margin-top:2px">Google · API-Key</p>
        </div>
      </div>

      ${selectedProvider && selectedProvider !== 'ollama' ? `
        <div class="aai-field" style="margin-top:16px">
          <label style="font-size:13px;font-weight:500;color:var(--text-secondary)">
            ${isDE ? 'API-Schlüssel eingeben' : 'Enter API key'}
          </label>
          <div style="display:flex;gap:6px;margin-top:4px">
            <input class="aai-input" type="password" id="ob-key" placeholder="${isDE ? 'sk-...' : 'sk-...'}" value="${keyValue}" style="flex:1;font-family:var(--mono);font-size:13px" />
            <button class="aai-btn aai-btn--ghost aai-btn--sm" id="ob-validate">${isDE ? 'Testen' : 'Test'}</button>
          </div>
          <div id="ob-key-status" style="margin-top:4px;font-size:12px"></div>
          <p style="font-size:11px;color:var(--text-muted);margin-top:6px">
            ${isDE
              ? 'Den API-Key findest du in deinem Anbieter-Dashboard. AUSTR.AI speichert ihn lokal auf deinem Rechner.'
              : 'Find your API key in your provider dashboard. AUSTR.AI stores it locally on your machine.'}
          </p>
        </div>
      ` : ''}

      ${selectedProvider === 'ollama' && !ollamaAvailable ? `
        <div style="background:var(--bg-sidebar);border-radius:var(--r-md);padding:14px;margin-top:14px;font-size:13px">
          ${!ollamaRunning ? `
            <p style="margin-bottom:8px"><strong>${isDE ? 'Ollama installieren:' : 'Install Ollama:'}</strong></p>
            <div style="background:#1e1e2e;border-radius:var(--r-sm);padding:8px 12px;font-family:var(--mono);font-size:12px;color:#e0e0e0;margin-bottom:8px">
              ${isDE ? 'Lade Ollama herunter: ' : 'Download Ollama: '}<a href="https://ollama.com" target="_blank" style="color:var(--accent)">ollama.com</a>
            </div>
          ` : ''}
          <p style="margin-bottom:8px"><strong>${isDE ? 'Ein Modell herunterladen:' : 'Download a model:'}</strong></p>
          <div style="background:#1e1e2e;border-radius:var(--r-sm);padding:8px 12px;font-family:var(--mono);font-size:12px;color:#e0e0e0">
            ollama pull llama3.2
          </div>
          <p style="font-size:11px;color:var(--text-muted);margin-top:8px">
            ${isDE ? 'Danach diese Seite neu laden.' : 'Then reload this page.'}
          </p>
        </div>
      ` : ''}
    </div>`;
}

function renderReady(isDE) {
  return `
    <div class="aai-ob-step active" style="text-align:center">
      <div class="aai-ob-icon" style="margin:0 auto">${SVG_CHECK}</div>
      <h2>${isDE ? 'Alles bereit!' : 'All set!'}</h2>
      <p style="font-size:15px;color:var(--text-secondary);max-width:360px;margin:0 auto;line-height:1.7">
        ${isDE
          ? 'Du kannst jetzt loschatten. Alles wird automatisch geschützt. Einstellungen, Tutorial und Werkzeuge findest du in der Seitenleiste.'
          : 'You can start chatting now. Everything is automatically protected. Settings, tutorial, and tools are in the sidebar.'}
      </p>
    </div>`;
}

function wireEvents() {
  // Navigation
  overlay.querySelector('#ob-back')?.addEventListener('click', () => { step--; render(); });
  overlay.querySelector('#ob-next')?.addEventListener('click', () => {
    if (step === 1 && !selectedProvider) {
      toast(getLang() === 'de' ? 'Bitte wähle einen KI-Anbieter' : 'Please select an AI provider', 'error');
      return;
    }
    if (step === 1 && selectedProvider !== 'ollama' && !keyValue) {
      toast(getLang() === 'de' ? 'Bitte gib einen API-Schlüssel ein' : 'Please enter an API key', 'error');
      return;
    }
    collectData();
    step++;
    render();
  });
  overlay.querySelector('#ob-finish')?.addEventListener('click', finish);

  // Provider selection
  overlay.querySelectorAll('.aai-ob-provider').forEach(el => {
    el.addEventListener('click', () => {
      selectedProvider = el.dataset.provider;
      keyValue = '';
      render();
    });
  });

  // API key input
  overlay.querySelector('#ob-key')?.addEventListener('input', (e) => {
    keyValue = e.target.value;
  });

  // Validate key
  overlay.querySelector('#ob-validate')?.addEventListener('click', async () => {
    const btn = overlay.querySelector('#ob-validate');
    const statusEl = overlay.querySelector('#ob-key-status');
    if (!keyValue) return;

    btn.disabled = true;
    btn.textContent = '…';

    try {
      const result = await api.validateKey(selectedProvider, keyValue);
      if (statusEl) {
        statusEl.textContent = result.valid ? '✓ Funktioniert!' : `✗ ${result.error || 'Ungültig'}`;
        statusEl.style.color = result.valid ? 'var(--success)' : 'var(--danger)';
      }
    } catch (err) {
      if (statusEl) { statusEl.textContent = err.message; statusEl.style.color = 'var(--danger)'; }
    }

    btn.disabled = false;
    btn.textContent = getLang() === 'de' ? 'Testen' : 'Test';
  });
}

function collectData() {
  if (step === 1) {
    const keyInput = overlay.querySelector('#ob-key');
    if (keyInput) keyValue = keyInput.value;
  }
}

async function finish() {
  collectData();

  const data = {
    default_provider: selectedProvider,
    ollama_url: ollamaUrl,
  };

  if (selectedProvider !== 'ollama' && keyValue) {
    data[`${selectedProvider}_api_key`] = keyValue;
  }

  // Pick default model
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
  } catch (err) {
    toast(err.message, 'error');
  }
}
