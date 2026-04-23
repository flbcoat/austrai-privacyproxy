/**
 * AUSTR.AI — Internationalization (DE / EN)
 */

const T = {
  de: {
    appName: 'AUSTR.AI',
    appTagline: 'Dein KI-Assistent mit eingebautem Datenschutz',
    newChat: 'Neuer Chat',
    conversations: 'Gespräche',
    noConversations: 'Noch keine Gespräche',
    deleteConv: 'Löschen',
    settings: 'Einstellungen',

    // Welcome
    welcomeTitle: 'Willkommen bei AUSTR.AI',
    welcomeSub: 'Chatte mit KI — deine Daten bleiben privat.',
    toolAnonymize: 'Dokument anonymisieren',
    toolAnonymizeDesc: 'Lade eine Datei hoch und sieh, welche Daten erkannt werden',
    toolRedact: 'Bild schwärzen',
    toolRedactDesc: 'Persönliche Daten in Bildern automatisch schwärzen',
    chipExplain: 'Erkläre mir ein Konzept',
    chipAnalyze: 'Analysiere dieses Dokument',
    chipRedact: 'Schwärze ein Bild',
    chipPrivacy: 'Wie funktioniert der Datenschutz?',

    // Chat
    placeholder: 'Nachricht eingeben…',
    send: 'Senden',
    stop: 'Stopp',
    thinking: 'Denkt nach…',
    copy: 'Kopieren',
    copied: 'Kopiert!',
    regenerate: 'Neu generieren',

    // Privacy
    privacyBadge: '{n} Begriffe anonymisiert',
    privacyBadge1: '1 Begriff anonymisiert',
    privacyNone: 'Keine Anonymisierung nötig',
    privacyRestored: '{n} Begriffe wiederhergestellt',
    privacyPanel: 'Datenschutz-Info',
    entitiesDetected: 'Erkannte Entitäten',
    allowAdd: 'Zur Allow-List',
    allowTitle: 'Allow-List',
    denyTitle: 'Deny-List',
    dismiss: 'Ignorieren',
    dismissPerm: 'Dauerhaft ignorieren',

    // Upload
    uploadHint: 'Datei hierher ziehen oder klicken',
    uploadProcessing: 'Wird verarbeitet…',
    uploadResult: 'Anonymisiertes Ergebnis',
    attachFile: 'Datei anhängen',
    formats: 'PDF, DOCX, XLSX, TXT, CSV, PNG, JPG, MP3, WAV',
    removeAttachment: 'Entfernen',

    // Settings
    settingsTitle: 'Einstellungen',
    tabProviders: 'KI-Anbieter',
    tabPrivacy: 'Datenschutz',
    apiKey: 'API-Schlüssel',
    apiKeyPh: 'Schlüssel eingeben…',
    validate: 'Testen',
    keyValid: 'Gültig',
    keyInvalid: 'Ungültig',
    ollamaUrl: 'Ollama URL',
    defaultProvider: 'Standard-Anbieter',
    defaultModel: 'Standard-Modell',
    threshold: 'Erkennungs-Schwelle',
    thresholdLow: 'Empfindlich',
    thresholdHigh: 'Strikt',
    allowList: 'Allow-List (nicht anonymisieren)',
    denyList: 'Deny-List (immer anonymisieren)',
    addTerm: 'Begriff hinzufügen…',
    save: 'Speichern',
    cancel: 'Abbrechen',
    close: 'Schließen',

    // Onboarding
    obTitle: 'AUSTR.AI einrichten',
    step: 'Schritt',
    of: 'von',
    next: 'Weiter',
    back: 'Zurück',
    finish: 'Los geht\'s',
    skip: 'Überspringen',
    ob1Title: 'Willkommen bei AUSTR.AI',
    ob1Text: 'Dein KI-Assistent mit eingebautem Datenschutz. Persönliche Daten werden automatisch anonymisiert, bevor sie an KI-Anbieter gesendet werden.',
    ob2Title: 'Wähle deinen KI-Anbieter',
    ob2Text: 'Nutze einen Cloud-Anbieter oder Ollama für komplett lokale Verarbeitung.',
    ob3Title: 'API-Schlüssel einrichten',
    ob3Text: 'Gib deinen API-Schlüssel ein. Bei Ollama ist kein Schlüssel nötig.',
    ob4Title: 'Datenschutz-Einstellungen',
    ob4Text: 'Lege fest, wie empfindlich die Erkennung sein soll.',
    ob5Title: 'Alles bereit!',
    ob5Text: 'Du kannst jetzt loslegen. Alle Einstellungen lassen sich jederzeit ändern.',

    // Providers
    pAnthropic: 'Anthropic (Claude)',
    pOpenai: 'OpenAI (GPT)',
    pMistral: 'Mistral',
    pGoogle: 'Google (Gemini)',
    pOllama: 'Ollama (lokal)',

    // Errors
    errConnection: 'Verbindungsfehler — ist der Server gestartet?',
    errStream: 'Streaming-Fehler',
    errUpload: 'Upload fehlgeschlagen',
    errNoProvider: 'Kein Anbieter konfiguriert',
  },

  en: {
    appName: 'AUSTR.AI',
    appTagline: 'Your AI assistant with built-in privacy',
    newChat: 'New Chat',
    conversations: 'Conversations',
    noConversations: 'No conversations yet',
    deleteConv: 'Delete',
    settings: 'Settings',

    welcomeTitle: 'Welcome to AUSTR.AI',
    welcomeSub: 'Chat with AI — your data stays private.',
    toolAnonymize: 'Anonymize Document',
    toolAnonymizeDesc: 'Upload a file and see which data is detected',
    toolRedact: 'Redact Image',
    toolRedactDesc: 'Automatically redact personal data in images',
    chipExplain: 'Explain a concept to me',
    chipAnalyze: 'Analyze this document',
    chipRedact: 'Redact an image',
    chipPrivacy: 'How does the privacy work?',

    placeholder: 'Type a message…',
    send: 'Send',
    stop: 'Stop',
    thinking: 'Thinking…',
    copy: 'Copy',
    copied: 'Copied!',
    regenerate: 'Regenerate',

    privacyBadge: '{n} terms anonymized',
    privacyBadge1: '1 term anonymized',
    privacyNone: 'No anonymization needed',
    privacyRestored: '{n} terms restored',
    privacyPanel: 'Privacy Info',
    entitiesDetected: 'Entities Detected',
    allowAdd: 'Add to allow list',
    allowTitle: 'Allow List',
    denyTitle: 'Deny List',
    dismiss: 'Dismiss',
    dismissPerm: 'Dismiss permanently',

    uploadHint: 'Drag file here or click to upload',
    uploadProcessing: 'Processing…',
    uploadResult: 'Anonymized Result',
    attachFile: 'Attach file',
    formats: 'PDF, DOCX, XLSX, TXT, CSV, PNG, JPG, MP3, WAV',
    removeAttachment: 'Remove',

    settingsTitle: 'Settings',
    tabProviders: 'AI Providers',
    tabPrivacy: 'Privacy',
    apiKey: 'API Key',
    apiKeyPh: 'Enter key…',
    validate: 'Validate',
    keyValid: 'Valid',
    keyInvalid: 'Invalid',
    ollamaUrl: 'Ollama URL',
    defaultProvider: 'Default Provider',
    defaultModel: 'Default Model',
    threshold: 'Detection Threshold',
    thresholdLow: 'Sensitive',
    thresholdHigh: 'Strict',
    allowList: 'Allow List (never anonymize)',
    denyList: 'Deny List (always anonymize)',
    addTerm: 'Add term…',
    save: 'Save',
    cancel: 'Cancel',
    close: 'Close',

    obTitle: 'Set up AUSTR.AI',
    step: 'Step',
    of: 'of',
    next: 'Next',
    back: 'Back',
    finish: 'Let\'s go',
    skip: 'Skip',
    ob1Title: 'Welcome to AUSTR.AI',
    ob1Text: 'Your AI assistant with built-in privacy. Personal data is automatically anonymized before being sent to AI providers.',
    ob2Title: 'Choose your AI provider',
    ob2Text: 'Use a cloud provider or Ollama for fully local processing.',
    ob3Title: 'Set up API key',
    ob3Text: 'Enter your API key. No key needed for Ollama.',
    ob4Title: 'Privacy settings',
    ob4Text: 'Set how sensitive the detection should be.',
    ob5Title: 'All set!',
    ob5Text: 'You\'re ready to go. All settings can be changed anytime.',

    pAnthropic: 'Anthropic (Claude)',
    pOpenai: 'OpenAI (GPT)',
    pMistral: 'Mistral',
    pGoogle: 'Google (Gemini)',
    pOllama: 'Ollama (local)',

    errConnection: 'Connection error — is the server running?',
    errStream: 'Streaming error',
    errUpload: 'Upload failed',
    errNoProvider: 'No provider configured',
  },
};

// Language is driven by signals.language so every component that reads
// signals.language.value re-renders automatically when the user switches
// languages. A persisted preference in localStorage wins over the browser
// default on the next start-up.
import { signals } from './state.js';

const STORED = (() => {
  try { return localStorage.getItem('aai_lang'); } catch { return null; }
})();
const BROWSER = (typeof navigator !== 'undefined' && (navigator.language || '').startsWith('de')) ? 'de' : 'en';
const INITIAL = STORED === 'de' || STORED === 'en' ? STORED : BROWSER;
// Seed the shared signal so state.js defaults are overridden with the
// persisted/browser preference on first access.
signals.language.value = INITIAL;

export function setLang(lang) {
  if (lang !== 'de' && lang !== 'en') return;
  signals.language.value = lang;
  try { localStorage.setItem('aai_lang', lang); } catch { /* ignore */ }
}
export function getLang() { return signals.language.value; }

export function t(key, params = {}) {
  const lang = signals.language.value;
  let text = T[lang]?.[key] || T.en[key] || key;
  for (const [k, v] of Object.entries(params)) {
    text = text.replace(`{${k}}`, v);
  }
  return text;
}
