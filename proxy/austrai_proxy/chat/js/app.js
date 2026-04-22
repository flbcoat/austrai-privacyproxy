/**
 * AUSTR.AI — Application Entry Point
 *
 * Orchestrator. All individual views (Welcome/Sidebar/Privacy/Settings/
 * Onboarding/Tutorial/Debug/Chat/Anonymize/Upload) are already Preact
 * components; this module wires boot, view-switching, keyboard shortcuts,
 * and the static header dropdowns that remain DOM-owned.
 *
 * Signals are the single source of truth. Legacy pub/sub listeners are
 * implemented internally on top of signals (see state.js).
 */

import { signals, batch, toast } from './state.js';
import * as api from './api.js';
import { t } from './i18n.js';

import * as sidebar from './sidebar.js';
import * as welcome from './welcome.js';
import * as chat from './chat.js';
import * as settings from './settings.js';
import * as onboarding from './onboarding.js';
import * as privacy from './privacy.js';
import * as upload from './upload.js';
import * as debug from './debug.js';
import * as anonymize from './anonymize.js';
import * as tutorial from './tutorial.js';

/* ---- View Management ---- */

const ALL_VIEWS = ['welcome-view', 'chat-view', 'tool-view', 'settings-view', 'tutorial-view'];

function hideAllViews() {
  for (const id of ALL_VIEWS) {
    const el = document.getElementById(id);
    if (el) el.hidden = true;
  }
}

function showView(viewId) {
  hideAllViews();
  const el = document.getElementById(viewId);
  if (el) el.hidden = false;

  const inputArea = document.getElementById('input-area');
  if (inputArea) inputArea.hidden = (viewId !== 'chat-view' && viewId !== 'welcome-view');

  const provSel = document.getElementById('provider-selector');
  if (provSel) {
    const hideProvider = viewId === 'settings-view' || viewId === 'tutorial-view' || viewId === 'tool-view';
    provSel.style.visibility = hideProvider ? 'hidden' : '';
  }
}

// Exposed for settings/tutorial/upload to trigger view changes without a circular import.
// Phase 11 intentionally keeps this escape hatch; a future refactor can move view routing
// into a `currentView` signal that the App root listens to.
window.__aai_showView = showView;

/* ---- Header Provider / Model Dropdowns ----
 * These live in static HTML (index.html) and remain DOM-owned. We wire them
 * imperatively and sync via signal subscriptions so that Preact components
 * updating `signals.provider`/`signals.model` are reflected in the UI.
 */

function populateProviderDropdowns(providers, activeProvider, activeModel) {
  const selProvider = document.getElementById('sel-provider');
  const selModel = document.getElementById('sel-model');
  if (!selProvider || !selModel) return;

  selProvider.innerHTML = Object.entries(providers).map(([pid, prov]) => {
    const configured = prov.configured;
    const suffix = configured ? '' : ' (kein Key)';
    const disabled = configured ? '' : 'disabled';
    return `<option value="${pid}" ${pid === activeProvider ? 'selected' : ''} ${disabled}>${prov.name}${suffix}</option>`;
  }).join('');

  updateModelDropdown(providers, activeProvider, activeModel);

  selProvider.onchange = () => {
    const pid = selProvider.value;
    signals.provider.value = pid;
    const prov = providers[pid] || {};
    const models = prov.models || [];
    const firstModel = models.length ? models[0].id : '';
    updateModelDropdown(providers, pid, firstModel);
    signals.model.value = firstModel;
    if (firstModel) {
      toast(`${prov.name} — ${models.find((m) => m.id === firstModel)?.name || firstModel}`, 'info', 2000);
    }
  };

  selModel.onchange = () => {
    const modelId = selModel.value;
    signals.model.value = modelId;
    const modelName = selModel.options[selModel.selectedIndex]?.text || modelId;
    toast(`Modell: ${modelName}`, 'info', 1500);
  };
}

function updateModelDropdown(providers, providerId, activeModel) {
  const selModel = document.getElementById('sel-model');
  if (!selModel) return;
  const models = providers[providerId]?.models || [];
  selModel.innerHTML = models.length
    ? models.map((m) => `<option value="${m.id}" ${m.id === activeModel ? 'selected' : ''}>${m.name}</option>`).join('')
    : '<option value="">—</option>';
}

