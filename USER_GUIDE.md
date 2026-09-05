# 📘 Benutzer-Handbuch: Hybrid Model Router & Privacy Gate

> **Setup:** Open WebUI auf Minisforum Server &bull; Compute Node via Tailscale (LM Studio Workstation) &bull; Cloud APIs (OpenRouter)

---

## 🌟 1. Was macht dieses System?

Dein KI-System kombiniert zwei Sicherheits- und Performance-Ebenen zu einer vollautomatischen **Hybrid-Orchestrierung** (nach dem Vorbild von *Perplexity Hybrid Compute*):

1. **Datenschutz (Privacy Gate):** Sensible Daten (Namen, Orte, Firmen, E-Mails) werden in der User-Eingabe geschwärzt (`[[NAME_PER_1]]`), bevor ein externes Modell sie sehen kann. Nach der Antwort werden sie automatisch wieder mit den Originaldaten befüllt.
2. **Intelligentes Modell-Routing:** Ein nachgelagertes Gateway entscheidet anhand von **Datenschutzstufe**, **Aufgabentyp (Intent)** und **Komplexität**, wohin die Anfrage gesendet wird:
   - **Lokale Workstation (LM Studio via Tailscale):** Für sensible/kritische Daten, Programmier-Routine, unzensierte Recherchen und Alltags-Chat (**0 Cloud-Credits / gratis**).
   - **Cloud High-End (OpenRouter):** Für hochkomplexe Systemarchitekturen, tiefste Logik und Mammut-Code (Claude Sonnet 4.5 / Opus 4.6), sofern keine kritischen Daten vorliegen.
3. **Automatische Hyperparameter:** Für jedes Modell werden automatisch die optimalen Werte für `temperature` und `top_p` gesetzt.

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

### B. Cloud-Modelle (OpenRouter)

| Profil | Modell in Open WebUI | Temp | Top-P | Wann wählt das Gateway dieses Modell? |
| :--- | :--- | :--- | :--- | :--- |
| **🚀 Cloud High-End** | `openrouter.anthropic/claude-sonnet-4.5` | `0.40` | `0.90` | Sehr lange Prompts (> 120 Wörter), Microservice-Architekturen, komplexe Refactorings ohne PII. |
| **🏛️ Cloud Flagship** | `openrouter.anthropic/claude-opus-4.6` | `0.50` | `0.90` | Wird bei manuellem Tag `#opus` für tiefste philosophische/strategische Analysen aufgerufen. |
| **⚡ Cloud High-Speed** | `openrouter.google/gemini-3-flash-preview` | `0.60` | `0.90` | Schnelle allgemeine Cloud-Recherchen bei manuellem Tag `#flash`. |

---

## 🛡️ 4. Die Datenschutz-Logik (Privacy Gate)

Das Gateway arbeitet nach klaren Sicherheits-Regeln:

1. **Rote Flagge (Kritische PII):**
   * Erkennt der PII-Filter `IBAN`, `CREDIT_CARD`, `SSN_US`, `URL_WITH_AUTH` oder `TAX_ID_DE`, wird **die Cloud sofort gesperrt**.
   * Die Anfrage bleibt **zwingend lokal auf deiner Workstation**.
   * Selbst wenn du im Prompt `#cloud` oder `#opus` schreibst, verhindert der Filter ein Abfließen in die Cloud!
2. **Grüne Flagge (Maskierte Standard-PII):**
   * Erkennt der Filter Namen von Personen oder Orten, werden diese durch Tokens (`[[NAME_PER_1]]`, `[[NAME_LOC_1]]`) ersetzt.
   * Das Cloud-Modell sieht nur abstrakte Bezeichner und kann die komplexe Aufgabe bearbeiten, ohne jemals echte Namen zu sehen.
   * Auf dem Minisforum-Server werden beim Rücklauf die Originalnamen wieder eingesetzt.
3. **Zero Cloud Credits (Spar-Modus):**
   * Routine-Aufgaben (z. B. *"Übersetze bitte..."*, *"Korrigiere Rechtschreibung..."*, Textformatierung) gehen standardmäßig an **Gemma 4 auf der Workstation**. Dein OpenRouter-Guthaben wird dafür nicht angetastet.

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
* `#sonnet` oder `#claude`: Wählt **Claude Sonnet 4.5** (Cloud).
* `#opus`: Wählt **Claude Opus 4.6** (Cloud Flagship).
* `#flash`: Wählt **Gemini 3 Flash** (schnell).
* `#cloud`: Bevorzugt Cloud-Verarbeitung (sofern datenschutzkonform).

> **Beispiel:**  
> `#r1 Löse dieses Optimierungsproblem: f(x) = x^3 - 5x + 2`  
> &rarr; Der Router entfernt `#r1`, wählt DeepSeek-R1 auf der Workstation und setzt Temperatur `0.60`.

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

## ⚙️ 7. Einstellungen & Feinjustierung (Admin Valves)

Als Administrator kannst du das Verhalten des Routers jederzeit in der Open-WebUI-Oberfläche anpassen:

1. Gehe zu **Workspace ➔ Functions**.
2. Klicke bei **Hybrid Model Router** auf das Zahnrad / Edit-Icon.
3. Unter **Valves** kannst du folgende Parameter ändern:
   * `priority`: Muss auf `10` bleiben (damit er nach dem PII-Filter mit `0` läuft).
   * `STRICT_LOCAL_ON_ANY_PII`: Wenn auf `True` gesetzt, darf bei *irgendeiner* PII (auch maskierten Namen) überhaupt nichts mehr in die Cloud.
   * `COMPLEXITY_WORD_THRESHOLD`: Standard `120` Wörter. Ab dieser Länge werden unkritische Anfragen an Claude Sonnet 4.5 in die Cloud geschickt.
   * `MODEL_LOCAL_*` & `MODEL_CLOUD_*`: Falls du in LM Studio neue Modelle lädst, kannst du die Modell-IDs hier direkt im Web-Interface aktualisieren.

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

