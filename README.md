# Open WebUI: Intelligent Hybrid Model Router (Edge/Cloud Gateway)

Ein intelligentes Routing-Gateway für [Open WebUI](https://github.com/open-webui/open-webui) (v0.5+), inspiriert vom **„Hybrid Compute“**-Ansatz (wie bei *Perplexity Computer*).

Routet Anfragen dynamisch zwischen:
1. **Lokaler Workstation (LM Studio via Tailscale/LAN):** Für vertrauliche Daten, PII, Routineaufgaben und unzensierte Recherchen (**0 Cloud-Credits**).
2. **Cloud High-End (OpenRouter):** Für hochkomplexes Reasoning, Architektur und Mammut-Code (Claude 4.5 Sonnet / Opus 4.6).

> 📊 **Interaktives Web-Dashboard:**
> - **Tailscale:** [http://100.116.36.64:8089](http://100.116.36.64:8089)
> - **Lokales LAN:** [http://192.168.168.202:8089](http://192.168.168.202:8089)
> - **Im Agentic Handbuch:** [http://100.116.36.64:8088](http://100.116.36.64:8088) (Karte 4 oder [/router/](http://100.116.36.64:8088/router/))

---

## 🏗️ Topologie & Architektur

```
                               ┌────────────────────────────────────────────────┐
                               │       Open WebUI (Minisforum Home Server)       │
                               │                                                │
 User tippt Nachricht  ───────▶│  1. pii_filter.py (Priority 0)                  │
                               │     - Regex + spaCy NER maskieren sensible Daten│
                               │     - Schreibt body.metadata.pii_counters       │
                               │                                                │
                               │  2. model_router.py (Priority 10)              │
                               │     - Privacy Gate (Kritische PII? Strict?)    │
                               │     - Intent: Coding, Reasoning, Writing, Heretic│
                               │     - Infiltriert optimale Temp & Top-P         │
                               │     - Schreibt body['model'] um                 │
                               └───────┬────────────────────────────────┬───────┘
                                       │                                │
                       [Datenschutz-Sperre oder Routine]        [Maskiert + High-Complexity]
                                       │                                │
                                       ▼                                ▼
                    ┌──────────────────────────────┐        ┌───────────────────────┐
                    │    Workstation (Tailscale)   │        │ Cloud APIs / OpenRouter│
                    │       LM Studio (:1234)      │        │                       │
                    │ ──────────────────────────── │        │ ───────────────────── │
                    │ • DeepSeek-R1 (Logik/Mathe)  │        │ • Claude Sonnet 4.5   │
                    │ • Qwen 2.5 Coder (Skripte)   │        │ • Claude Opus 4.6     │
                    │ • Gemma 4 (Anti-KI / Writing)│        │ • Gemini 3 Flash      │
                    │ • Heretic 9B (Unzensiert)    │        │                       │
                    └──────────────┬───────────────┘        └───────────┬───────────┘
                                   │                                    │
                                   └─────────────────┬──────────────────┘
                                                     ▼
                               ┌────────────────────────────────────────────────┐
                               │  3. PII Outlet / Stream (Minisforum Server)     │
                               │     - Re-Hydrierung der Originaldaten          │
                               └─────────────────────┬──────────────────────────┘
                                                     ▼
                                          User liest fertigen Text
```

---

## 🎯 Lokale Modell-Profile (LM Studio auf Workstation)

| Profil / Einsatzzweck | Modellbezeichnung (Open WebUI ID) | Temp | Top-P | Rationale & Besonderheit |
| :--- | :--- | :--- | :--- | :--- |
| **🧠 Deep Reasoning** | `LMStudio.deepseek-r1-distill-qwen-14b` | `0.60` | `0.95` | Niemals auf 0.0 setzen; benötigt explorativen Denkspielraum für `<think>`. |
| **💻 Coding & Skripte** | `LMStudio.qwen2.5-coder-14b-instruct` | `0.20` | `0.85` | Deterministische Syntax, präzise Dateidiffs und Code-Blöcke. |
| **✍️ Writing & Chat** | `LMStudio.google/gemma-4-12b-qat` | `0.55` | `0.90` | Authentische menschliche Diktion ohne Stereotypen (Anti-KI Diktion). |
| **🔓 Uncensored** | `LMStudio.qwen3.8-9b-distill-uncensored-heretic-i1` | `0.70` | `0.90` | Volle redaktionelle Freiheit, keine moralisierenden Refusals. |

---

## ☁️ Cloud Modell-Profile (Flexible Fallkonfiguration via Valves)

In den Admin-Valves können die Cloud-Modelle für alle 5 typischen Praxisfälle flexibel und ohne Code-Änderung konfiguriert werden:

| Fall / Profil | Valve-Parameter | Standard-Modell (Open WebUI ID) | Temp | Top-P | Einsatzzweck |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Fall 1: High-End Coding** | `MODEL_CLOUD_HEAVY` | `openrouter.anthropic/claude-sonnet-4.5` | `0.40` | `0.90` | Hochkomplexe Fullstack-Architekturen & Mammut-Code. |
| **Fall 2: Deep Reasoning** | `MODEL_CLOUD_OPUS` | `openrouter.anthropic/claude-opus-4.6` | `0.50` | `0.90` | Tiefste strategische & philosophische Grundsatzanalysen (`#opus`). |
| **Fall 3: Complex Writing** | `MODEL_CLOUD_WRITING` | `openrouter.anthropic/claude-sonnet-4.5` | `0.45` | `0.90` | Anspruchsvolle Textanalyse & lange Ausarbeitungen (> 120 Wörter). |
| **Fall 4: Cloud Fast** | `MODEL_CLOUD_FAST` | `openrouter.google/gemini-3-flash-preview` | `0.60` | `0.90` | Schnelle allgemeine Cloud-Recherchen mit minimaler Latenz (`#flash`). |
| **Fall 5: Analytics & OpenAI** | `MODEL_CLOUD_GPT` | `openrouter.openai/gpt-5.2` | `0.30` | `0.90` | Analytische Aufgaben, Data Science & GPT-spezifische Workflows (`#gpt`). |

> 👤 **User-Valves:** Jeder Nutzer kann über `UserValves.preferred_cloud_model` ein persönliches Standard-Cloud-Modell in seinen Profileinstellungen hinterlegen.

---

## 🛡️ Das 4-Aktionen Privacy Gate (Perplexity Blueprint Parität)

Das integrierte Privacy Gate implementiert die 4 Säulen des Blueprint-Klassifikators (2-stufig: Regex + spaCy ML NER):
1. **Mask Value:** Namen, Orte, Organisationen und E-Mails werden mit reversiblen Tokens maskiert (`[[NAME_PER_1]]`). Cloud-Modelle operieren auf der Struktur, ohne private Daten zu halten.
2. **Keep Local:** Kritisches PII (`IBAN`, `CREDIT_CARD`, `SSN_US`, `URL_WITH_AUTH`) erzwingt einen sofortigen Hardware-Lockdown auf die lokale GPU-Workstation (**0 Cloud-Credits**).
3. **Refuse / Sanitize:** Sicherheitskritische URL-Zugangsdaten (`user:pass@`) werden bereinigt und neutralisiert.
4. **User Control / Override:** Nutzer können via Tags (`#local`, `#cloud`, `#opus`, `#sonnet`, `#r1`, `#code`) eingreifen und über User-Valves eigene Cloud-Präferenzen setzen. Selbst manuelle Cloud-Tags werden bei unmaskierter IBAN/Kreditkarte zum Schutz des Nutzers überstimmt.

---

## 🕹️ Manuelle Tags & Kurzbefehle

Du kannst das automatische Routing jederzeit durch kurze Präfixe im Prompt gezielt übersteuern (das Tag wird vor dem Senden automatisch entfernt):

* `#r1` oder `/r1`: Forciert DeepSeek-R1 (Temp `0.60`, Top-P `0.95`).
* `#code` oder `/coder`: Forciert den lokalen Coder.
* `#write` oder `#human`: Forciert Gemma 4 (Human Master Text-Stil).
* `#heretic` oder `#uncensored`: Forciert Heretic 9B (unzensiert).
* `#opus`: Forciert Claude Opus 4.6 (sofern keine kritischen PII vorliegen).
* `#sonnet` oder `#claude`: Forciert Claude Sonnet 4.5.
* `#gpt` oder `#openai`: Forciert OpenAI GPT-5.2.
* `#flash` oder `#gemini`: Forciert Gemini 3 Flash.
* `#local`: Forciert lokale Ausführung auf der Workstation.
* `#cloud`: Bevorzugt Cloud-Ausführung (sofern datenschutzkonform).

---

## 📦 Installation in Open WebUI

1. In Open WebUI als Admin anmelden.
2. Navigiere zu **Workspace ➔ Functions ➔ + (New Function)**.
3. Wähle als Typ: **Filter**.
4. Name: `Hybrid Model Router`.
5. Kopiere den vollständigen Inhalt von `model_router.py` in das Code-Feld.
6. **Speichern**.
7. Stelle unter **Valves** sicher:
   * `priority: 10` (muss höher sein als der PII-Filter auf `0`).
8. Aktiviere den Filter global unter **Admin Panel ➔ Settings ➔ Interface ➔ Default Filters**.

---

## 🔍 Transparenz & Audit in der UI

Unter jeder Antwortnachricht in Open WebUI findest du im Info-Icon (Metadaten) den genauen Entscheidungsweg des Routers:

```json
{
  "router_decision": {
    "original_model": "default-ui-model",
    "routed_to": "openrouter.anthropic/claude-sonnet-4.5",
    "target_node": "Cloud Provider (OpenRouter)",
    "profile": "cloud_heavy",
    "temperature": 0.40,
    "top_p": 0.90,
    "reason": "High-End Coding & Architektur -> Claude Sonnet 4.5 (Cloud)",
    "pii_detected": 0,
    "critical_pii_blocked": false
  }
}
```

---

## 📦 Enthaltene Kernkomponenten

| Komponente | Priorität | Aufgabe | Technologien |
| :--- | :--- | :--- | :--- |
| **[`pii_filter.py`](pii_filter.py)** | `0` | **Datenschutz & Anonymisierung:** Scannt Prompts, schwärzt sensible Daten (IBAN, Karten, Namen, Orte), speichert Mapping in `metadata.pii_map` und stellt im Outlet/Stream den Originaltext wieder her. | Regex + spaCy NER (`de_core_news_sm`), adaptiver Stream-Buffer |
| **[`model_router.py`](model_router.py)** | `10` | **Intelligentes Gateway:** Wertet PII-Counters, Aufgabentyp (Coding, Mathe, Text) und Komplexität aus. Sperrt bei kritischer PII die Cloud und setzt optimale Hyperparameter. | Intent Regex, Dynamic Model Swapping, Auto-Sampling |

---

## 🧪 Lokale Tests ausführen

```bash
# 1. PII-Filter Tests (Regex, Reversibilität, Stream-Buffer, Audit-Log):
python -m unittest test_pii_filter.py

# 2. Model-Router Tests (Privacy Gate, Intent-Routing, Tags, Sampling):
python -m unittest test_model_router.py
```

---

## 📘 Detaillierte Prompts & Praxistests

Vollständige Test-Prompts für alle fünf Hauptszenarien (Datenschutz-Lockdown, Deep Reasoning mit R1, Text-Veredelung, Cloud High-End und Privacy Gate Override-Test) findest du ausführlich dokumentiert in:
👉 **[`USER_GUIDE.md#8-praxis-beispiele--test-prompts-prompt-showcase`](USER_GUIDE.md)**

---

## ⚡ Streaming & Frontend-Synchronisation

Beim dynamischen Modell-Routing zur Laufzeit (z. B. von einem Cloud-Standardmodell zu einem lokalen Workstation-Modell bei sensiblen Daten) injiziert das Gateway `selected_model_id` in die Request-Metadaten:
```python
body["metadata"]["selected_model_id"] = selected_model
```
Dies stellt sicher, dass Open WebUI den SSE-Stream sofort mit `data: {"selected_model_id": ...}` initialisiert. Die Benutzeroberfläche ordnet den Stream somit nahtlos der richtigen Sprechblase zu und visualisiert Denk-Tokens (`reasoning_content`) ohne Verzögerung.


