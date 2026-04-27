/**
 * AUSTR.AI — Settings Page (Preact)
 * Full-page view: provider config, API keys, privacy settings.
 */

import { h, render, Fragment } from 'preact';
import { useState, useEffect } from 'preact/hooks';
import htm from 'htm';
import { signals, batch, toast } from './state.js';
import * as api from './api.js';
import { t, setLang } from './i18n.js';
import { SkillsTab, KnowledgeTab, SlashAliasesEditor } from './skills_kb.js';

const html = htm.bind(h);

const PROVIDER_IDS = ['anthropic', 'openai', 'mistral', 'google', 'ollama', 'lmstudio'];
const PROVIDER_LABEL_KEYS = {
  anthropic: 'pAnthropic', openai: 'pOpenai', mistral: 'pMistral', google: 'pGoogle',
  ollama: 'pOllama', lmstudio: 'pLmStudio',
};

// Setup-Anleitungen pro Provider. Werden direkt in der ProviderCard angezeigt.
// Cloud-APIs: kurze Anleitung wie man an einen Key kommt.
// Lokale Runner: was vor dem Verbinden installiert/gestartet sein muss.
const PROVIDER_HELP = {
  anthropic: {
    de: 'Account auf console.anthropic.com → Settings → API Keys → "Create Key". Schlüssel beginnt mit sk-ant-.',
    en: 'Sign up at console.anthropic.com → Settings → API Keys → "Create Key". Key starts with sk-ant-.',
  },
  openai: {
    de: 'Account auf platform.openai.com → API Keys → "Create new secret key". Schlüssel beginnt mit sk-.',
    en: 'Sign up at platform.openai.com → API Keys → "Create new secret key". Key starts with sk-.',
  },
  mistral: {
    de: 'Account auf console.mistral.ai → API Keys. Mistral hat einen kostenlosen Tier.',
    en: 'Sign up at console.mistral.ai → API Keys. Mistral has a free tier.',
  },
  google: {
    de: 'Account auf aistudio.google.com → "Get API Key". Gemini hat einen großzügigen kostenlosen Tier.',
    en: 'Sign up at aistudio.google.com → "Get API Key". Gemini has a generous free tier.',
  },
  ollama: {
    de: 'Ollama von ollama.com/download installieren. Die Mac-App startet den Server automatisch im Hintergrund — du musst nichts ausführen. Falls "address already in use" beim Start kommt: Server läuft bereits, einfach hier prüfen. Modelle mit "ollama pull llama3.2" im Terminal laden. URL: http://localhost:11434 (nur die Basis, kein /api oder /v1).',
    en: 'Install Ollama from ollama.com/download. The Mac app auto-starts the server in the background — nothing to launch. If "address already in use" appears: the server is already running, just press Validate here. Pull models with "ollama pull llama3.2" in terminal. URL: http://localhost:11434 (base only, no /api or /v1).',
  },
  lmstudio: {
    de: 'LM Studio von lmstudio.ai installieren → App öffnen → Tab "Local Server" oder "Developer" → "Start Server". URL bleibt meist http://localhost:1234 (nur die Basis, ohne /v1). Modelle musst du in der App selbst laden bevor sie hier erscheinen.',
    en: 'Install LM Studio from lmstudio.ai → open app → "Local Server" or "Developer" tab → "Start Server". URL stays http://localhost:1234 (base only, no /v1). Models must be loaded in-app before they appear here.',
  },
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

function ProviderCard({ pid, prov, draftKey, onKeyChange, ollamaUrl, onOllamaUrlChange, lmstudioUrl, onLmStudioUrlChange }) {
  const isOllama = pid === 'ollama';
  const isLmStudio = pid === 'lmstudio';
  const isLocal = isOllama || isLmStudio;
  const configured = prov.configured;
  const statusClass = configured ? 'aai-provider-status--ok' : 'aai-provider-status--none';
  const statusText = configured ? '✓' : '—';
  const lang = signals.language.value === 'de' ? 'de' : 'en';
  const helpText = PROVIDER_HELP[pid]?.[lang];

  const [status, setStatus] = useState(null); // {valid, message}
  const [validating, setValidating] = useState(false);

  async function handleValidate() {
    setValidating(true);
    setStatus(null);
    try {
      let result;
      if (isOllama) result = await api.validateKey('ollama', '', ollamaUrl);
      else if (isLmStudio) result = await api.validateKey('lmstudio', '', undefined, lmstudioUrl);
      else result = await api.validateKey(pid, draftKey);
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
        <span class="aai-provider-name">${t(PROVIDER_LABEL_KEYS[pid]) || pid}</span>
        <span class=${`aai-provider-status ${statusClass}`}>${statusText}</span>
      </div>
      ${helpText ? html`
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;line-height:1.5;padding:6px 10px;background:var(--bg-subtle);border-radius:4px">
          ${helpText}
        </div>
      ` : null}
      ${isOllama ? html`
        <div class="aai-field">
          <label>${signals.language.value === 'de' ? 'Ollama URL' : 'Ollama URL'}</label>
          <div class="aai-key-row">
            <input
              class="aai-input"
              placeholder="http://localhost:11434"
              value=${ollamaUrl}
              onInput=${(e) => onOllamaUrlChange(e.target.value)}
            />
            <button class="aai-btn aai-btn--ghost aai-btn--sm" onClick=${handleValidate} disabled=${validating}>
              ${validating ? '…' : t('validate')}
            </button>
          </div>
        </div>
      ` : isLmStudio ? html`
        <div class="aai-field">
          <label>${signals.language.value === 'de' ? 'LM Studio URL' : 'LM Studio URL'}</label>
          <div class="aai-key-row">
            <input
              class="aai-input"
              placeholder="http://localhost:1234"
              value=${lmstudioUrl}
              onInput=${(e) => onLmStudioUrlChange(e.target.value)}
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
        </div>
      `}
      ${status && !isLocal ? html`
        <div
          class="aai-key-status"
          style=${`margin-top:4px;font-size:12px;color:${status.valid ? 'var(--success)' : 'var(--danger)'}`}
        >${status.valid ? '✓' : '✗'} ${status.message}</div>
      ` : null}
      ${status && isLocal ? html`
        <div
          style=${`margin-top:4px;font-size:12px;color:${status.valid ? 'var(--success)' : 'var(--danger)'}`}
        >${status.valid ? '✓' : '✗'} ${status.message}</div>
      ` : null}
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
  const [lmstudioUrl, setLmStudioUrl] = useState(settings.lmstudio_url || 'http://localhost:1234');
  // Default provider/model are set via the chat header dropdown (which
  // persists on change). Removed from Settings UI to avoid the
  // "two places for one thing" UX problem.
  const [threshold, setThreshold] = useState(settings.confidence_threshold ?? 0.5);
  const [allowList, setAllowList] = useState(settings.allow_list || []);
  const [denyList, setDenyList] = useState(settings.deny_list || []);
  const [confirmSend, setConfirmSendLocal] = useState(getConfirmSend());

  // Advanced-mode state (opt-in; keeps basic UI uncluttered)
  const [advancedMode, setAdvancedMode] = useState(!!settings.advanced_mode);
  const [slashCommands, setSlashCommands] = useState(!!settings.slash_commands);
  const [slashAliases, setSlashAliases] = useState(settings.slash_aliases || {});
  const [reasoningEffort, setReasoningEffort] = useState(settings.reasoning_effort || 'medium');
  const [temperature, setTemperature] = useState(
    settings.temperature !== undefined ? settings.temperature : 1.0,
  );
  const [topP, setTopP] = useState(settings.top_p !== undefined ? settings.top_p : 1.0);
  const [maxTokens, setMaxTokens] = useState(settings.max_tokens || 4096);
  const routerStages = (providers && providers._meta && providers._meta.router_stages) || {
    local_llm: false, embeddings: false, rules: true,
  };

  function handleKeyChange(pid, value) {
    setDraftKeys({ ...draftKeys, [pid]: value });
  }

  async function handleSave() {
    const data = {
      ollama_url: ollamaUrl,
      lmstudio_url: lmstudioUrl,
      confidence_threshold: parseFloat(threshold),
      allow_list: allowList,
      deny_list: denyList,
      // Advanced mode + its params are always sent, so disabling the master
      // toggle cleanly resets the runtime back to basic-mode defaults.
      advanced_mode: advancedMode,
      auto_route: false,
      slash_commands: advancedMode && slashCommands,
      slash_aliases: slashAliases,
      reasoning_effort: reasoningEffort,
      temperature: parseFloat(temperature),
      top_p: parseFloat(topP),
      max_tokens: parseInt(maxTokens, 10) || 4096,
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
        // Do NOT override provider/model here — the chat header owns those
        // and persists them directly. Settings-save only touches the other
        // tabs' fields (privacy, advanced, keys).
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
        <div style="display:flex;align-items:center;gap:12px">
          <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--text-secondary)">
            ${signals.language.value === 'de' ? 'Sprache' : 'Language'}
            <select
              class="aai-select"
              style="padding:4px 8px;font-size:13px"
              value=${signals.language.value}
              onChange=${(e) => setLang(e.target.value)}
            >
              <option value="de">Deutsch</option>
              <option value="en">English</option>
            </select>
          </label>
          <button class="aai-btn aai-btn--ghost aai-btn--sm" onClick=${onClose}>
            ${signals.language.value === 'de' ? '← Zurück' : '← Back'}
          </button>
        </div>
      </div>

      <div class="aai-tabs" role="tablist">
        <button class=${`aai-tab${tab === 'providers' ? ' active' : ''}`} role="tab" onClick=${() => setTab('providers')}>
          ${t('tabProviders')}
        </button>
        <button class=${`aai-tab${tab === 'privacy' ? ' active' : ''}`} role="tab" onClick=${() => setTab('privacy')}>
          ${t('tabPrivacy')}
        </button>
        <button class=${`aai-tab${tab === 'skills' ? ' active' : ''}`} role="tab" onClick=${() => setTab('skills')}>
          ${signals.language.value === 'de' ? 'Skills' : 'Skills'}
        </button>
        <button class=${`aai-tab${tab === 'knowledge' ? ' active' : ''}`} role="tab" onClick=${() => setTab('knowledge')}>
          ${signals.language.value === 'de' ? 'Wissensbasis' : 'Knowledge'}
        </button>
        <button class=${`aai-tab${tab === 'advanced' ? ' active' : ''}`} role="tab" onClick=${() => setTab('advanced')}>
          ${signals.language.value === 'de' ? 'Erweitert' : 'Advanced'}
        </button>
      </div>

      ${tab === 'skills' ? html`<${SkillsTab} />` : null}
      ${tab === 'knowledge' ? html`<${KnowledgeTab} />` : null}

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
              lmstudioUrl=${lmstudioUrl}
              onLmStudioUrlChange=${setLmStudioUrl}
            />
          `)}

          <div style="font-size:12px;color:var(--text-muted);margin-top:8px;padding:8px 12px;background:var(--bg-subtle);border-radius:6px">
            ${signals.language.value === 'de'
              ? '💡 Dein Standard-Modell wählst du direkt im Dropdown über dem Chat. Die Auswahl wird automatisch als Standard gespeichert.'
              : '💡 Pick your default model in the dropdown above the chat. The selection is automatically saved as your default.'}
          </div>
        </div>
      ` : null}

      ${tab === 'advanced' ? html`
        <div class="aai-tab-content active">
          <!-- Intro / Warnung: Power-User-Bereich -->
          <div style="background:var(--bg-subtle);border-left:3px solid var(--accent);padding:12px 16px;margin-bottom:16px;border-radius:4px">
            <div style="font-weight:500;margin-bottom:4px">
              ${signals.language.value === 'de'
                ? 'Erweiterte Einstellungen (für Power-User)'
                : 'Advanced settings (power users)'}
            </div>
            <p style="font-size:12px;color:var(--text-muted);margin:0">
              ${signals.language.value === 'de'
                ? 'Du brauchst das hier nicht, um AUSTR.AI zu nutzen. Die Defaults funktionieren für alle gängigen Aufgaben. Schalte den erweiterten Modus nur ein, wenn du bewusst an Modell-Wahl, Reasoning-Tiefe oder Sampling-Parametern drehen willst.'
                : 'You do not need this to use AUSTR.AI. Defaults work well for everyday tasks. Only enable advanced mode if you deliberately want to tune model selection, reasoning depth or sampling.'}
            </p>
          </div>

          <div class="aai-field">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
              <input
                type="checkbox"
                style="accent-color:var(--accent);width:16px;height:16px"
                checked=${advancedMode}
                onChange=${(e) => setAdvancedMode(e.target.checked)}
              />
              <span style="font-weight:500">
                ${signals.language.value === 'de'
                  ? 'Erweiterten Modus aktivieren'
                  : 'Enable advanced mode'}
              </span>
            </label>
          </div>

          ${advancedMode ? html`
            <!-- Sektion 1: Slash-Befehle (Power-User) -->
            <div style="border:1px solid var(--border);border-radius:8px;padding:12px 16px;margin-bottom:12px">
              <div style="font-weight:500;margin-bottom:4px">
                ${signals.language.value === 'de' ? '1 · Slash-Befehle' : '1 · Slash commands'}
              </div>
              <p style="font-size:12px;color:var(--text-muted);margin:0 0 10px 0">
                ${signals.language.value === 'de'
                  ? 'Erlaubt schnelle Modell- und Skill-Wechsel direkt im Chat. Ein Befehl wird nur erkannt, wenn er als erstes in einer leeren Eingabe steht. „/haiku" mitten im Text bleibt normaler Inhalt.'
                  : 'Lets you switch model or skill quickly from the chat. A command is only recognised when it is the first token of an otherwise-empty input. "/haiku" mid-text stays content.'}
              </p>
              <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
                <input
                  type="checkbox"
                  style="accent-color:var(--accent);width:16px;height:16px"
                  checked=${slashCommands}
                  onChange=${(e) => setSlashCommands(e.target.checked)}
                />
                <span>
                  ${signals.language.value === 'de'
                    ? 'Slash-Befehle aktivieren'
                    : 'Enable slash commands'}
                </span>
              </label>
              ${slashCommands ? html`
                <div style="font-size:12px;color:var(--text-muted);margin-top:10px;padding:8px 12px;background:var(--bg-subtle);border-radius:4px;line-height:1.6">
                  <div style="font-weight:500;margin-bottom:4px">
                    ${signals.language.value === 'de' ? 'Befehls-Aliase' : 'Command aliases'}
                  </div>
                  <div style="font-size:11px;opacity:0.8">
                    ${signals.language.value === 'de'
                      ? 'Definiere selbst, welcher Befehl welches Modell auswählt. Provider/Modell aus deinen konfigurierten Quellen. Skill-Befehle (/<slug>) funktionieren automatisch, sobald ein Skill angelegt ist.'
                      : 'Define which command picks which model. Provider/model from your configured sources. Skill commands (/<slug>) work automatically once a skill exists.'}
                  </div>
                  <${SlashAliasesEditor}
                    value=${slashAliases}
                    onChange=${setSlashAliases}
                    providers=${providers}
                    lang=${signals.language.value}
                  />
                </div>
              ` : null}
            </div>

            <!-- Sektion 2: Modell-Verhalten -->
            ${(() => {
              // Capabilities for the currently active model. providers[pid]
              // ships annotated_models with `reasoning_type`, `supports_temperature`,
              // `tier` so we can switch UI sections on/off based on what the
              // chosen model actually accepts.
              const _activePid = signals.provider.value || '';
              const _activeMid = signals.model.value || '';
              const _modelEntry = (providers && providers[_activePid] && (providers[_activePid].models || []).find((m) => m.id === _activeMid)) || null;
              const _supportsReasoning = _modelEntry?.reasoning_type ? true : false;
              const _supportsTemperature = _modelEntry ? _modelEntry.supports_temperature !== false : true;
              // Anthropic API rejects sending both temperature and top_p together.
              const _isAnthropic = _activePid === 'anthropic';
              const _supportsTopP = _supportsTemperature && !_isAnthropic;
              return html`
              <div style="border:1px solid var(--border);border-radius:8px;padding:12px 16px;margin-bottom:12px">
                <div style="font-weight:500;margin-bottom:4px">
                  ${signals.language.value === 'de' ? '2 · Modell-Verhalten' : '2 · Model behavior'}
                </div>
                <p style="font-size:12px;color:var(--text-muted);margin:0 0 12px 0">
                  ${signals.language.value === 'de'
                    ? html`Aktives Modell im Header: <code>${_activePid || '–'} / ${_activeMid || '–'}</code>. Felder, die das Modell nicht unterstützt, sind ausgegraut.`
                    : html`Active model in header: <code>${_activePid || '–'} / ${_activeMid || '–'}</code>. Fields the model does not support are greyed out.`}
                </p>

                <div class="aai-field" style="opacity:${_supportsReasoning ? '1' : '0.4'}">
                  <label>
                    ${signals.language.value === 'de' ? 'Reasoning-Tiefe' : 'Reasoning depth'}
                    ${!_supportsReasoning ? html`<span style="color:var(--text-muted);font-weight:normal;font-size:11px;margin-left:6px">${signals.language.value === 'de' ? '(Modell unterstützt kein Reasoning)' : '(model has no reasoning)'}</span>` : null}
                  </label>
                  <select
                    class="aai-select"
                    style="width:100%"
                    value=${reasoningEffort}
                    disabled=${!_supportsReasoning}
                    onChange=${(e) => setReasoningEffort(e.target.value)}
                  >
                    <option value="off">${signals.language.value === 'de' ? 'Aus (kein Extended Thinking)' : 'Off (no extended thinking)'}</option>
                    <option value="low">${signals.language.value === 'de' ? 'Niedrig (~1k Tokens Denkbudget)' : 'Low (~1k thinking tokens)'}</option>
                    <option value="medium">${signals.language.value === 'de' ? 'Mittel (~4k Tokens Denkbudget)' : 'Medium (~4k thinking tokens)'}</option>
                    <option value="high">${signals.language.value === 'de' ? 'Hoch (~16k Tokens Denkbudget)' : 'High (~16k thinking tokens)'}</option>
                  </select>
                  ${_supportsReasoning ? html`
                    <p style="font-size:11px;color:var(--text-muted);margin-top:4px">
                      ${signals.language.value === 'de'
                        ? html`Reasoning-Typ dieses Modells: <code>${_modelEntry.reasoning_type}</code>. Der Denk-Block wird im Chat sichtbar gemacht.`
                        : html`Reasoning type for this model: <code>${_modelEntry.reasoning_type}</code>. The thinking block is shown inline in the chat.`}
                    </p>
                  ` : null}
                </div>

                <div class="aai-field" style="opacity:${_supportsTemperature ? '1' : '0.4'}">
                  <label>
                    ${signals.language.value === 'de' ? 'Temperature (Kreativität, 0 = streng, 2 = wild)' : 'Temperature (creativity, 0 = strict, 2 = wild)'}
                    ${!_supportsTemperature ? html`<span style="color:var(--text-muted);font-weight:normal;font-size:11px;margin-left:6px">${signals.language.value === 'de' ? '(o-series ignoriert Temperature)' : '(o-series ignores temperature)'}</span>` : null}
                  </label>
                  <div class="aai-slider-wrap">
                    <span class="aai-slider-label">0.0</span>
                    <input
                      type="range"
                      min="0" max="2" step="0.1"
                      value=${temperature}
                      disabled=${!_supportsTemperature}
                      onInput=${(e) => setTemperature(e.target.value)}
                    />
                    <span class="aai-slider-label">2.0</span>
                    <span class="aai-slider-value">${temperature}</span>
                  </div>
                </div>

                <div class="aai-field" style="opacity:${_supportsTopP ? '1' : '0.4'}">
                  <label>
                    Top-P ${signals.language.value === 'de' ? '(Wortwahl-Breite, 1.0 = volles Vokabular)' : '(vocabulary breadth, 1.0 = full)'}
                    ${!_supportsTopP ? html`<span style="color:var(--text-muted);font-weight:normal;font-size:11px;margin-left:6px">${_isAnthropic ? (signals.language.value === 'de' ? '(Anthropic akzeptiert nicht Temperature + Top-P gemeinsam — wird gedroppt)' : '(Anthropic disallows temperature + top-p together — dropped)') : (signals.language.value === 'de' ? '(Modell ignoriert Top-P)' : '(model ignores top-p)')}</span>` : null}
                  </label>
                  <div class="aai-slider-wrap">
                    <span class="aai-slider-label">0.0</span>
                    <input
                      type="range"
                      min="0" max="1" step="0.05"
                      value=${topP}
                      disabled=${!_supportsTopP}
                      onInput=${(e) => setTopP(e.target.value)}
                    />
                    <span class="aai-slider-label">1.0</span>
                    <span class="aai-slider-value">${topP}</span>
                  </div>
                </div>

                <div class="aai-field">
                  <label>${signals.language.value === 'de' ? 'Max. Tokens pro Antwort' : 'Max tokens per response'}</label>
                  <input
                    type="number"
                    class="aai-input"
                    min="128" max="200000" step="128"
                    value=${maxTokens}
                    onInput=${(e) => setMaxTokens(e.target.value)}
                  />
                </div>
              </div>
              `;
            })()}

            <!-- Kurz-Anleitung -->
            <div style="font-size:12px;color:var(--text-muted);padding:12px 16px;background:var(--bg-subtle);border-radius:6px">
              <div style="font-weight:500;margin-bottom:6px;color:var(--text-primary)">
                ${signals.language.value === 'de' ? 'Kurz-Anleitung' : 'Quick guide'}
              </div>
              <ul style="margin:0;padding-left:18px;line-height:1.6">
                <li>${signals.language.value === 'de'
                  ? html`<strong>Slash-Befehle</strong> aktivieren, wenn du pro Nachricht ein anderes Modell oder einen Skill via /alias-Befehl wählen willst. Funktioniert nur, wenn der Befehl als Erstes in einer leeren Eingabe steht.`
                  : html`Enable <strong>slash commands</strong> to switch model or skill per message via /alias. Works only if the command is the first token in an otherwise-empty input.`}</li>
                <li>${signals.language.value === 'de'
                  ? html`<strong>Reasoning-Tiefe</strong> erhöhen bei komplexen Aufgaben (Beweise, Multi-Step-Analyse). Niedrig halten für Alltag — spart Zeit und Kosten. Wirkt nur bei Modellen, die Reasoning unterstützen.`
                  : html`Raise <strong>reasoning depth</strong> for complex tasks (proofs, multi-step analysis). Keep low for everyday use — saves time and cost. Only affects models that support reasoning.`}</li>
                <li>${signals.language.value === 'de'
                  ? html`<strong>Temperature</strong> niedrig (0.2–0.5) für Fakten, hoch (1.0–1.5) für kreatives Schreiben. Wird ignoriert bei o-series.`
                  : html`Lower <strong>temperature</strong> (0.2–0.5) for factual tasks, higher (1.0–1.5) for creative writing. Ignored for o-series.`}</li>
                <li>${signals.language.value === 'de'
                  ? 'Privacy-Garantie bleibt aktiv: Alle Modelle und alle Skill-/Wissensbasis-Inhalte sehen nur anonymisierten Text, nie Klartext.'
                  : 'Privacy guarantee unchanged: every model and every skill/KB payload sees only anonymized text, never raw input.'}</li>
              </ul>
            </div>
          ` : null}
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
