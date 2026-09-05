# Open WebUI: Intelligent Hybrid Model Router (Edge/Cloud Gateway)

Ein intelligentes Routing-Gateway für [Open WebUI](https://github.com/open-webui/open-webui) (v0.5+), inspiriert vom **„Hybrid Compute“**-Ansatz (wie bei *Perplexity Computer*).

Routet Anfragen dynamisch zwischen:
1. **Lokaler Workstation (LM Studio via Tailscale/LAN):** Für vertrauliche Daten, PII, Routineaufgaben und unzensierte Recherchen (**0 Cloud-Credits**).
2. **Cloud High-End (Cortecs / OpenRouter):** Für hochkomplexes Reasoning, Architektur und Mammut-Code (Alibaba Qwen 3.5 397B MoE / DeepSeek V4 / Claude Sonnet 4.5 / Opus 4.6).

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
                    │    Workstation (Tailscale)   │        │ Cloud APIs (Cortecs/OR)│
                    │       LM Studio (:1234)      │        │                       │
                    │ ──────────────────────────── │        │ ───────────────────── │
                    │ • DeepSeek-R1 (Logik/Mathe)  │        │ • Qwen 3.5 397B MoE   │
                    │ • Qwen 2.5 Coder (Skripte)   │        │ • DeepSeek V4 Flash   │
                    │ • Gemma 4 (Anti-KI / Writing)│        │ • Claude Sonnet 4.5   │
                    │ • Heretic 9B (Unzensiert)    │        │ • Claude Opus 4.6     │
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
| **Fall 1: High-End Coding** | `MODEL_CLOUD_HEAVY` | `Cortecs.qwen3.5-397b-a17b` | `0.20` | `0.85` | Hochkomplexe Fullstack-Architekturen & Mammut-Code (Alibaba Qwen 3.5 397B MoE Open-Weight). |
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

* `#direct`, `#keep`, `#lock`: **Direkt-Durchstellung.** Behält exakt das im Menü gewählte Modell 1:1 bei (Bypass).
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

## 🎯 Nur interne Modelle nutzen & Modellauswahl steuern

Möchtest du nur interne Modelle (z. B. Gemma 4 oder Qwen Coder) nutzen und die automatische Modellauswahl steuern oder umgehen?

> 🔒 **PII-Datenschutz bleibt 100 % aktiv:**  
> Der PII-Filter (`pii_filter_reversible`, Priorität 0) und der Model Router (`hybrid_model_router`, Priorität 10) sind **vollständig unabhängig**. Wenn du den Router abschaltest oder umgehst, werden IBANs, Namen und E-Mails im Prompt weiterhin geschwärzt und in der Antwort restauriert!

* **Option 4: Automatische Beibehaltung intern gewählter Modelle (Standardmäßig aktiv!):**
  - Wählst du im Open WebUI Menü oben explizit ein internes Modell (z. B. `LMStudio.google/gemma-4-12b-qat`), erkennt der Router deine Wahl und behält dieses Modell automatisch bei (kein Umbiegen auf Qwen Coder mehr!).
  - Gesteuert über `RESPECT_MANUAL_LOCAL_SELECTION: true`.
* **Tag `#direct` oder `#keep`:**
  - Schicke `#direct` im Prompt mit, um das aktuell im Menü gewählte Modell sofort 1:1 ohne Umleitung auszuführen.
* **Option 2: Reiner Airgap-Modus (100 % lokal mit Aufteilung):**
  - Tag `#local` im Prompt oder in den User-Valves `prefer_local = true`. Bleibt immer lokal auf der Workstation (0 Cloud-Credits).
* **Option 3: Gezieltes Modell-Pinning:**
  - Nutze `#write` (Gemma 4), `#code` (Qwen Coder), `#r1` (DeepSeek-R1) oder `#heretic` (Heretic 9B) direkt im Prompt.
* **Option 1: Router komplett ausschalten (100 % manuelle Kontrolle):**
  - *Pro Nutzer:* Profileinstellungen ➔ *Functions ➔ Hybrid Model Router ➔ Valves:* `enabled = false`.
  - *Global:* Admin-Panel ➔ *Functions ➔ Hybrid Model Router:* Hauptschalter auf **Aus**.

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

Beim dynamischen Modell-Routing zur Laufzeit (z. B. von einem Cloud-Standardmodell zu einem lokalen Workstation-Modell bei sensiblen Daten) injiziert das Gateway `selected_model_id` bei interaktiven WebUI-Chats in die Request-Metadaten:
```python
if is_interactive_chat:
    body["metadata"]["selected_model_id"] = selected_model
```
Dies stellt sicher, dass Open WebUI den SSE-Stream für den Browser sofort mit `data: {"selected_model_id": ...}` initialisiert, während externe API-Clients (wie OpenCode / Vercel AI SDK) ein 100% standardkonformes OpenAI-Chunk-Schema ohne Validierungsfehler erhalten.

---

## 💻 OpenCode Integration (Weg 1)

Das Gateway dient gleichzeitig als OpenAI-kompatibler Endpunkt für autonome Coding-Agenten wie **OpenCode** (Web-UI auf Port 4096 & CLI):
* **Provider:** `@ai-sdk/openai-compatible`
* **BaseURL:** `http://open-webui:8080/api` (intern im Docker `caddy_network`)
* **API-Key:** Open WebUI Bearer Key (`sk-opencode-router-...`)
* **Vollständige Modellauswahl in OpenCode:**
  1. `🛡️ Auto-Router (Hybrid Gateway + PII)`: Automatische Routing-Entscheidung und Kontext-Eskalation.
  2. `⚡ Qwen 2.5 Coder 14B (Lokal: Code)`: Lokale Code-Entwicklung auf der RTX 4090 Workstation.
  3. `🧠 DeepSeek-R1 Distill 14B (Lokal: Reasoning)`: Lokale mathematische Logik & CoT.
  4. `🌐 Google Gemma 4 12B (Lokal: Text & Chat)`: Lokaler Textallrounder (Human Master Stil).
  5. `🔓 Qwen 3.8 Heretic 9B (Lokal: Unzensiert)`: Lokales unzensiertes Modell für freie Recherche.
  6. `🇨🇳 Alibaba Qwen 3.5 397B MoE (Cloud Open-Weight)`: Chinesisches Open-Weight Flaggschiff für High-End Architektur.
  7. `⚡ DeepSeek V4 Flash (Cloud Speed)`: Ultraschnelle Cloud-Antworten (< 2s).
  8. `🧠 Claude Sonnet 4.5 (Cloud Fallback)`: Proprietäres Fallback-Modell.
* **Features:** Voller Zero-Leakage PII-Schutz für Code, automatische Kontext-Eskalation an Qwen 3.5 397B MoE bei großen Agenten-Prompts (>7k Tokens) und Live-Deanonymisierung von Tool-Call Argumenten (`delta.tool_calls`).

Details & vollständige `opencode.json`: 👉 **[`USER_GUIDE.md#10-externe-entwickler-tools--opencode-integration`](USER_GUIDE.md)**



