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

    // Sidebar navigation
    modeChat: 'Chat',
    modeTools: 'Werkzeuge',
    helpTutorial: 'Hilfe & Tutorial',
    newChatDefault: 'Neuer Chat',

    // Tutorial / FAQ — komplette Hilfe-Sektion
    tutBack: '← Zurück',
    tutTitle: 'Hilfe & Tutorial',
    tutIntro: 'AUSTR.AI ist dein KI-Assistent mit eingebautem Datenschutz. Alle Erkennung und Anonymisierung läuft lokal auf deinem Rechner — keine sensiblen Daten verlassen dein Gerät. Klick auf ein Thema unten, um es zu öffnen.',
    tutSectionHow: 'So funktioniert AUSTR.AI',
    tutSectionChat: 'Chatten mit Datenschutz',
    tutSectionAttach: 'Dateien anhängen & befragen',
    tutSectionRedact: 'Bilder und PDFs schwärzen',
    tutSectionToolsTab: 'Werkzeuge-Tab: Standalone-Anonymisierung',
    tutSectionSettings: 'Einstellungen & KI-Anbieter',
    tutSectionDemo: 'Live ausprobieren',
    tutSectionFaq: 'Häufige Fragen',

    tutHowBody1: 'AUSTR.AI schiebt sich zwischen dich und den KI-Anbieter. Bevor deine Nachricht das Gerät verlässt, werden sensible Daten (Namen, Adressen, IBANs, Telefonnummern, medizinische Begriffe …) durch Platzhalter und Codenames ersetzt. Die KI antwortet auf der anonymisierten Fassung, und in der Antwort werden die Platzhalter wieder durch deine Originalbegriffe ersetzt.',
    tutHowBody2: 'Was die KI also zu sehen bekommt, ist NIE dein Klartext — und trotzdem liest du die Antwort so, als hätte die KI direkt mit deinen Daten gearbeitet. Das Mapping zwischen Codename und Original bleibt ausschließlich lokal in einem AES-verschlüsselten Vault.',
    tutHowFlow: 'Dein Text → Anonymisiert → KI → Antwort → Wiederhergestellt',

    tutChatBody: 'Tippe einfach los wie in jedem anderen KI-Chat. Rechts oben siehst du ein Schild-Symbol mit der Zahl der erkannten Begriffe. Unter jeder gesendeten Nachricht wird als Badge angezeigt, welche Typen anonymisiert wurden (PERSON, AT_IBAN, DATE_OF_BIRTH …).',
    tutChatPreview: 'Vor dem Absenden kannst du auf das Augen-Symbol neben dem Sende-Button klicken — dann siehst du die Anonymisierung als Vorschau und kannst einzelne Begriffe noch ergänzen oder zurücknehmen.',
    tutChatRename: 'Tipp: Jede Konversation wird automatisch nach deiner ersten Nachricht oder dem Dateinamen benannt. Hover in der Seitenleiste, klick auf das Stift-Icon oder Doppelklick auf den Titel, um umzubenennen.',

    tutAttachBody: 'Büroklammer im Chat-Input → Menü öffnet sich mit zwei Optionen:',
    tutAttachOpt1: 'Datei anhängen — PDF, DOCX, Excel, TXT, Bild oder Audio. Wird sofort anonymisiert; du siehst Original + anonymisierten Volltext nebeneinander. Die rechte Seite ist editierbar, falls die Automatik einen Begriff übersehen hat.',
    tutAttachOpt2: 'Bild / PDF schwärzen — pixelgenaue Maskierung ohne Chat. Ergebnis als Thumbnail-Vorschau mit Download-Button.',
    tutAttachDrag: 'Alternativ: einfach eine Datei ins Fenster ziehen — sie wird automatisch als Anhang behandelt.',

    tutRedactBody: 'Das Schwärzen funktioniert auf zwei Wegen:',
    tutRedactPath1: 'Im Chat (Büroklammer → Schwärzen): Das geschwärzte Bild erscheint als Chat-Message mit 250×250 Vorschau, Klick aufs Bild öffnet es in voller Größe im neuen Tab.',
    tutRedactPath2: 'Im Werkzeuge-Tab → "Bild schwärzen": Gleiches Ergebnis, aber ohne Konversation — ideal wenn du nur das geschwärzte Bild brauchst und nicht darüber chatten willst.',
    tutRedactFormats: 'Unterstützte Formate: PNG, JPG, TIFF, BMP, WebP, PDF.',

    tutToolsTabBody: 'Der Werkzeuge-Tab links in der Seitenleiste ist für "Ich will nur schnell anonymisieren, kein Chat". Vier Karten:',
    tutToolsCard1: 'Text anonymisieren → führt in den Chat mit Live-Preview',
    tutToolsCard2: 'Excel analysieren → Tabellen werden anonymisiert, Zahlen bleiben erhalten',
    tutToolsCard3: 'Dokument anonymisieren → PDF/DOCX/TXT, Ergebnis als Volltext-Split mit editierbarer rechter Seite',
    tutToolsCard4: 'Bild schwärzen → pixelgenaue Maskierung, Download als PNG',
    tutToolsTabNote: 'Ergebnisse bleiben lokal — es wird weder eine Konversation angelegt noch etwas in der Seitenleiste gespeichert.',

    tutSettingsBody: 'Klick unten links auf Einstellungen. Dort konfigurierst du:',
    tutSettingsProvider: 'KI-Anbieter: Anthropic Claude, OpenAI GPT, Mistral, Google Gemini, Ollama (lokal), LM Studio (lokal). Für maximale Privatsphäre: Ollama oder LM Studio — dann verlässt nicht ein einziges Byte deinen Rechner.',
    tutSettingsAllow: 'Allow-Liste: Begriffe, die nie anonymisiert werden sollen (z.B. dein eigener Name in einem Rollenspiel).',
    tutSettingsDeny: 'Deny-Liste: zusätzliche Begriffe, die immer anonymisiert werden, auch wenn die Automatik sie nicht erkennt.',
    tutSettingsThreshold: 'Erkennungs-Schwelle: wie empfindlich die Detection sein soll.',
    tutSettingsLang: 'Sprache DE/EN: betrifft nur die UI — die Erkennung arbeitet mehrsprachig.',

    tutDemoIntro: 'Gib Text mit persönlichen Daten ein und sieh live, was erkannt wird. Der Text verlässt deinen Browser nicht.',
    tutDemoExampleBtn: 'Beispiel laden',
    tutDemoExampleText: 'Dr. Müller wohnt in der Mariahilfer Straße 45, 1060 Wien. Seine IBAN ist AT48 2011 1820 8120 0100 und seine Mail ist mueller@example.at',
    tutDemoPlaceholder: 'Text mit Namen, Adressen, IBANs, E-Mails eingeben…',
    tutDemoButton: 'Anonymisieren',
    tutDemoLoading: 'Wird analysiert…',
    tutDemoNone: 'Keine personenbezogenen Daten erkannt',
    tutDemoNoneHint: 'Dieser Text würde unverändert an die KI gehen.',
    tutDemoAnonymized: '{n} Begriff(e) anonymisiert',
    tutDemoOrig: 'Dein Text',
    tutDemoSeen: 'Was die KI sieht',
    tutDemoReplacements: 'Ersetzungen',

    faqQ1: 'Verlassen meine Daten wirklich nie den Rechner?',
    faqA1: 'Die Erkennung und Anonymisierung läuft 100% lokal auf deinem Gerät. An den KI-Anbieter gehen ausschließlich die anonymisierten Texte. Wenn du einen lokalen Provider wie Ollama oder LM Studio nutzt, bleibt überhaupt alles auf deinem Rechner.',

    faqQ2: 'Wie erkennt AUSTR.AI, was sensibel ist?',
    faqA2: 'Drei Erkennungs-Schichten arbeiten parallel: (1) GLiNER — ein moderner Transformer-basierter PII-Detector mit F1=0,98 auf Standard-Benchmarks, (2) Presidio + spaCy für klassische NER, (3) Österreich-spezifische Regex-Recognizer für IBAN, UID-Nummer, SVNr, Firmenbuchnummer, Kennzeichen. Die Schichten ergänzen sich, damit nichts durchrutscht.',

    faqQ3: 'Was sind diese "Codenames" statt der echten Namen?',
    faqA3: 'Personen-Entitäten werden nicht durch generische Platzhalter wie [PERSON_1] ersetzt, sondern durch frei erfundene Codenames ("Arion", "Brynn", "Nexon Corp"). Das hilft dem LLM, natürlichen Satzfluss zu produzieren — sonst würde es um "[PERSON_1]" herum holpern. Bei strukturierten Daten (IBAN, Datum, Telefonnummer) wird aber ein typisierter Bracket-Code wie [AT_IBAN_1], [DATE_OF_BIRTH_1] verwendet, damit die KI das Format versteht.',

    faqQ4: 'Kann die KI erraten, wer hinter einem Codename steckt?',
    faqA4: 'Durch Context-Kombination wäre das theoretisch möglich, darum haben wir 4 Schutzstufen mit gestaffelten TTLs: Public (24h), Internal (1h), Confidential (30min), Restricted (5min). In medizinischen oder juristischen Kontexten werden Entitäten automatisch auf eine höhere Stufe angehoben. Codenames werden nach Ablauf gelöscht, neue Anfragen erzeugen neue Codenames.',

    faqQ5: 'Was passiert, wenn AUSTR.AI einen Begriff übersehen hat?',
    faqA5: 'Für Attachments: die rechte Textarea nach dem Upload ist editierbar — du kannst jeden Begriff manuell durch einen Platzhalter ersetzen bevor du eine Frage stellst. Generell: füge den Begriff in den Einstellungen zur Deny-Liste hinzu, dann wird er ab sofort immer anonymisiert. Umgekehrt: Allow-Liste für Begriffe, die fälschlich erkannt werden (z.B. dein eigener Name in einem Kreativ-Kontext).',

    faqQ6: 'Warum sieht die KI-Antwort manchmal komische Codenames?',
    faqA6: 'Die automatische Rehydrierung tauscht Codenames in der Antwort wieder gegen deine Originalbegriffe aus. Wenn ein Codename in der Antwort nicht exakt dem anonymisierten Original entspricht (fuzzy match unterhalb der Schwelle), bleibt er stehen. Unter der Nachricht steht "X von Y Begriffen wiederhergestellt" — der Rest ist im Raw-Response-Button sichtbar.',

    faqQ7: 'Welche Dateien kann ich hochladen?',
    faqA7: 'Als Anhang: PDF, DOCX, Excel/CSV, TXT, PNG/JPG, MP3/WAV/M4A (Audio wird transkribiert). Zum Schwärzen: PNG, JPG, TIFF, BMP, WebP, PDF. Gescannte PDFs ohne Textschicht werden automatisch durch OCR (Tesseract) verarbeitet.',

    faqQ8: 'Welche KI-Anbieter sind unterstützt?',
    faqA8: 'Anthropic Claude, OpenAI GPT (inkl. o3/o4-mini), Mistral, Google Gemini, Ollama und LM Studio. Für die lokalen Anbieter brauchst du keinen API-Key; für die Cloud-Anbieter trägst du den Key einmalig in den Einstellungen ein (wird lokal mit Fernet/AES verschlüsselt).',

    faqQ9: 'Was kostet AUSTR.AI?',
    faqA9: 'AUSTR.AI selbst ist für Privatnutzer und Unternehmen bis 10 Mitarbeiter:innen kostenlos. Größere Organisationen brauchen eine kommerzielle Lizenz — Kontakt: info@austr.ai. Die Kosten der KI-Anbieter (z.B. Anthropic API) trägst du natürlich selbst.',

    faqQ10: 'Wo werden meine Gespräche gespeichert?',
    faqA10: 'Ausschließlich lokal auf deinem Gerät — in einer AES-verschlüsselten SQLite-Datenbank. Nichts geht an AUSTR.AI-Server (die gibt\'s für deine Daten gar nicht — austr.ai ist nur eine Demo-Website). Du kannst jede Konversation in der Seitenleiste löschen; der Vault wird sofort bereinigt.',
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

    // Sidebar navigation
    modeChat: 'Chat',
    modeTools: 'Tools',
    helpTutorial: 'Help & Tutorial',
    newChatDefault: 'New Chat',

    // Tutorial / FAQ
    tutBack: '← Back',
    tutTitle: 'Help & Tutorial',
    tutIntro: 'AUSTR.AI is your AI assistant with built-in privacy. All detection and anonymization runs locally on your machine — no sensitive data ever leaves your device. Click any topic below to expand it.',
    tutSectionHow: 'How AUSTR.AI works',
    tutSectionChat: 'Chatting with privacy',
    tutSectionAttach: 'Attach & ask about files',
    tutSectionRedact: 'Redact images and PDFs',
    tutSectionToolsTab: 'Tools tab: standalone anonymization',
    tutSectionSettings: 'Settings & AI providers',
    tutSectionDemo: 'Try it live',
    tutSectionFaq: 'Frequently asked questions',

    tutHowBody1: 'AUSTR.AI sits between you and the AI provider. Before your message leaves the device, sensitive data (names, addresses, IBANs, phone numbers, medical terms …) is replaced with placeholders and codenames. The AI responds to the anonymized version, and the response is automatically re-hydrated with your original terms.',
    tutHowBody2: 'So what the AI sees is NEVER your cleartext — and you still read the response as if the AI worked directly with your data. The mapping between codename and original stays exclusively in an AES-encrypted local vault.',
    tutHowFlow: 'Your text → Anonymized → AI → Response → Re-hydrated',

    tutChatBody: 'Type away like in any other AI chat. Top right you\'ll see a shield icon with the count of detected terms. Under every sent message a badge shows which types were anonymized (PERSON, AT_IBAN, DATE_OF_BIRTH …).',
    tutChatPreview: 'Before sending, click the eye icon next to the send button — you\'ll see the anonymization as a preview and can add or remove individual terms.',
    tutChatRename: 'Tip: every conversation is automatically titled after your first message or the uploaded filename. Hover in the sidebar, click the pencil icon, or double-click the title to rename.',

    tutAttachBody: 'Paperclip in the chat input → a menu opens with two options:',
    tutAttachOpt1: 'Attach file — PDF, DOCX, Excel, TXT, image or audio. Anonymized instantly; you see original + anonymized full text side by side. The right pane is editable in case automation missed a term.',
    tutAttachOpt2: 'Redact image / PDF — pixel-accurate masking without chat. Result as thumbnail preview with download button.',
    tutAttachDrag: 'Or just drag a file into the window — it\'s automatically handled as an attachment.',

    tutRedactBody: 'Redaction works two ways:',
    tutRedactPath1: 'In chat (Paperclip → Redact): the redacted image appears as a chat message with a 250×250 thumbnail; click opens it full-size in a new tab.',
    tutRedactPath2: 'In the Tools tab → "Redact Image": same result, but no conversation is created — ideal when you just need the redacted image without chatting about it.',
    tutRedactFormats: 'Supported formats: PNG, JPG, TIFF, BMP, WebP, PDF.',

    tutToolsTabBody: 'The Tools tab on the left is for "I just want to anonymize quickly, no chat". Four cards:',
    tutToolsCard1: 'Anonymize Text → switches to chat with live preview',
    tutToolsCard2: 'Analyze Excel → tables anonymized, numbers preserved',
    tutToolsCard3: 'Anonymize Document → PDF/DOCX/TXT, result as full-text split with editable right pane',
    tutToolsCard4: 'Redact Image → pixel-accurate masking, download as PNG',
    tutToolsTabNote: 'Results stay local — no conversation is created and nothing is saved to the sidebar.',

    tutSettingsBody: 'Click Settings at the bottom left. You can configure:',
    tutSettingsProvider: 'AI Provider: Anthropic Claude, OpenAI GPT, Mistral, Google Gemini, Ollama (local), LM Studio (local). For maximum privacy: use Ollama or LM Studio — not a single byte leaves your machine.',
    tutSettingsAllow: 'Allow list: terms that should never be anonymized (e.g. your own name in a role-play).',
    tutSettingsDeny: 'Deny list: extra terms always anonymized, even if automation missed them.',
    tutSettingsThreshold: 'Detection threshold: how sensitive the detection should be.',
    tutSettingsLang: 'Language DE/EN: affects the UI only — detection works multilingual.',

    tutDemoIntro: 'Enter text with personal data and see live what\'s detected. The text never leaves your browser.',
    tutDemoExampleBtn: 'Load example',
    tutDemoExampleText: 'Dr. Smith lives at 123 Main Street, New York. His IBAN is AT48 2011 1820 8120 0100 and his email is smith@example.com',
    tutDemoPlaceholder: 'Enter text with names, addresses, IBANs, emails…',
    tutDemoButton: 'Anonymize',
    tutDemoLoading: 'Analyzing…',
    tutDemoNone: 'No personal data detected',
    tutDemoNoneHint: 'This text would be sent to the AI unchanged.',
    tutDemoAnonymized: '{n} term(s) anonymized',
    tutDemoOrig: 'Your text',
    tutDemoSeen: 'What the AI sees',
    tutDemoReplacements: 'Replacements',

    faqQ1: 'Does my data really never leave my machine?',
    faqA1: 'Detection and anonymization run 100% locally on your device. Only anonymized text is sent to the AI provider. If you use a local provider like Ollama or LM Studio, nothing leaves your machine at all.',

    faqQ2: 'How does AUSTR.AI detect what\'s sensitive?',
    faqA2: 'Three detection layers work in parallel: (1) GLiNER — a modern transformer-based PII detector with F1=0.98 on standard benchmarks, (2) Presidio + spaCy for classical NER, (3) Austria-specific regex recognizers for IBAN, UID number, SVNr, company registry number, license plates. The layers overlap so nothing slips through.',

    faqQ3: 'What are these "codenames" instead of real names?',
    faqA3: 'Person entities aren\'t replaced with generic placeholders like [PERSON_1], but with made-up codenames ("Arion", "Brynn", "Nexon Corp"). This helps the LLM produce natural-sounding text — it would stumble around a raw [PERSON_1]. For structured data (IBAN, date, phone) a typed bracket code like [AT_IBAN_1], [DATE_OF_BIRTH_1] is used so the AI understands the format.',

    faqQ4: 'Could the AI guess who\'s behind a codename?',
    faqA4: 'Through context combination it\'s theoretically possible, so we have 4 protection levels with graduated TTLs: Public (24h), Internal (1h), Confidential (30min), Restricted (5min). In medical or legal contexts, entities are automatically upgraded one level. Codenames expire; new requests produce fresh codenames.',

    faqQ5: 'What if AUSTR.AI missed a term?',
    faqA5: 'For attachments: the right-side textarea after upload is editable — you can manually replace any term with a placeholder before asking a question. More generally: add the term to the Deny list in Settings and it will always be anonymized from now on. Conversely: use the Allow list for terms that are falsely detected (e.g. your own name in a creative context).',

    faqQ6: 'Why do AI responses sometimes show weird codenames?',
    faqA6: 'Automatic rehydration swaps codenames in the response back to your original terms. If a codename in the response doesn\'t exactly match the anonymized original (fuzzy match below threshold), it stays. Below the message you\'ll see "X of Y terms restored" — the rest is visible via the Raw Response button.',

    faqQ7: 'Which files can I upload?',
    faqA7: 'As attachment: PDF, DOCX, Excel/CSV, TXT, PNG/JPG, MP3/WAV/M4A (audio is transcribed). For redaction: PNG, JPG, TIFF, BMP, WebP, PDF. Scanned PDFs without text layer are automatically processed via OCR (Tesseract).',

    faqQ8: 'Which AI providers are supported?',
    faqA8: 'Anthropic Claude, OpenAI GPT (incl. o3/o4-mini), Mistral, Google Gemini, Ollama, and LM Studio. Local providers need no API key; for cloud providers you enter the key once in Settings (stored locally, AES-encrypted via Fernet).',

    faqQ9: 'What does AUSTR.AI cost?',
    faqA9: 'AUSTR.AI itself is free for private users and businesses with up to 10 people. Larger organizations need a commercial license — contact: info@austr.ai. You pay the AI providers (e.g. Anthropic API) directly.',

    faqQ10: 'Where are my conversations stored?',
    faqA10: 'Exclusively on your local device — in an AES-encrypted SQLite database. Nothing is sent to AUSTR.AI servers (there aren\'t any for your data — austr.ai is only a demo site). You can delete any conversation in the sidebar; the vault is cleared immediately.',
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
