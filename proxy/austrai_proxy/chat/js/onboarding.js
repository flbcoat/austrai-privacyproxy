/**
 * AUSTR.AI — Onboarding (First Run, Preact)
 * DAU-proof: assumes ZERO technical knowledge.
 * 3 steps: Welcome → Provider → Ready.
 */

import { h, render, Fragment } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import htm from 'htm';
import { signals, batch, toast } from './state.js';
import * as api from './api.js';
import { getLang } from './i18n.js';

const html = htm.bind(h);

const SVG_SHIELD = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>';
const SVG_CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>';

const DEFAULT_OLLAMA_URL = 'http://localhost:11434';

/* ---- Step components ---- */

function WelcomeStep({ isDE }) {
  return html`
    <div class="aai-ob-step active">
      <div class="aai-ob-icon"><span dangerouslySetInnerHTML=${{ __html: SVG_SHIELD }} /></div>
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
    </div>
  `;
}

function ProviderStep({ isDE, providers, selectedProvider, setSelectedProvider, keyValue, setKeyValue, keyStatus, setKeyStatus }) {
  const ollamaAvailable = providers.ollama?.configured && providers.ollama.models?.length > 0;
  const ollamaRunning = providers.ollama?.configured;

  const cloudProviders = [
    { id: 'anthropic', name: 'Claude', sub: 'Anthropic · API-Key' },
    { id: 'openai', name: 'ChatGPT', sub: 'OpenAI · API-Key' },
    { id: 'mistral', name: 'Mistral', sub: 'EU-Server · API-Key' },
    { id: 'google', name: 'Gemini', sub: 'Google · API-Key' },
  ];

  const ollamaDescription = ollamaAvailable
    ? (isDE ? '✓ Ollama läuft, Modelle verfügbar' : '✓ Ollama running, models available')
    : ollamaRunning
      ? (isDE ? '⚠ Ollama läuft, aber kein Modell installiert' : '⚠ Ollama running, but no model installed')
      : (isDE ? 'Kostenlos, keine Daten verlassen deinen Rechner' : 'Free, no data leaves your computer');

  const [validating, setValidating] = useState(false);

  async function handleValidate() {
    if (!keyValue) return;
    setValidating(true);
    setKeyStatus({ text: '…', color: 'var(--text-muted)' });
    try {
      const result = await api.validateKey(selectedProvider, keyValue);
      setKeyStatus({
        text: result.valid ? '✓ Funktioniert!' : `✗ ${result.error || 'Ungültig'}`,
        color: result.valid ? 'var(--success)' : 'var(--danger)',
      });
    } catch (err) {
      setKeyStatus({ text: err.message, color: 'var(--danger)' });
    }
    setValidating(false);
  }

  function selectProvider(id) {
    setSelectedProvider(id);
    setKeyValue('');
    setKeyStatus(null);
  }

  return html`
    <div class="aai-ob-step active">
      <h2>${isDE ? 'Welche KI möchtest du nutzen?' : 'Which AI would you like to use?'}</h2>
      <p style="color:var(--text-secondary);font-size:14px;margin-bottom:12px">
        ${isDE ? 'Du kannst das jederzeit in den Einstellungen ändern.' : 'You can change this anytime in settings.'}
      </p>

      <div class="aai-ob-provider-grid">
        <div
          class=${`aai-ob-provider aai-ob-provider-local${selectedProvider === 'ollama' ? ' selected' : ''}`}
          onClick=${() => selectProvider('ollama')}
        >
          <strong>${isDE ? '🏠 Ollama — Komplett lokal' : '🏠 Ollama — Fully local'}</strong>
          <p style="font-size:12px;color:var(--text-muted);margin-top:4px">${ollamaDescription}</p>
        </div>

        ${cloudProviders.map((p) => html`
          <div
            key=${p.id}
            class=${`aai-ob-provider${selectedProvider === p.id ? ' selected' : ''}`}
            onClick=${() => selectProvider(p.id)}
          >
            <strong>${p.name}</strong>
            <p style="font-size:11px;color:var(--text-muted);margin-top:2px">${p.sub}</p>
          </div>
        `)}
      </div>

      ${selectedProvider && selectedProvider !== 'ollama' ? html`
        <div class="aai-field" style="margin-top:16px">
          <label style="font-size:13px;font-weight:500;color:var(--text-secondary)">
            ${isDE ? 'API-Schlüssel eingeben' : 'Enter API key'}
          </label>
          <div style="display:flex;gap:6px;margin-top:4px">
            <input
              class="aai-input"
              type="password"
              placeholder="sk-..."
              value=${keyValue}
              onInput=${(e) => setKeyValue(e.target.value)}
              style="flex:1;font-family:var(--mono);font-size:13px"
            />
            <button
              class="aai-btn aai-btn--ghost aai-btn--sm"
              onClick=${handleValidate}
              disabled=${validating || !keyValue}
            >${validating ? '…' : (isDE ? 'Testen' : 'Test')}</button>
          </div>
          ${keyStatus ? html`
            <div style=${`margin-top:4px;font-size:12px;color:${keyStatus.color}`}>${keyStatus.text}</div>
          ` : null}
          <p style="font-size:11px;color:var(--text-muted);margin-top:6px">
            ${isDE
              ? 'Den API-Key findest du in deinem Anbieter-Dashboard. AUSTR.AI speichert ihn lokal auf deinem Rechner.'
              : 'Find your API key in your provider dashboard. AUSTR.AI stores it locally on your machine.'}
          </p>
        </div>
      ` : null}

      ${selectedProvider === 'ollama' && !ollamaAvailable ? html`
        <div style="background:var(--bg-sidebar);border-radius:var(--r-md);padding:14px;margin-top:14px;font-size:13px">
          ${!ollamaRunning ? html`
            <p style="margin-bottom:8px"><strong>${isDE ? 'Ollama installieren:' : 'Install Ollama:'}</strong></p>
            <div style="background:#1e1e2e;border-radius:var(--r-sm);padding:8px 12px;font-family:var(--mono);font-size:12px;color:#e0e0e0;margin-bottom:8px">
              ${isDE ? 'Lade Ollama herunter: ' : 'Download Ollama: '}
              <a href="https://ollama.com" target="_blank" style="color:var(--accent)">ollama.com</a>
            </div>
          ` : null}
          <p style="margin-bottom:8px"><strong>${isDE ? 'Ein Modell herunterladen:' : 'Download a model:'}</strong></p>
          <div style="background:#1e1e2e;border-radius:var(--r-sm);padding:8px 12px;font-family:var(--mono);font-size:12px;color:#e0e0e0">
            ollama pull llama3.2
          </div>
          <p style="font-size:11px;color:var(--text-muted);margin-top:8px">
            ${isDE ? 'Danach diese Seite neu laden.' : 'Then reload this page.'}
          </p>
        </div>
      ` : null}
    </div>
  `;
}

