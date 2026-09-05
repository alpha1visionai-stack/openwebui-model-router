# Open WebUI: Intelligent Hybrid Model Router (Edge/Cloud Gateway)

Ein intelligentes Routing-Gateway für [Open WebUI](https://github.com/open-webui/open-webui) (v0.5+), inspiriert vom **„Hybrid Compute“**-Ansatz (wie bei *Perplexity Computer*).

Routet Anfragen dynamisch zwischen:
1. **Lokaler Workstation (LM Studio via Tailscale/LAN):** Für vertrauliche Daten, PII, Routineaufgaben und unzensierte Recherchen (**0 Cloud-Credits**).
2. **Cloud High-End (OpenRouter):** Für hochkomplexes Reasoning, Architektur und Mammut-Code (Claude 4.5 Sonnet / Opus 4.6).

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

## ☁️ Cloud Modell-Profile (OpenRouter auf Minisforum Server)

| Profil | Modellbezeichnung (Open WebUI ID) | Temp | Top-P | Einsatzzweck |
| :--- | :--- | :--- | :--- | :--- |
| **🚀 Cloud High-End** | `openrouter.anthropic/claude-sonnet-4.5` | `0.40` | `0.90` | Hochkomplexe Fullstack-Architekturen, Bug-Hunting & Systementwürfe. |
| **🏛️ Cloud Flagship** | `openrouter.anthropic/claude-opus-4.6` | `0.50` | `0.90` | Strategische Grundsatzanalysen & Mammut-Dokumente. |
| **⚡ Cloud High-Speed** | `openrouter.google/gemini-3-flash-preview` | `0.60` | `0.90` | Schnelle allgemeine Cloud-Abfragen mit minimaler Latenz. |

---

## 🛡️ Das 4-Stufen Privacy Gate

1. **Kritische PII:** Erkennt der PII-Filter `IBAN`, `CREDIT_CARD`, `SSN_US`, `URL_WITH_AUTH` oder `TAX_ID_DE`, wird ein Routing in die Cloud **sofort blockiert**. Die Anfrage wird zwingend an die lokale Workstation übergeben.
2. **Maskierte Standard-PII:** Namen, Städte und Firmen werden vom PII-Filter maskiert (`[[NAME_PER_1]]`). Das Cloud-Modell sieht nur abstrakte Entitäten und liefert die Struktur zurück.
3. **Zero Cloud Credits:** Routine-Aufgaben (Zusammenfassungen, Übersetzungen, Standard-Chat) bleiben lokal auf der Workstation und verbrauchen **0 API-Credits**.
4. **Manueller Override Schutz:** Selbst wenn der Nutzer explizit `#cloud` oder `#opus` angibt, verhindert das Privacy Gate bei kritischen PII das Verlassen des lokalen Netzes.

---

## 🕹️ Manuelle Tags & Kurzbefehle

Du kannst das automatische Routing jederzeit durch kurze Präfixe im Prompt gezielt übersteuern (das Tag wird vor dem Senden automatisch entfernt):

* `#r1` oder `/r1`: Forciert DeepSeek-R1 (Temp `0.60`, Top-P `0.95`).
* `#code` oder `/coder`: Forciert den lokalen Coder.
* `#write` oder `#human`: Forciert Gemma 4 (Human Master Text-Stil).
* `#heretic` oder `#uncensored`: Forciert Heretic 9B (unzensiert).
* `#opus`: Forciert Claude Opus 4.6 (sofern keine kritischen PII vorliegen).
* `#sonnet` oder `#claude`: Forciert Claude Sonnet 4.5.
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

## 🧪 Lokale Tests ausführen

```bash
python -m unittest test_model_router.py
```
