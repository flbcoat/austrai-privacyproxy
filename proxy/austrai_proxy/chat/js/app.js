/**
 * AUSTR.AI — Application Entry Point
 * Imports all modules, loads initial state, wires global events.
 * Page-based navigation (no modals for settings/tutorial).
 */

import { get, set, on, batch, toast } from './state.js';
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

async function boot() {
  // Initialize all components
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

  // Load initial data
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
    document.getElementById('msg-input').placeholder = t('placeholder');

    // Show onboarding if first run or no provider configured
    const hasAnyProvider = Object.values(providersData).some(p => p.configured);
    if (!settingsData.onboarding_done || !hasAnyProvider) {
      onboarding.show();
    }

  } catch (err) {
    console.error('AUSTR.AI boot error:', err);
    document.getElementById('msg-input').placeholder = t('errConnection');
  }
}

/* ---- View Management: only one view visible at a time ---- */

const ALL_VIEWS = ['welcome-view', 'chat-view', 'tool-view', 'settings-view', 'tutorial-view'];

function hideAllViews() {
  ALL_VIEWS.forEach(id => { const el = document.getElementById(id); if (el) el.hidden = true; });
}

function showView(viewId) {
  hideAllViews();
  const el = document.getElementById(viewId);
  if (el) el.hidden = false;
  // Show/hide input area (only for chat/welcome)
  const inputArea = document.getElementById('input-area');
  if (inputArea) inputArea.hidden = (viewId !== 'chat-view' && viewId !== 'welcome-view');
  // Show/hide provider selector
  const provSel = document.getElementById('provider-selector');
  if (provSel) provSel.style.visibility = (viewId === 'settings-view' || viewId === 'tutorial-view' || viewId === 'tool-view') ? 'hidden' : '';
}

function findFirstConfigured(providers) {
  for (const pid of ['ollama', 'anthropic', 'openai', 'mistral', 'google']) {
    if (providers[pid]?.configured) return pid;
  }
  return null;
}

/* ---- Header Dropdowns ---- */

function populateProviderDropdowns(providers, activeProvider, activeModel) {
  const selProvider = document.getElementById('sel-provider');
  const selModel = document.getElementById('sel-model');

  selProvider.innerHTML = Object.entries(providers).map(([pid, prov]) => {
    const configured = prov.configured ? '' : ' (—)';
    return `<option value="${pid}" ${pid === activeProvider ? 'selected' : ''}>${prov.name}${configured}</option>`;
  }).join('');

  updateModelDropdown(providers, activeProvider, activeModel);

  selProvider.onchange = () => {
    const pid = selProvider.value;
    set('provider', pid);
    const prov = providers[pid] || {};
    const models = prov.models || [];
    const firstModel = models.length ? models[0].id : '';
    updateModelDropdown(providers, pid, firstModel);
    set('model', firstModel);
    if (firstModel) {
      toast(`${prov.name} — ${models.find(m => m.id === firstModel)?.name || firstModel}`, 'info', 2000);
    }
  };

  selModel.onchange = () => {
    const modelId = selModel.value;
    set('model', modelId);
    const modelName = selModel.options[selModel.selectedIndex]?.text || modelId;
    toast(`Modell: ${modelName}`, 'info', 1500);
  };
}

function updateModelDropdown(providers, providerId, activeModel) {
  const selModel = document.getElementById('sel-model');
  const models = providers[providerId]?.models || [];
  selModel.innerHTML = models.length
    ? models.map(m => `<option value="${m.id}" ${m.id === activeModel ? 'selected' : ''}>${m.name}</option>`).join('')
    : '<option value="">—</option>';
}

// Expose showView globally so settings/tutorial can use it
window.__aai_showView = showView;

/* ---- Global Events ---- */

function wireGlobalEvents() {
  const sidebarEl = document.getElementById('sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');

  // Sidebar toggle (mobile: overlay, desktop: collapse)
  document.getElementById('btn-sidebar-toggle').addEventListener('click', () => {
    if (window.innerWidth <= 768) {
      sidebarEl.classList.toggle('open');
      backdrop.classList.toggle('open');
    } else {
      sidebarEl.classList.toggle('collapsed');
    }
  });

  // Close sidebar on backdrop click (mobile)
  backdrop.addEventListener('click', () => {
    sidebarEl.classList.remove('open');
    backdrop.classList.remove('open');
  });

  // Mode switcher (Chat / Werkzeuge)
  document.querySelectorAll('.aai-sidebar-nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const mode = btn.dataset.mode;
      document.querySelectorAll('.aai-sidebar-nav-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const isTool = mode === 'tools';

      if (isTool) {
        showView('tool-view');
        anonymize.init();
      } else {
        const viewId = get('currentConversationId') ? 'chat-view' : 'welcome-view';
        showView(viewId);
      }

      // Show/hide sidebar chat elements
      const newChatBtn = document.getElementById('btn-new-chat');
      if (newChatBtn) newChatBtn.hidden = isTool;
      const convList = document.getElementById('conversation-list');
      if (convList) convList.hidden = isTool;

      // Close sidebar on mobile
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
    if (e.key === 'Escape') {
      if (get('privacyPanelOpen')) set('privacyPanelOpen', false);
    }
  });

  // Provider/model state sync
  on('provider', (provider) => {
    const sel = document.getElementById('sel-provider');
    if (sel && sel.value !== provider) sel.value = provider;
  });
  on('model', (model) => {
    const sel = document.getElementById('sel-model');
    if (sel && sel.value !== model) sel.value = model;
  });
  on('providers', (providers) => {
    populateProviderDropdowns(providers, get('provider'), get('model'));
  });
}

// Boot
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
