# 📘 Benutzer-Handbuch: Hybrid Model Router & Privacy Gate

> **Setup:** Open WebUI auf Minisforum Server &bull; Compute Node via Tailscale (LM Studio Workstation) &bull; Cloud APIs (OpenRouter)
> 
> 📊 **Interaktives Live-Dashboard:**
> - **Tailscale (Team & Remote):** [http://100.116.36.64:8089](http://100.116.36.64:8089)
> - **Lokales Netzwerk (Office LAN):** [http://192.168.168.202:8089](http://192.168.168.202:8089)
> - **Im Agentic Handbuch:** [http://100.116.36.64:8088](http://100.116.36.64:8088) (Direktaufruf-Karte 4 oder [/router/](http://100.116.36.64:8088/router/))

---

## 🌟 1. Was macht dieses System?

Dein KI-System kombiniert zwei Sicherheits- und Performance-Ebenen zu einer vollautomatischen **Hybrid-Orchestrierung** (nach dem Vorbild von *Perplexity Hybrid Compute*):

1. **Datenschutz (Privacy Gate):** Sensible Daten (Namen, Orte, Firmen, E-Mails) werden in der User-Eingabe geschwärzt (`[[NAME_PER_1]]`), bevor ein externes Modell sie sehen kann. Nach der Antwort werden sie automatisch wieder mit den Originaldaten befüllt.
2. **Intelligentes Modell-Routing:** Ein nachgelagertes Gateway entscheidet anhand von **Datenschutzstufe**, **Aufgabentyp (Intent)** und **Komplexität**, wohin die Anfrage gesendet wird:
   - **Lokale Workstation (LM Studio via Tailscale):** Für sensible/kritische Daten, Programmier-Routine, unzensierte Recherchen und Alltags-Chat (**0 Cloud-Credits / gratis**).
   - **Cloud High-End (OpenRouter):** Für hochkomplexe Systemarchitekturen, tiefste Logik und Mammut-Code (Claude Sonnet 4.5 / Opus 4.6), sofern keine kritischen Daten vorliegen.
3. **Automatische Hyperparameter:** Für jedes Modell werden automatisch die optimalen Werte für `temperature` und `top_p` gesetzt.

---

## 🏛️ 1.1 Architektur-Reflexion: Perplexity Hybrid Compute Blueprint vs. Unsere Implementierung

Wir haben unsere Architektur exakt gegen die drei Kernpfeiler des **Perplexity Hybrid Compute Blueprints** abgeglichen und im Detail umgesetzt:

### 📸 Pfeiler 1: Hybrid Compute – Ein Task, zwei Welten (Blueprint-Prinzip 1)
* **Perplexity Blueprint:** Ein Orchestrator teilt eine Gesamtaufgabe intelligent auf. Die Cloud übernimmt anspruchsvolles Reasoning & Websuche, während lokale Modelle vertrauliche Dokumente und sensible Daten verarbeiten. Ein zentraler Orchestrator führt die Ergebnisse nahtlos zusammen.
* **Unsere Implementierung in Open WebUI:**
  - **Realisierung:** Unser zweistufiges Pipeline-System (`pii_filter.py` auf Priority 0 + `model_router.py` auf Priority 10) übernimmt genau diese Orchestrierung.
  - **Verteilung:** Reine Struktur- und Architekturfragen ohne PII werden an High-End Cloud-Modelle (Claude 4.5 Sonnet / Opus 4.6) übergeben. Sobald PII oder unkritische Routineaufgaben vorliegen, übernimmt die lokale Workstation (LM Studio via Tailscale).
  - **Zusammenführung:** Durch den Re-Hydrierungs-Outlet und den Streaming-Subtoken-Buffer werden die vertraulichen Daten erst auf dem Minisforum-Server wieder in die Antwort eingefügt. Die Cloud sieht zu keinem Zeitpunkt Rohdaten.

### 📸 Pfeiler 2: Modell-Split & Zero Cloud Credits (Blueprint-Prinzip 2)
* **Perplexity Blueprint:** Aufgaben werden auf spezialisierte lokale Modelle aufgeteilt, um 0 Cloud-Credits zu verbrauchen: Gemma 4 für Writing, Qwen Coder für Code, DeepSeek für Reasoning.
* **Unsere Implementierung in Open WebUI:**
  - **1:1 Parität erreicht:**
    - `LMStudio.deepseek-r1-distill-qwen-14b`: Deep Reasoning, formale Logik, mathematische Beweise (Temp `0.60`, Top-P `0.95`).
    - `LMStudio.qwen2.5-coder-14b-instruct`: Syntax-präzises Programmieren, Skripte, Refactorings (Temp `0.20`, Top-P `0.85`).
    - `LMStudio.google/gemma-4-12b-qat`: Natürliche menschliche Diktion, Anti-KI Schreibstil, E-Mails und Zusammenfassungen (Temp `0.55`, Top-P `0.90`).
    - `LMStudio.qwen3.8-9b-distill-uncensored-heretic-i1`: Unzensierte historische und kontroverse Recherchen ohne Moralisierung (Temp `0.70`, Top-P `0.90`).
  - **Kosten:** Alltägliche Chat- und Arbeitslasten laufen zu 100 % lokal über die GPU-Workstation (**0 API-Kosten**).

### 📸 Pfeiler 3: Privacy Gate & 4-Aktionen-Klassifikator (Blueprint-Prinzip 3)
* **Perplexity Blueprint:** Ein Privacy Gate mit einem vollwertigen PII-Klassifikator (nicht nur einfache Regex). 4 Aktionen:
  1. *Mask Value:* Wert durch Platzhalter ersetzen.
  2. *Keep Local:* Bei sensiblen Inhalten lokal auf dem Gerät bleiben.
  3. *Refuse:* Anfrage bereinigen / blockieren.
  4. *Ask You:* Benutzer entscheiden lassen / kontrollieren.
  Cloud-Modelle operieren ausschließlich auf abstrakter Struktur, ohne private Daten zu halten.
* **Unsere Implementierung in Open WebUI:**
  - **2-Schichten Klassifikator:** Kombination aus deterministischer Regex-Engine (IBAN, Kreditkarten, Passwörter in URLs, SSN, E-Mail, Telefon, IPs) und Machine-Learning NLP (**spaCy NER** `de_core_news_sm` für Personen, Orte, Organisationen).
  - **Die 4 Aktionen umgesetzt:**
    1. **Mask Value:** Namen, Orte, Organisationen und E-Mails werden mit reversiblen Tokens (`[[NAME_PER_1]]`, `[[EMAIL_1]]`) maskiert. Cloud-Modelle analysieren die Satz- und Logikstruktur, besitzen aber keine echten Personendaten.
    2. **Keep Local:** Kritisches Finanz-PII (`IBAN`, `CREDIT_CARD`, `SSN_US`, `URL_WITH_AUTH`) löst einen sofortigen **Hard Lockdown** aus. Selbst wenn der Nutzer ein Cloud-Modell oder `#opus` gewählt hat, wird der Request hardware-seitig lokal erzwungen.
    3. **Refuse / Sanitization:** Gefährliche Authentifizierungs-Muster in URLs (`user:pass@`) werden bereinigt und neutralisiert.
    4. **Ask You / Benutzer-Souveränität:** Benutzer können über Chat-Tags (`#local`, `#cloud`, `#r1`, `#code`, `#write`, `#heretic`, `#opus`, `#sonnet`, `#flash`, `#gpt`) die Kontrolle übernehmen und in den `UserValves` ihr bevorzugtes Cloud-Standardmodell individuell festlegen.

---

## 🏗️ 2. Die System-Topologie

```
[Browser / Handy]
       │
       ▼ (Port 8080)
┌─────────────────────────────────────────────────────────────┐
│ MINISFORUM SERVER (Home Server)                             │
│                                                             │
│ 1. Filter: PII Redaction Filter (Priority 0)                │
│    Erkennt IBAN, E-Mail, Namen via Regex + spaCy NER        │
│    Ersetzt z.B. "Herr Schmidt" durch "[[NAME_PER_1]]"       │
│                                                             │
│ 2. Filter: Hybrid Model Router (Priority 10)                │
│    - Prüft: Gibt es unmaskierbare PII (z.B. IBAN/Bankdaten)?│
│    - Prüft: Handelt es sich um Code, Mathe, Text, Recherche?│
│    - Wählt Modell & setzt exakte Temp/Top-P                 │
└────────────────┬────────────────────────────┬───────────────┘
                 │                            │
   [Sensibel / Routine / 0 Credits]     [Maskiert + High-Complexity]
                 │                            │
                 ▼ (Tailscale / LAN :1234)    ▼ (Internet HTTPS)
┌────────────────────────────────┐ ┌──────────────────────────┐
│ WORKSTATION (LM Studio GPU)    │ │ OPENROUTER (Cloud)       │
│ • DeepSeek-R1 (Logik)          │ │ • Claude Sonnet 4.5      │
│ • Qwen 2.5 Coder (Skripte)     │ │ • Claude Opus 4.6        │
│ • Gemma 4 (Writing / Anti-KI)  │ │ • Gemini 3 Flash         │
│ • Heretic 9B (Unzensiert)      │ │                          │
└────────────────┬───────────────┘ └──────────┬───────────────┘
                 │                            │
                 └───────────────┬────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. PII Outlet / Stream (Minisforum Server)                  │
│    Setzt "[[NAME_PER_1]]" wieder zu "Herr Schmidt" zusammen │
└────────────────────────────────┬────────────────────────────┘
                                 ▼
                       [Fertige Antwort im Chat]
```

---

## 🧠 3. Die Modell-Profile & wann was verwendet wird

### A. Lokale Modelle (Workstation &bull; LM Studio)

| Profil | Modell in Open WebUI | Temp | Top-P | Wann wählt das Gateway dieses Modell? |
| :--- | :--- | :--- | :--- | :--- |
| **🧠 Deep Reasoning** | `LMStudio.deepseek-r1-distill-qwen-14b` | `0.60` | `0.95` | Mathematische Beweise, formale Logik, Chain-of-Thought, logische Rätsel. |
| **💻 Coding & Skripte** | `LMStudio.qwen2.5-coder-14b-instruct` | `0.20` | `0.85` | Python-Skripte, SQL-Abfragen, Bash, Regex, Debugging, Code-Reviews. |
| **✍️ Writing & Chat** | `LMStudio.google/gemma-4-12b-qat` | `0.55` | `0.90` | Text-Veredelung, Aufsätze, Mails, Zusammenfassungen, Standard-Chat (Human Master / Anti-KI). |
| **🔓 Unzensiert** | `LMStudio.qwen3.8-9b-distill-uncensored-heretic-i1` | `0.70` | `0.90` | Tabuthemen, kontroverse Fragen, unzensierte historische Analysen ohne Moralisierung. |

### B. Cloud-Modelle (OpenRouter) & Flexible Fallkonfiguration

Über die Admin-Valves können die Cloud-Modelle für alle 5 typischen Praxisfälle flexibel und ohne Code-Änderung ausgetauscht werden:

| Profil | Fall / Einsatzzweck | Valve-Name | Standard-Modell (Open WebUI ID) | Temp | Top-P |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **🚀 Cloud High-End** | **Fall 1: High-End Coding & Architektur** (Prompts > 120 Wörter oder `#sonnet` / `#claude`) | `MODEL_CLOUD_HEAVY` | `openrouter.anthropic/claude-sonnet-4.5` | `0.40` | `0.90` |
| **🏛️ Cloud Flagship** | **Fall 2: Deep Reasoning, Philosophie & Strategie** (Erfordert `#opus`) | `MODEL_CLOUD_OPUS` | `openrouter.anthropic/claude-opus-4.6` | `0.50` | `0.90` |
| **✍️ Cloud Writing** | **Fall 3: Komplexe Textanalyse & Mammut-Texte** (Lange Schreibaufträge > 120 Wörter) | `MODEL_CLOUD_WRITING` | `openrouter.anthropic/claude-sonnet-4.5` | `0.45` | `0.90` |
| **⚡ Cloud Fast** | **Fall 4: Schnelle unkritische Abfragen & Suche** (Erfordert `#flash` / `#gemini`) | `MODEL_CLOUD_FAST` | `openrouter.google/gemini-3-flash-preview` | `0.60` | `0.90` |
| **🌐 OpenAI Flagship** | **Fall 5: Analytik, Data Science & OpenAI-Tasks** (Erfordert `#gpt` / `#openai`) | `MODEL_CLOUD_GPT` | `openrouter.openai/gpt-5.2` | `0.30` | `0.90` |

> [!TIP]
> **👤 Individuelle Benutzer-Präferenz (`UserValves.preferred_cloud_model`):**
> Jeder Benutzer kann in seinen Profileinstellungen unter **Account ➔ Functions ➔ Hybrid Model Router** ein persönliches Standard-Cloud-Modell hinterlegen. Wird dieses gesetzt, wird es bei generellen Cloud-Anfragen bevorzugt verwendet.

> [!NOTE]
> **🛡️ Intelligenter Auto-Fallback Schutz:**
> Veraltete oder von OpenRouter deaktivierte Modell-IDs (wie das nicht existierende `google/gemini-3-pro-preview` oder deaktivierte Presets wie `@preset/deepseek-v4`) werden vom Gateway **vollautomatisch abgefangen und auf stabile, operative Alternativen umgeleitet**. Es kommt dadurch zu keinerlei 404- oder 400-Abbrüchen im Chat.

---

## 🛡️ 4. Die PII-Datenschutz-Komponente im Detail (`pii_filter.py`)

Das System setzt auf einen hochentwickelten, zweilagigen und **vollständig reversiblen** Anonymisierungs-Filter, der als vorgeschalteter Wächter (Priority 0) in Open WebUI agiert. Er stellt sicher, dass weder echte Identitäten noch kritische Finanzdaten jemals ungeschützt an externe Cloud-APIs übertragen werden.

### 4.1 Die 2-Schichten Erkennungs-Engine

| Schicht | Technologie | Erkannte Datentypen & Entitäten | Erzeugter Platzhalter | Auswirkung auf Cloud-Routing |
| :--- | :--- | :--- | :--- | :--- |
| **Layer 1: Strukturierte Daten** | Präzise reguläre Ausdrücke (Regex) | **IBAN** (Deutsche & internat. Kontonummern) | `[[IBAN_1]]` | 🔒 **Hard Lockdown** (Cloud strikt verboten) |
| | | **Kreditkarten** (Visa, MC, Amex 13–19 stellig) | `[[CREDIT_CARD_1]]` | 🔒 **Hard Lockdown** (Cloud strikt verboten) |
| | | **Passwörter in URLs** (`https://user:pass@...`) | `[[URL_WITH_AUTH_1]]` | 🔒 **Hard Lockdown** (Cloud strikt verboten) |
| | | **US SSN / Sozialversicherungsnr.** | `[[SSN_US_1]]` | 🔒 **Hard Lockdown** (Cloud strikt verboten) |
| | | **E-Mail-Adressen** (Geschäftlich & privat) | `[[EMAIL_1]]` | 🟡 Maskiert & an Cloud erlaubt (sofern kein Lockdown) |
| | | **Telefonnummern** (DE Mobil/Festnetz & Intl) | `[[PHONE_DE_1]]`, `[[PHONE_INTL_1]]`| 🟡 Maskiert & an Cloud erlaubt |
| | | **IPv4-Adressen** (Netzwerk-Infrastruktur) | `[[IPV4_1]]` | 🟡 Maskiert & an Cloud erlaubt |
| **Layer 2: Unstrukturierte Entitäten** | spaCy NER (`de_core_news_sm`) | **Personen & Namen** (`PER` / `PERSON`) | `[[PER_1]]` (oder `[[NAME_PER_1]]`) | 🟡 Maskiert & an Cloud erlaubt |
| | | **Orte & Städte** (`LOC` / `GPE`) | `[[LOC_1]]` | 🟡 Maskiert & an Cloud erlaubt |
| | | **Organisationen & Firmen** (`ORG`) | `[[ORG_1]]` | 🟡 Maskiert & an Cloud erlaubt |
| | | **Sonstige Entitäten** (`MISC`) | `[[MISC_1]]` | 🟡 Maskiert & an Cloud erlaubt |

#### 🛡️ Schutz gegen False-Positives (Stopwords & Heuristiken)
Um zu verhindern, dass normale deutsche Alltagswörter wie *„Hallo“*, *„Bitte“*, *„Danke“*, *„Montag“*, *„Morgen“* oder *„Ende“* fälschlicherweise von spaCy als Personen oder Orte maskiert werden, besitzt der Filter eine integrierte Stoppwort-Bibliothek (`NER_STOPWORDS`) und ignoriert Wörter unter 3 Zeichen (`ner_min_token_len=3`).

---

### 4.2 Der 4-Phasen Lebenszyklus (Reversibilität & Streaming)

```
1. INLET (User tippt)       2. ROUTER (P=10)           3. INFERENZ                 4. OUTLET / STREAM
"Herr Schmidt aus München"  Prüft PII-Counters         Modell sieht nur:           Ersetzt [[PER_1]]
         │                           │                 "[[PER_1]] aus [[LOC_1]]"         │
         ▼                           ▼                           │                       ▼
   [[PER_1]] & [[LOC_1]]    -> Routet lokal oder Cloud          │              "Herr Schmidt aus München"
   Mapping in metadata      (Kritisch = Local only!)             │              Im Browser sichtbar!
```

1. **Inlet (Maskierung vor dem Senden):**
   * Der Filter scannt die Benutzereingabe, erzeugt fortlaufende Platzhalter (`[[PER_1]]`, `[[IBAN_1]]`) und speichert das geheime Zuordnungs-Wörterbuch in `body["metadata"]["pii_map"]`.
2. **Gateway-Entscheidung (Model Router):**
   * Der Router liest `metadata["pii_counters"]`. Bei kritischen Funden (`IBAN`, `CREDIT_CARD`) wird die Cloud hardwareseitig gesperrt – der Request bleibt auf der lokalen Workstation.
3. **Outlet (Vollständige Re-Hydrierung):**
   * Sobald das Modell antwortet, durchläuft die Antwort das `outlet`. Alle Platzhalter werden millimetergenau durch die Originaldaten ersetzt.
4. **Live-Streaming Hook (`stream`):**
   * Beim Token-Streaming (SSE) kommen Tokens stückweise an. Ein Platzhalter wie `[[IBAN_1]]` könnte über zwei Chunks zerschnitten sein (Chunk 1: `Konto: [[IB`, Chunk 2: `AN_1]] verbucht`).
   * Der Filter besitzt einen **adaptiven Substring-Buffer**: Er puffert unvollständige Tokens kurz zwischen und expandiert den Klartext flüssig in dem Moment, in dem das schließende `]]` eintrifft. Für den Benutzer gibt es kein sichtbares Flackern oder Aufblitzen von Platzhaltern.

---

### 4.3 Reasoning-Schutz (`deanonymize_reasoning`)

Modelle wie **DeepSeek-R1** oder **Gemma 4** generieren vor dem eigentlichen Text ausführliche Denkprozesse (`reasoning_content` bzw. `<think>`). 
* Ist `deanonymize_reasoning: true` (Standard), werden die Platzhalter auch im einklappbaren Denkblock wieder mit den echten Namen befüllt.
* Dadurch bleibt der Gedankengang für den Benutzer vollständig nachvollziehbar und transparent.

---

### 4.4 Konfiguration & Anpassung (Valves)

In Open WebUI unter **Workspace ➔ Functions ➔ PII Redaction Filter (Reversible) ➔ Valves (⚙️)** können Administratoren das Verhalten feingranular steuern:

| Parameter (Valve) | Standard | Beschreibung |
| :--- | :--- | :--- |
| `enable_regex` | `true` | Aktiviert die strukturierte Erkennung (IBAN, E-Mail, Telefon, IP). |
| `enable_ner` | `true` | Aktiviert spaCy NER für Personen, Orte und Organisationen. |
| `deanonymize_output` | `true` | Stellt Originaldaten im Outlet wieder her (auf `false` setzen für Anonymisierungs-Demos). |
| `deanonymize_reasoning`| `true` | Füllt auch den Modell-Denkprozess (`<think>`) wieder mit echten Daten. |
| `token_format` | `[[{label}_{n}]]` | Format der Platzhalter-Tokens. |
| `extra_patterns` | `""` | Benutzerdefinierte Regex-Muster pro Zeile (`NAME\|PATTERN`), z. B. `MITARBEITER\|M\d{6}`. |
| `ner_min_token_len` | `3` | Mindestlänge für Entity-Bestandteile zur Vermeidung von False Positives. |

> [!TIP]
> **User-Valves:** Jeder Benutzer kann in seinen Profileinstellungen die PII-Redaktion für seinen eigenen Account temporär ein- oder ausschalten (`UserValves.enabled`).

---

### 4.5 Transparenz & Audit-Log (Das Info-Icon ℹ️)

Nach jeder Antwort legt der PII-Filter unter `metadata["pii_audit"]` ein revisionssicheres Protokoll ab. Klickt der Benutzer in Open WebUI auf das **Info-Icon (ℹ️)** einer Nachricht, sieht er:
* Gesamtzahl der geschwärzten Entitäten.
* Detail-Liste: Welches Token wurde für welchen Originalwert eingesetzt.
* Zeitstempel und Status (*„Vollständig deanonymisiert ✓“*).

---

## 🕹️ 5. Manuelle Steuerung im Chat (Tags & Aliase)

Du musst das Routing nicht der Automatik überlassen. Wenn du ein bestimmtes Modell erzwingen willst, schreibe einfach eines der folgenden Tags an eine beliebige Stelle in deinen Prompt (das Tag wird vor dem Senden an das Modell **automatisch gelöscht**):

### Kurzbefehle für lokale Modelle:
* `#r1` oder `/r1`: Erzwingt **DeepSeek-R1** (Temp `0.60`, Top-P `0.95`).
* `#code` oder `/coder`: Erzwingt **Qwen 2.5 Coder** (Temp `0.20`, Top-P `0.85`).
* `#write` oder `#human`: Erzwingt **Gemma 4** (Temp `0.55`, Top-P `0.90`).
* `#heretic` oder `#uncensored`: Erzwingt **Heretic 9B** (Temp `0.70`, Top-P `0.90`).
* `#local`: Forciert generelle Ausführung auf der lokalen Workstation.

### Kurzbefehle für Cloud-Modelle:
* `#sonnet` oder `#claude`: Wählt **Claude Sonnet 4.5** (Cloud High-End).
* `#opus`: Wählt **Claude Opus 4.6** (Cloud Flagship für tiefste Synthesen).
* `#gpt` oder `#openai`: Wählt **OpenAI GPT-5.2** (Cloud High-End für Analytik & Data-Science).
* `#flash` oder `#gemini`: Wählt **Gemini 3 Flash** (schnelle Routine in der Cloud).
* `#cloud`: Bevorzugt Cloud-Verarbeitung (sofern datenschutzkonform).

> **Beispiel:**  
> `#r1 Löse dieses Optimierungsproblem: f(x) = x^3 - 5x + 2`  
> &rarr; Der Router entfernt `#r1`, wählt DeepSeek-R1 auf der Workstation und setzt Temperatur `0.60`.

---

## 🎯 5.1 Nur interne Modelle nutzen & automatische Modellauswahl umgehen (Manual Override & Airgap)

Eine der wichtigsten Fragen in der Praxis lautet:  
> *„Was ist, wenn ich nur ein bestimmtes internes Modell (z. B. Gemma 4 oder Qwen Coder) nutzen möchte, aber die automatische Modellauswahl des Routers soll dabei nicht eingreifen?“*

### 🔑 Grundprinzip: PII-Datenschutz und Model Router sind unabhängig voneinander!

In Open WebUI arbeiten zwei eigenständige Filter-Funktionen mit getrennten Prioritäten:
1. **`pii_filter_reversible` (Priorität 0):** Scannt den Prompt, schwärzt sensible Entitäten (IBAN, Namen, E-Mails, Adressen) mit Platzhaltern (`[[NAME_PER_1]]`), restauriert sie nach der Antwort im Outlet und stellt das interaktive Protokoll bereit.
2. **`hybrid_model_router` (Priorität 10):** Liest die Metadaten des PII-Filters, analysiert den Intent (Code, Logik, Text) und überschreibt `body['model']` mit dem optimalen Modell.

> [!IMPORTANT]
> **Voller Datenschutz auch ohne Router:**  
> Du kannst den Model Router jederzeit für deinen Account oder das Gesamtsystem **deaktivieren oder umgehen** – der PII-Datenschutzfilter bleibt dabei **zu 100 % aktiv**! Alle sensiblen Daten werden weiterhin zuverlässig geschwärzt und in der Antwort wiederhergestellt.

---

### Die 4 Wege in der Übersicht:

| Weg | Ziel | Wo konfigurieren? | Verhalten des Systems |
| :--- | :--- | :--- | :--- |
| **Weg 1: 100 % Manuelle Wahl** | Du wählst oben im Dropdown frei ein Modell, der Router greift überhaupt nicht ein. | **Profil ➔ Settings ➔ Functions ➔ Valves:** `enabled = false` (oder Admin global) | Router ist inaktiv. Open WebUI nutzt exakt dein gewähltes Modell. PII-Filter läuft normal weiter. |
| **Weg 2: Reiner Airgap-Modus** | Nur lokale Modelle (0 Cloud-Credits), aber automatische Aufteilung nach Code/Logik/Text. | Im Prompt `#local` schreiben oder in den User-Valves `prefer_local = true` setzen | Bleibt immer auf der Workstation. Routet zwischen Gemma, Qwen Coder und DeepSeek-R1. |
| **Weg 3: Gezieltes Modell-Pinning** | Für einen einzelnen Prompt gezielt ein bestimmtes lokales Modell erzwingen. | Tag `#write`, `#code`, `#r1` oder `#heretic` im Prompt | Erzwingt das jeweilige lokale Modell, überschreibt andere Automatismen. |
| **Weg 4: Festes Standard-Modell** | Alle Rollen des Routers sollen immer auf ein einziges lokales Allround-Modell zeigen. | **Admin-Valves:** `MODEL_LOCAL_WRITING`, `_CODING`, `_REASONING` auf dieselbe ID setzen | Jeder lokale Routing-Pfad führt immer zu deinem favorisierten Modell. |

---

### Detaillierte Schritt-für-Schritt-Anleitung:

#### Weg 1: Automatische Modellauswahl komplett ausschalten (Reine manuelle Kontrolle)
Wenn du im Dropdown-Menü oben einfach dein gewünschtes internes Modell (z. B. `LMStudio.google/gemma-4-12b-qat`) wählen willst und kein Automatismus dazwischenfunken soll:

* **Nur für deinen eigenen Benutzer-Account:**
  1. Klicke in Open WebUI ganz unten links auf deinen **Benutzernamen / Profilbild ➔ Einstellungen (⚙️)**.
  2. Klicke auf **Funktionen (Functions)**.
  3. Klicke beim **Hybrid Model Router** auf das Zahnrad / Regler-Symbol (**Valves**).
  4. Schalte den Parameter `enabled` auf **Aus (`false`)** und speichere.
  * **Ergebnis:** Der Router ist für deinen Account vollständig deaktiviert. Du wählst im Modell-Dropdown oben ein beliebiges Modell aus – Open WebUI sendet deinen Prompt 1:1 genau dorthin. Der `pii_filter_reversible` schützt deine Daten im Hintergrund weiterhin vollständig.

* **Global für alle Benutzer des Servers (System-Administrator):**
  1. Öffne das **Admin-Panel ➔ Funktionen (Functions)**.
  2. Suche den Eintrag `Hybrid Model Router` (`hybrid_model_router`).
  3. Schalte den Hauptschalter von **Aktiv auf Inaktiv**.
  * **Ergebnis:** Kein Benutzer wird mehr automatisch umgeleitet. Alle Anwender nutzen die manuelle Modellauswahl von Open WebUI. Der PII-Filter bleibt global aktiv.

#### Weg 2: 100 % Intern bleiben, aber automatische Modell-Spezialisierung nutzen (Airgap)
Wenn du sagst: *„Ich möchte strikt 0 Cloud-Credits verbrauchen und keine Daten ins Internet senden, aber wenn ich Code frage, soll Qwen Coder antworten, und wenn ich Mathe frage, DeepSeek-R1“*:
* **Ad-hoc im Chat:** Schreibe einfach `#local` in deine Nachricht (z. B. `#local Schreibe eine Funktion für...`).
* **Dauerhaft als Profil-Einstellung:** Gehe in deine **Profileinstellungen ➔ Funktionen ➔ Hybrid Model Router (Valves)** und setze `prefer_local` auf **`true`**.
* **Ergebnis:** Selbst bei hochkomplexen Texten oder Code-Aufgaben wird niemals die Cloud (OpenRouter) kontaktiert. Der Router bleibt strikt auf der lokalen LM Studio Workstation.

#### Weg 3: Gezieltes Modell-Pinning per Prompt-Tag
Wenn der Router grundsätzlich aktiv bleiben soll, du aber bei einem speziellen Prompt ein ganz bestimmtes internes Modell ansteuern willst:
* **Gemma 4 (Anti-KI / Schreiben):** Nutze `#write` oder `#human`
* **Qwen 2.5 Coder (Code & SQL):** Nutze `#code` oder `/coder`
* **DeepSeek-R1 (Logik & Mathe):** Nutze `#r1` oder `/r1`
* **Heretic 9B (Unzensiert):** Nutze `#heretic` oder `#uncensored`
* **Ergebnis:** Das Tag wird vor dem Versenden automatisch aus dem Text entfernt, und der Prompt wird ohne Intent-Analyse direkt an das forzierte Modell übergeben.

---

## 🔍 6. Transparenz & Audit: Modell & PII-Verlauf im Info-Icon (ℹ️)

Unter jeder Antwortnachricht in Open WebUI kannst du im **Info-Icon (ℹ️)** die vollständige Historie und Herkunft der Nachricht einsehen.

### 1. Das Routing (`router_decision`)
Zeigt, welches Modell gewählt wurde, warum, und welche Parameter gesetzt wurden:

```json
{
  "router_decision": {
    "original_model": "openrouter.@preset/gpt-oss-europe",
    "routed_to": "LMStudio.qwen2.5-coder-14b-instruct",
    "target_node": "Workstation (LM Studio via Tailscale)",
    "profile": "coding",
    "temperature": 0.2,
    "top_p": 0.85,
    "reason": "Standard Coding & Skripte -> Qwen 2.5 Coder 14B auf Workstation",
    "pii_detected": 2,
    "critical_pii_blocked": false,
    "pii_behandelte_elemente": [
      {
        "token": "[[NAME_PER_1]]",
        "kategorie": "NAME_PER",
        "original": "Anna",
        "status": "Im Prompt geschwärzt ➔ In Antwort wiederhergestellt"
      },
      {
        "token": "[[NAME_PER_2]]",
        "kategorie": "NAME_PER",
        "original": "Schmidt",
        "status": "Im Prompt geschwärzt ➔ In Antwort wiederhergestellt"
      }
    ]
  }
}
```

### 2. Das PII-Audit-Log (`pii_audit`)
Zeigt lückenlos alle Teile, die vom PII-Filter erkannt, maskiert und nach der LLM-Antwort wieder zu den Originalen zusammengesetzt wurden:

```json
{
  "pii_audit": {
    "anzahl_behandelt": 2,
    "status": "Vollständig deanonymisiert (Originaldaten wiederhergestellt)",
    "elemente": [
      {
        "token": "[[NAME_PER_1]]",
        "kategorie": "NAME_PER",
        "original": "Anna",
        "status": "Im Prompt geschwärzt ➔ In Antwort erfolgreich wiederhergestellt"
      },
      {
        "token": "[[NAME_PER_2]]",
        "kategorie": "NAME_PER",
        "original": "Schmidt",
        "status": "Im Prompt geschwärzt ➔ In Antwort erfolgreich wiederhergestellt"
      }
    ]
  }
}
```

Damit hast du die **100 %ige Gewissheit**:
- Welche Daten das Modell im Rohzustand verlassen haben (nur neutrale Tokens wie `[[NAME_PER_1]]`).
- Welche Daten nach Rückkehr des Modells wieder eingesetzt wurden.

---

## ⚙️ 7. Einstellungen & Feinjustierung (Admin & User Valves)

Sowohl Administratoren als auch Endanwender können das Verhalten des Routers ohne jede Code-Änderung über die Web-Oberfläche anpassen.

### 7.1 Admin Valves (Globale Systemkonfiguration)

1. Navigiere zu **Workspace ➔ Functions**.
2. Klicke bei **Hybrid Model Router** auf das Zahnrad / Edit-Icon (⚙️ Valves).
3. Folgende Parameter stehen zur Verfügung:

| Parameter | Typ / Standard | Beschreibung |
| :--- | :--- | :--- |
| `priority` | `10` | **Wichtig:** Muss immer auf `10` stehen, damit der Router nach dem PII-Filter (`0`) ausgeführt wird. |
| `COMPLEXITY_WORD_THRESHOLD` | `120` | Ab wie vielen Wörtern ein unkritischer Prompt automatisch als komplex eingestuft und an die Cloud delegiert wird. |
| `STRICT_LOCAL_ON_ANY_PII` | `false` | Wenn `true`, wird bei *jeder* PII (auch maskierten Namen/Orten) der Cloud-Abfluss komplett gesperrt. Standard `false` erlaubt maskierte Standard-PII für Struktur-Reasoning. |
| `MODEL_LOCAL_ROUTINE` | `LMStudio.google/gemma-4-12b-qat` | Lokales Modell für Routine-Chat, Zusammenfassungen, E-Mails und Standard-Prompts. |
| `MODEL_LOCAL_CODING` | `LMStudio.qwen2.5-coder-14b-instruct` | Lokales Modell für Code-Generierung, Bash, SQL, Regex und Debugging. |
| `MODEL_LOCAL_REASONING` | `LMStudio.deepseek-r1-distill-qwen-14b` | Lokales Modell für formale Logik, mathematische Beweise und Denkketten. |
| `MODEL_LOCAL_UNCENSORED` | `LMStudio.qwen3.8-9b-distill-uncensored-heretic-i1` | Lokales Modell für Tabuthemen und unzensierte Recherchen (`#heretic`). |
| `MODEL_CLOUD_HEAVY` | `openrouter.anthropic/claude-sonnet-4.5` | **Fall 1:** Cloud-Modell für High-End Coding & Architektur (lange Prompts oder `#sonnet` / `#claude`). |
| `MODEL_CLOUD_OPUS` | `openrouter.anthropic/claude-opus-4.6` | **Fall 2:** Cloud-Modell für tiefstes Reasoning, Philosophie & Strategie (`#opus`). |
| `MODEL_CLOUD_WRITING` | `openrouter.anthropic/claude-sonnet-4.5` | **Fall 3:** Cloud-Modell für komplexe Textanalyse & Mammut-Texte (> 120 Wörter). |
| `MODEL_CLOUD_FAST` | `openrouter.google/gemini-3-flash-preview` | **Fall 4:** Cloud-Modell für schnelle, latenzkritische Cloud-Abfragen (`#flash` / `#gemini`). |
| `MODEL_CLOUD_GPT` | `openrouter.openai/gpt-5.2` | **Fall 5:** Cloud-Modell für Data Science, Analytik & OpenAI-spezifische Aufgaben (`#gpt` / `#openai`). |

### 7.2 User Valves (Persönliche Einstellungen pro Account)

Jeder Nutzer kann im WebUI sein persönliches Profil individualisieren:
1. Klicke links unten auf deinen **Benutzernamen / Profilbild ➔ Settings ➔ Functions**.
2. Wähle **Hybrid Model Router**:
   - `preferred_cloud_model`: Frei wählbare Modell-ID (z. B. `openrouter.anthropic/claude-sonnet-4.5`, `openrouter.google/gemini-3-flash-preview` oder ein beliebiges anderes in Open WebUI aktives Modell).
   - Wenn gesetzt, wird dieses Modell als persönliche Standard-Wahl bei generellen Cloud-Anfragen verwendet, anstelle des globalen Systemstandards.

---

## 🧪 8. Praxis-Beispiele & Test-Prompts (Prompt Showcase)

Hier sind fünf praxiserprobte Test-Prompts, mit denen du die verschiedenen Sicherheits- und Routing-Mechanismen direkt in Open WebUI ausprobieren und im **Info-Icon (ℹ️)** überprüfen kannst:

### 🏦 Szenario 1: Datenschutz-Lockdown (Kritisches PII + Coding)
* **Ziel:** Überprüfen, ob Bankverbindungen zuverlässig erkannt werden und den Cloud-Abfluss sperren.
* **Erwartetes Routing:**
  - **Inlet:** Maskiert Name, Adresse, E-Mail, Telefon und IBAN zu `[[NAME_PER_1]]`, `[[IBAN_1]]` etc.
  - **Privacy Gate:** Erkennt `[[IBAN_1]]` ➔ **Cloud-Sperre aktiv**.
  - **Target:** Lokale Workstation `LMStudio.qwen2.5-coder-14b-instruct` (Temp: `0.20`, Top-P: `0.85`).
  - **Outlet:** Re-hydriert alle Tokens wieder mit den echten Daten in der Code-Ausgabe.

```text
Hallo! Für unseren Mandanten Dr. Maximilian von Berg (Leopoldstraße 42, 80802 München, E-Mail: m.berg@alpen-consulting.de, Tel: +49 89 12345678) muss eine automatisierte Rechnungsprüfung implementiert werden.

Seine hinterlegte Auszahlungs-IBAN lautet: DE89 3704 0044 0532 0130 00.

Aufgabe:
Schreibe mir ein sauberes Python-Skript (unter Verwendung von Pydantic v2), das:
1. Ein Datenmodell `Mandant` mit allen oben genannten Attributen definiert.
2. Eine Beispielfunktion enthält, die diese konkreten Mandantendaten instanziiert und eine kurze Überweisungsbestätigung im Konsolen-Log ausgibt.
```

---

### 🧠 Szenario 2: Deep Reasoning & Mathematik (Lokal mit DeepSeek-R1)
* **Ziel:** Prüfen, ob mathematische Beweise automatisch an das lokale R1-Modell geleitet werden.
* **Erwartetes Routing:**
  - **Intent:** Erkennt mathematische Beweisführung und formale Logik.
  - **Target:** Lokale Workstation `LMStudio.deepseek-r1-distill-qwen-14b`.
  - **Parameter:** Temp: `0.60`, Top-P: `0.95` (explorativer Denkspielraum für `<think>`-Tokens).

```text
Beweise formell durch vollständige Induktion, dass für alle natürlichen Zahlen n >= 1 gilt:
1 + 2 + 3 + ... + n = n * (n + 1) / 2.
Zeige jeden logischen Teilschritt explizit auf und begründe den Induktionsschritt mathematisch exakt.
```

---

### ✍️ Szenario 3: Text-Veredelung & Writing (Anti-KI / Human Master)
* **Ziel:** Null Cloud-Credits verbrauchen für alltägliche Schreib- und Redaktionsaufgaben.
* **Erwartetes Routing:**
  - **Inlet:** Maskiert `Frau Dr. Julia Sommerfeld` zu `[[NAME_PER_1]]`.
  - **Intent:** Erkennt E-Mail / Schreib-Veredelung.
  - **Target:** Lokale Workstation `LMStudio.google/gemma-4-12b-qat` (Temp: `0.55`, Top-P: `0.90`).
  - **Outlet:** Setzt den echten Namen wieder ein. Kosten: **0 Cloud-Credits**.

```text
Sehr geehrte Frau Dr. Julia Sommerfeld, vielen Dank für das freundliche Telefonat heute Vormittag.

Aufgabe:
Formuliere mir aus dieser kurzen Notiz eine professionelle, warme und präzise Follow-up-E-Mail auf Deutsch. Der Tonfall soll menschlich, verbindlich und frei von typischen KI-Floskeln (wie 'Ich hoffe, diese E-Mail erreicht Sie wohlbehalten') sein. Betone, dass wir das besprochene Angebot bis kommenden Donnerstag finalisieren.
```

---

### 🚀 Szenario 4: Cloud High-End Architektur (Claude Sonnet 4.5 via OpenRouter)
* **Ziel:** Komplexe Software-Architektur ohne sensible PII zur Cloud delegieren.
* **Erwartetes Routing:**
  - **Prüfung:** Keine PII vorhanden, Anforderung übersteigt Komplexitätsschwelle (> 120 Wörter) bzw. nutzt `#sonnet`.
  - **Target:** OpenRouter Cloud `openrouter.anthropic/claude-sonnet-4.5`.
  - **Parameter:** Temp: `0.40`, Top-P: `0.90`.

```text
#sonnet
Entwirf eine hochverfügbare Event-Driven Microservice-Architektur für eine E-Commerce-Plattform mit folgenden Anforderungen:
1. Event-Bus mit Apache Kafka für Bestellungen, Bestandsänderungen und Rechnungsstellung.
2. Outbox-Pattern zur Gewährleistung von Konsistenz zwischen PostgreSQL und Kafka ohne Two-Phase-Commits.
3. Resilience-Pattern (Circuit Breaker, Dead-Letter-Queues und Idempotenz-Keys für Zahlungsabwicklungen).
Erstelle ein übersichtliches Text-Architekturdiagramm und beschreibe die Fehlerbehandlung bei temporären Netzwerk-Partitions.
```

---

### 🛡️ Szenario 5: Privacy Gate Override-Test (Schutz vor versehentlichem Cloud-Leak)
* **Ziel:** Sicherstellen, dass das Privacy Gate selbst einen expliziten `#opus`-Tag überstimmt, wenn eine IBAN im Text steht.
* **Erwartetes Routing:**
  - **Tag:** User fordert `#opus` an.
  - **Privacy Gate:** Erkennt IBAN ➔ **Erzwingt lokalen Fallback**!
  - **Target:** Lokale Workstation `LMStudio.qwen2.5-coder-14b-instruct`.
  - **Audit-Info (ℹ️):** `reason: "Overridden to local: prompt contains critical PII (IBAN)"`.

```text
#opus
Hier ist die Abrechnung für Herrn Michael Weber mit IBAN DE44 5001 0517 5409 3211 00.
Erstelle mir eine formatierte Zusammenfassung der Auszahlungssumme von 1.450,00 EUR und formatiere eine Überweisungszeile für das ERP-System.
```

---

## ⚡ 9. Technische Details, Latenz & Troubleshooting (Good to Know)

Damit du das Laufzeitverhalten der Pipeline im Alltag optimal verstehst und einschätzen kannst:

### 1. Nahtlose Modell-Synchronisation im Browser (`selected_model_id`)
* **Hintergrund:** Wenn du im Chat ein Cloud-Modell (z. B. `Cortecs.gemini-3.7-flash`) ausgewählt hast, der Router deine Anfrage aber wegen einer IBAN auf die lokale Workstation (`LMStudio.qwen2.5-coder-14b-instruct`) umleitet, tauscht das Gateway das Modell serverseitig zur Laufzeit aus.
* **Synchronisation:** Der Router injiziert das Feld `selected_model_id` in die Metadaten. Open WebUI sendet dieses als allererstes Server-Sent-Event (`data: {"selected_model_id": ...}`) an den Browser. Dadurch weiß dein Web-Frontend sofort, dass die eingehenden Tokens zu dem neuen Modell gehören, und rendert die Antwort ohne Verzögerung in die richtige Chat-Sprechblase.

### 2. Cold-Starts & VRAM-Ladezeiten auf der Workstation
* **Wie LM Studio arbeitet:** Auf der lokalen Workstation stehen mehrere 9B- bis 14B-Modelle bereit (Qwen Coder, DeepSeek-R1, Gemma 4, Heretic). LM Studio lädt Modelle bei Bedarf dynamisch in den VRAM der Grafikkarte (*Just-in-Time Loading*).
* **Erst-Aufruf:** Wenn du ein Modell anfragst, das gerade nicht im GPU-Speicher liegt, benötigt das Laden des Modells von der SSD in den Grafikspeicher ca. **10–15 Sekunden**.
* **Folge-Aufrufe:** Sobald das Modell im Speicher liegt, antwortet es ohne Ladezeit sofort.

### 3. Der interne Denkprozess (`reasoning_content` / CoT)
* **Gedankengang vor Text:** Modelle wie DeepSeek-R1 oder Gemma 4 erzeugen vor der eigentlichen Ausgabe einen internen Denkprozess (`reasoning_content` bzw. `<think>`). 
* **Wichtig:** Während dieser Phase generiert das lokale Modell 400–800 Denk-Tokens (dauert ca. 15–25 Sekunden auf der GPU). Open WebUI zeigt dies als einklappbaren Denkblock (*"Denken..."* bzw. *Thought*) an. Das ist **kein Hänger oder Verbindungsabbruch**, sondern die normale Ausführungszeit der lokalen Inferenz.

### 4. Verbindung nicht vorzeitig abbrechen
* **Tipp:** Wenn du eine komplexe Anfrage oder sensible Daten abschickst, lass dem Tab ca. **20–30 Sekunden Zeit**. Ein vorzeitiges Neuladen der Seite (*F5 / Refresh*) trennt den WebSocket-Kanal zum Minisforum-Server, bricht die laufende GPU-Berechnung in LM Studio ab und hinterlässt eine unvollständige Nachricht.