function findFirstConfigured(providers) {
  for (const pid of ['ollama', 'anthropic', 'openai', 'mistral', 'google']) {
    if (providers[pid]?.configured) return pid;
  }
  return null;
}

/* ---- Global Event Wiring ---- */

function wireGlobalEvents() {
  const sidebarEl = document.getElementById('sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');

  document.getElementById('btn-sidebar-toggle')?.addEventListener('click', () => {
    if (window.innerWidth <= 768) {
      sidebarEl.classList.toggle('open');
      backdrop.classList.toggle('open');
    } else {
      sidebarEl.classList.toggle('collapsed');
    }
  });

  backdrop?.addEventListener('click', () => {
    sidebarEl.classList.remove('open');
    backdrop.classList.remove('open');
  });

  // Mode switcher (Chat / Werkzeuge)
  document.querySelectorAll('.aai-sidebar-nav-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const mode = btn.dataset.mode;
      document.querySelectorAll('.aai-sidebar-nav-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');

      const isTool = mode === 'tools';
      if (isTool) {
        showView('tool-view');
      } else {
        const viewId = signals.currentConversationId.value ? 'chat-view' : 'welcome-view';
        showView(viewId);
      }

      const newChatBtn = document.getElementById('btn-new-chat');
      if (newChatBtn) newChatBtn.hidden = isTool;
      const convList = document.getElementById('conversation-list');
      if (convList) convList.hidden = isTool;

      if (window.innerWidth <= 768) {
        sidebarEl.classList.remove('open');
        backdrop.classList.remove('open');
      }
    });
  });

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
      e.preventDefault();
      sidebar.newChat();
    }
    if (e.key === 'Escape' && signals.privacyPanelOpen.value) {
      signals.privacyPanelOpen.value = false;
    }
  });

  // Reactive sync for header dropdowns. Using `signal.subscribe` directly
  // (skipping the legacy `on()` wrapper) because these are one-off sync
  // effects that should NOT skip the initial value — we want the dropdown
  // to reflect the current signal state on first render too.
  signals.provider.subscribe((provider) => {
    const sel = document.getElementById('sel-provider');
    if (sel && sel.value !== provider) sel.value = provider;
  });
  signals.model.subscribe((model) => {
    const sel = document.getElementById('sel-model');
    if (sel && sel.value !== model) sel.value = model;
  });
  signals.providers.subscribe((providers) => {
    populateProviderDropdowns(providers, signals.provider.value, signals.model.value);
  });

  // View switching based on currentView signal
  signals.currentView.subscribe((view) => {
    if (view === 'chat') showView('chat-view');
    else if (view === 'welcome') showView('welcome-view');
  });
}

/* ---- Boot ---- */

async function boot() {
  sidebar.init();
  welcome.init();
  chat.init();
  settings.init();
  onboarding.init();
  privacy.init();
  upload.init();
  debug.init();
  anonymize.init();
  tutorial.init();

  wireGlobalEvents();

  try {
    const [settingsData, providersData, convs] = await Promise.all([
      api.getSettings(),
      api.getProviders(),
      api.listConversations(),
    ]);

    const provider = settingsData.default_provider || findFirstConfigured(providersData) || 'ollama';
    const provModels = providersData[provider]?.models || [];
    const model = settingsData.default_model || (provModels.length ? provModels[0].id : '');

    batch({
      settings: settingsData,
      providers: providersData,
      conversations: convs,
      provider,
      model,
      onboardingDone: settingsData.onboarding_done,
    });

    populateProviderDropdowns(providersData, provider, model);
    const msgInput = document.getElementById('msg-input');
    if (msgInput) msgInput.placeholder = t('placeholder');

    // Show onboarding on first run or when no provider is configured
    const hasAnyProvider = Object.values(providersData).some((p) => p.configured);
    if (!settingsData.onboarding_done || !hasAnyProvider) {
      onboarding.show();
    }
  } catch (err) {
    console.error('AUSTR.AI boot error:', err);
    const msgInput = document.getElementById('msg-input');
    if (msgInput) msgInput.placeholder = t('errConnection');
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
