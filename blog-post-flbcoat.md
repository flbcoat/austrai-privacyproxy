# Blog-Post fuer FLB.CO.AT
## Titel-Optionen (SEO-optimiert):
- "AUSTR.AI: Warum ich eine Open-Source Privacy Firewall fuer KI gebaut habe"
- "KI nutzen ohne Daten preiszugeben — AUSTR.AI PrivacyProxy"
- "DSGVO und ChatGPT: So schuetzt AUSTR.AI sensible Daten automatisch"

---

## AUSTR.AI: Warum ich eine Open-Source Privacy Firewall fuer KI gebaut habe

*Von Florian Bieche, FLB.CO.AT — Maerz 2026*

### Das Problem: Jeder Prompt ist ein Datenleck

In meiner taeglichen Arbeit als KI-Berater sehe ich dasselbe Muster: Unternehmen wollen KI nutzen — fuer E-Mails, Zusammenfassungen, Analysen, Vertragspruefungen. Aber jedes Mal, wenn ein Mitarbeiter einen Text in ChatGPT, Claude oder Copilot eingibt, landen potenziell sensible Daten auf Servern in den USA.

Kundennamen, IBANs, Sozialversicherungsnummern, Diagnosen, Vertragsdetails — all das wird an LLM-Anbieter uebermittelt und dort teilweise bis zu 30 Tage gespeichert. Fuer europaeische Unternehmen ist das ein DSGVO-Risiko, das kaum jemand auf dem Schirm hat.

### Die Loesung: Anonymisierung vor dem Absenden

Deshalb habe ich [AUSTR.AI PrivacyProxy](https://austr.ai) entwickelt — eine Open-Source Privacy Firewall, die sensible Daten erkennt und anonymisiert, **bevor** sie das eigene Netzwerk verlassen.

Der Ansatz: Statt "Thomas Gruber, IBAN AT48 3200 0000 1234 5678" sieht die KI nur "Arion, IBAN [AT_IBAN_1]". Die Antwort kommt mit Codenames zurueck und wird lokal wieder mit den echten Daten angereichert.

### Was AUSTR.AI von anderen Tools unterscheidet

Es gibt bereits PII-Detection-Tools — Lakera, Private AI, Microsoft Purview. Aber die sind Cloud-Dienste fuer Konzerne. AUSTR.AI ist anders:

**Komplett lokal**: Andere Tools senden deine Daten an ihre Cloud zur Analyse. AUSTR.AI laeuft zu 100% auf deinem Rechner. Nichts verlaesst dein Netzwerk.

**3-Schichten-Erkennung**: Kein einzelnes Tool ist perfekt. Deshalb kombiniert AUSTR.AI drei Erkennungsschichten: GLiNER (ein spezialisiertes NER-Modell mit F1 0.98), Microsoft Presidio mit 2.200+ Vornamen-Datenbank, und optional ein lokales LLM ueber Ollama. Was eine Schicht uebersieht, faengt die naechste auf.

**Nicht-rueckverfolgbare Codenames**: Die meisten Tools ersetzen Namen durch [REDACTED] oder Fake-Namen wie "Yuki Tanaka". Problem: Ein LLM erkennt sofort, dass das ein japanischer Name ist und koennte Rueckschluesse ziehen. AUSTR.AI nutzt abstrakte Codenames wie "Arion" — erfunden, sprachlos, nicht zurueckuebersetzbar.

**Bidirektionale Pipeline**: Anonymisierung ist nur die halbe Miete. AUSTR.AI setzt die echten Daten in der KI-Antwort automatisch wieder ein — auch bei Streaming-Responses.

### Zwei Wege, AUSTR.AI zu nutzen

**Fuer Privatanwender: Die Chat-Oberflaeche**
`aai start` startet die lokale Chat-UI im Browser. Text anonymisieren, an eine KI senden, Antwort deanonymisieren. Alles in einem Fenster, kein Copy-Paste noetig. Mit automatischer Datenklassifizierung (4 Schutzklassen) und zeitlich begrenztem Mapping-Vault.

**Fuer Unternehmen: Der API-Proxy**
Der selbe Befehl startet auch einen transparenten Proxy auf Port 8282. Anwendungen wie Cursor, Continue oder eigene Apps werden einfach auf diesen Endpunkt umkonfiguriert. Ab dann anonymisiert der Proxy jeden Request und stellt jede Response automatisch wieder her — transparent, ohne dass Mitarbeiter etwas tun muessen.

### Open Source, kostenlos, aus Oesterreich

AUSTR.AI steht unter MIT-Lizenz. Keine Lizenzgebuehren, keine Nutzerlimits, keine Telemetrie. Der gesamte Code ist auf [GitHub](https://github.com/flbcoat/austrai-privacyproxy) einsehbar und auditierbar.

Installation: `pip install austrai`

Das Projekt ist aus meiner taeglichen Beratungsarbeit bei [FLB.CO.AT](https://flb.co.at) entstanden. Wenn Sie Unterstuetzung bei der Integration in Ihre Infrastruktur brauchen — ob als API-Proxy, Chat-Loesung oder Docker-Deployment — [kontaktieren Sie mich](https://flb.co.at).

### Links

- Website: [austr.ai](https://austr.ai)
- GitHub: [github.com/flbcoat/austrai-privacyproxy](https://github.com/flbcoat/austrai-privacyproxy)
- PyPI: [pypi.org/project/austrai/](https://pypi.org/project/austrai/)
- KI-Beratung: [flb.co.at](https://flb.co.at)

---

## SEO-Empfehlungen fuer den Blog-Post auf FLB.CO.AT

### Meta-Tags:
```html
<title>AUSTR.AI: Open-Source Privacy Firewall fuer KI — DSGVO-konform | FLB.CO.AT</title>
<meta name="description" content="AUSTR.AI PrivacyProxy schuetzt sensible Daten in KI-Prompts. Open Source, komplett lokal, DSGVO-konform. Entwickelt von Florian Bieche, FLB.CO.AT Wien." />
<meta name="keywords" content="AUSTR.AI, KI Datenschutz, DSGVO KI, Austria AI, Oesterreich KI, ChatGPT Datenschutz, Privacy Firewall, KI Sicherheit, AI Security, Florian Bieche, FLB.CO.AT" />
```

### Interne Links die von FLB.CO.AT auf AUSTR.AI zeigen sollten:
- Haupt-Blogpost → https://austr.ai (Homepage)
- "Installation" Text → https://pypi.org/project/austrai/
- "GitHub" → https://github.com/flbcoat/austrai-privacyproxy
- Navigation/Footer auf FLB.CO.AT → "AUSTR.AI" Link

### Gegenlinks die von AUSTR.AI auf FLB.CO.AT zeigen (bereits eingebaut):
- Footer: "KI-Beratung" → https://flb.co.at
- About-Sektion: Florian Bieche Link → https://flb.co.at
- About-Sektion: "Mehr erfahren auf FLB.CO.AT" Button → https://flb.co.at
- JSON-LD Schema: author.url → https://flb.co.at
- JSON-LD Schema: parentOrganization.url → https://flb.co.at