function ReadyStep({ isDE }) {
  return html`
    <div class="aai-ob-step active" style="text-align:center">
      <div class="aai-ob-icon" style="margin:0 auto"><span dangerouslySetInnerHTML=${{ __html: SVG_CHECK }} /></div>
      <h2>${isDE ? 'Alles bereit!' : 'All set!'}</h2>
      <p style="font-size:15px;color:var(--text-secondary);max-width:360px;margin:0 auto;line-height:1.7">
        ${isDE
          ? 'Du kannst jetzt loschatten. Alles wird automatisch geschützt. Einstellungen, Tutorial und Werkzeuge findest du in der Seitenleiste.'
          : 'You can start chatting now. Everything is automatically protected. Settings, tutorial, and tools are in the sidebar.'}
      </p>
    </div>
  `;
}

/* ---- Main Onboarding Component ---- */

function Onboarding({ onFinish }) {
  const [step, setStep] = useState(0);
  const [providers, setProviders] = useState({});
  const [selectedProvider, setSelectedProvider] = useState('');
  const [keyValue, setKeyValue] = useState('');
  const [keyStatus, setKeyStatus] = useState(null);

  const isDE = getLang() === 'de';

  // Load providers on mount, auto-select Ollama if available
  useEffect(() => {
    (async () => {
      try {
        const p = await api.getProviders();
        setProviders(p);
        if (p.ollama?.configured && p.ollama.models?.length) {
          setSelectedProvider('ollama');
        }
      } catch { /* offline: empty providers */ }
    })();
  }, []);

  function handleNext() {
    if (step === 1 && !selectedProvider) {
      toast(isDE ? 'Bitte wähle einen KI-Anbieter' : 'Please select an AI provider', 'error');
      return;
    }
    if (step === 1 && selectedProvider !== 'ollama' && !keyValue) {
      toast(isDE ? 'Bitte gib einen API-Schlüssel ein' : 'Please enter an API key', 'error');
      return;
    }
    setStep(step + 1);
  }

  async function handleFinish() {
    const data = {
      default_provider: selectedProvider,
      ollama_url: DEFAULT_OLLAMA_URL,
    };

    if (selectedProvider !== 'ollama' && keyValue) {
      data[`${selectedProvider}_api_key`] = keyValue;
    }

    // Pick default model from the selected provider
    const prov = providers[selectedProvider];
    if (prov?.models?.length) {
      data.default_model = prov.models[0].id;
    }

    try {
      await api.putSettings(data);
      const [newSettings, newProviders] = await Promise.all([api.getSettings(), api.getProviders()]);
      batch({
        settings: newSettings,
        providers: newProviders,
        provider: selectedProvider,
        model: data.default_model || '',
        onboardingDone: true,
      });
      onFinish();
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  return html`
    <div class="aai-onboarding">
      <div class="aai-ob-progress">
        <div class=${`aai-ob-dot${step >= 0 ? ' current' : ''}`}></div>
        <div class=${`aai-ob-dot${step >= 1 ? ' current' : ''}`}></div>
        <div class=${`aai-ob-dot${step >= 2 ? ' current' : ''}`}></div>
      </div>

      ${step === 0 ? html`<${WelcomeStep} isDE=${isDE} />` : null}
      ${step === 1 ? html`<${ProviderStep}
        isDE=${isDE}
        providers=${providers}
        selectedProvider=${selectedProvider}
        setSelectedProvider=${setSelectedProvider}
        keyValue=${keyValue}
        setKeyValue=${setKeyValue}
        keyStatus=${keyStatus}
        setKeyStatus=${setKeyStatus}
      />` : null}
      ${step === 2 ? html`<${ReadyStep} isDE=${isDE} />` : null}

      <div class="aai-ob-footer">
        <span class="aai-ob-step-label">${step + 1} / 3</span>
        <div class="aai-ob-buttons">
          ${step > 0 ? html`<button class="aai-btn aai-btn--ghost" onClick=${() => setStep(step - 1)}>${isDE ? 'Zurück' : 'Back'}</button>` : null}
          ${step < 2
            ? html`<button class="aai-btn aai-btn--primary" onClick=${handleNext}>${isDE ? 'Weiter' : 'Next'}</button>`
            : html`<button class="aai-btn aai-btn--primary aai-btn--lg" onClick=${handleFinish}>${isDE ? 'Loslegen' : 'Get started'}</button>`
          }
        </div>
      </div>
    </div>
  `;
}

/* ---- Exports ---- */

let overlay;

export function init() {
  overlay = document.getElementById('onboarding-overlay');
}

export function show() {
  if (!overlay) return;
  overlay.hidden = false;
  render(
    html`<${Onboarding} onFinish=${() => { overlay.hidden = true; render(null, overlay); }} />`,
    overlay
  );
}
