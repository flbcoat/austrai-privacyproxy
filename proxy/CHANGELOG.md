# CHANGELOG

## 3.2.1 — 2026-04-27

Polish-Patch direkt nach 3.2.0.

- **Bug-Fix**: „Im neuen Tab öffnen" bei geschwärzten Bildern hat in Safari/Chrome nichts gemacht — Browser hatten den programmatischen `<a>.click()` als Popup blockiert. Ersetzt durch echtes Anchor-Tag mit `target="_blank"`, klickt jetzt zuverlässig.
- **Neu**: Token-Limit-Warnung. Wenn das Modell die Antwort wegen `max_tokens` abschneidet, erscheint unter der Antwort ein gelber Banner mit Erklärung und einem **Weiter**-Button, der die Generierung mit „Bitte mach weiter, wo du aufgehört hast" fortsetzt. Plus Hinweis, dass `max_tokens` in Settings → Erweitert dauerhaft erhöht werden kann.
- Stop-Reason wird jetzt vom Backend (Anthropic `message_delta.stop_reason`, OpenAI `choices[0].finish_reason`) im SSE-`done`-Event mitgeschickt und auf der Message persistiert.

## 3.2.0 — 2026-04-27

Großes Architektur-Update. Auto-Routing wurde aus dem Default-UX entfernt und durch deklarative Mechanismen ersetzt: Slash-Befehle, Skills und Wissensbasis. Detection-Layer für österreichische Inhalte stark erweitert.

### Neu

- **Skills**: User-definierte „Profis" mit System-Prompt + Modell-Empfehlung. Anlegen und verwalten in Settings → Skills, aktivieren via Header-Dropdown oder `/<skill-slug>` Slash-Befehl. Skill-Inhalte laufen durch dieselbe Anonymisierungs-Pipeline wie User-Messages.
- **Wissensbasis (Projekte)**: Lokale Dokument-Indizierung mit anonymisierten Chunks. Drag-and-Drop Upload (PDF, Docx, Txt), automatische Anonymisierung vor Indexierung. Während des Tippens werden passende Stellen via Live-Search vorgeschlagen, beim Send automatisch angehängt. Originaltext-Vorschau lokal rehydriert; das LLM bekommt nur anonymisierten Text.
- **Slash-Befehle**: User-definierte Aliase für Modell- und Skill-Wechsel pro Nachricht. Position-locked: nur als erstes Token einer leeren Eingabe. Standard-Aliase: `/opus`, `/sonnet`, `/haiku`, `/lokal`.
- **Reasoning sichtbar**: Extended-Thinking-Output von Claude und o-series wird in einem aufklappbaren Block über der Antwort angezeigt.
- **Inspector + Inline-Deny-Liste**: Pro Wissensbasis-Dokument können die anonymisierten Chunks geprüft und übersehene Begriffe direkt in die globale Deny-Liste übernommen werden. Re-Index läuft mit erweiterten Termen.
- **Header-Dropdowns**: Neben Provider/Modell stehen jetzt Skill und Wissensbasis als Selektoren.
- **Upload-Progress**: Drei-Phasen-Anzeige (Upload → Anonymisieren → Fertig) statt nur „lädt…".

### Detection-Layer

- 5 neue Custom-Recognizer für österreichische Patterns:
  - `AustrianAddressRecognizer`: Straße + Hausnummer + PLZ + Ort, mit drei Match-Pässen
  - `AustrianStateAndCityRecognizer`: 9 Bundesländer + 17 große Städte
  - `AustrianAcademicTitleRecognizer`: Ing., Dr., Mag., Univ.-Prof., DDr., BA, MA, MSc, etc.
  - `AustrianEducationalInstitutionRecognizer`: 50+ Universitäten, Fachhochschulen, Schultypen
  - `AustrianPublicBodyRecognizer`: 60+ Behörden, Ministerien, Gerichte, Sozialversicherung, Banken, NPOs
- 10 neue zero-shot GLiNER-Labels für österreichische Domain (university, school, government agency, academic title, academic degree, street address, postal code, NPO, company, URL).

### Bug-Fixes

- Anthropic-API-Fehler: temperature und top_p werden für Anthropic-Modelle nicht mehr beide gesendet (Anthropic akzeptiert nur eines).
- Sonnet 4.5 datiert (`claude-sonnet-4-5-20250929`): adaptive Thinking wird nicht mehr fälschlich gesetzt; datierte IDs nutzen das Legacy-`thinking_budget`-Format.
- Header-Modell-Anzeige zeigt nicht mehr „—", wenn der persistierte `default_model` nicht in der dynamisch geladenen Provider-Liste steht.
- De-Anonymisierung der Wissensbasis: Mappings werden pro Chunk gespeichert und beim Send gemergt, sodass der Rehydrator Codenames aus Doc-Kontext korrekt zurückübersetzt.
- Delete-Buttons in Wissensbasis: zwei-Klick-Inline-Confirm statt `confirm()` (Browser können Letzteres unterdrücken).

### Geändert

- Auto-Routing-Toggle aus Settings → Erweitert entfernt. `auto_route`-Flag in der Config bleibt parsbar, ist aber off-by-default und nicht mehr im UI sichtbar.
- Settings → Erweitert konditioniert jetzt Reasoning-/Temperature-/Top-P-Slider basierend auf den Capabilities des aktiven Modells (o-series gräyt Temperature aus, Anthropic gräyt Top-P aus, Modelle ohne Reasoning gräyen den Reasoning-Slider aus).
- Wissensbasis-Vorschau: kompakter Status-Indikator („📚 N passende Stellen aus „Projekt" werden mitgesendet") statt Vorschau-Liste mit Checkboxen. Auf-Klick zeigt rehydrierten Klartext für den User. Das LLM bekommt unverändert nur anonymisierten Text.

### Privacy-Architektur (unverändert garantiert)

- Skill-System-Prompts laufen durch die Anonymisierungs-Pipeline.
- Wissensbasis-Dokumente werden VOR der Indexierung anonymisiert; chromadb/sqlite hält nur anonymisierte Chunks.
- Mappings im Fernet-encrypted MappingStore.
- Keine Cloud-Abhängigkeiten für Skills oder Wissensbasis.
