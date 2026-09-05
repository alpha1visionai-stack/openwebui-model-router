"""
title: Intelligent Hybrid Model Router (Edge/Cloud Gateway)
author: walte
author_url: https://github.com/walte
version: 0.1.0
required_open_webui_version: 0.5.0
license: MIT

Intelligentes Gateway & Router für Open WebUI nach dem Vorbild von 'Perplexity Hybrid Compute'.
Arbeitet nahtlos mit dem vorgelagerten PII-Filter (openwebui-pii-filter) zusammen:

1. Datenschutz-Gate (Privacy Gate):
   - Prüft die vom PII-Filter erzeugten Metadaten (body.metadata.pii_counters).
   - Kritische Daten (IBAN, Kreditkarten, Credentials, Steuer-IDs) forzieren zwingend
     das lokale Modellnetzwerk (LM Studio auf der Workstation via Tailscale/LAN).
   - Bereits geschwärzte / unbedenkliche Anfragen dürfen für High-End-Reasoning
     in die Cloud (OpenRouter: Claude 4.5 Sonnet / Opus 4.6).

2. Task- & Intent-Klassifikation:
   - Coding: Routing an Qwen 2.5 Coder 14B (lokal) oder Claude 4.5 Sonnet (Cloud bei High-Complexity).
   - Reasoning: Routing an DeepSeek-R1 Distill 14B (lokal) mit erzwungenem Denkspielraum.
   - Writing & Chat: Routing an Gemma 4 12B (Human Master / Anti-KI Diktion).
   - Uncensored / Freies Denken: Routing an Heretic 9B (ohne Moralfilter).

3. Profilspezifische Hyperparameter-Injektion:
   - Passt Temperatur und Top-P automatisch an das gewählte Modellprofil an
     (z.B. DeepSeek-R1: Temp 0.60, Top-P 0.95; Coder: Temp 0.20, Top-P 0.85).

4. Manuelle Overrides:
   - Tags (#local, #cloud, #r1, #code, #write, #heretic, #opus) im Prompt werden
     ausgewertet und vor dem Absenden transparent bereinigt.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Modell-Profile & Standard-Parameter
# ---------------------------------------------------------------------------

PROFILES: dict[str, dict[str, Any]] = {
    "reasoning": {
        "label": "Reasoning (DeepSeek-R1)",
        "temperature": 0.60,
        "top_p": 0.95,
        "context_length": 16384,
        "rationale": "Niemals auf 0.0 setzen; benötigt explorativen Denkspielraum für <think>.",
    },
    "coding": {
        "label": "Coding (Qwen 2.5 Coder)",
        "temperature": 0.20,
        "top_p": 0.85,
        "context_length": 32768,
        "rationale": "Deterministische Syntax, präzise Dateidiffs und Code-Blöcke.",
    },
    "writing": {
        "label": "Writing & Chat (Gemma 4 / Human Master)",
        "temperature": 0.55,
        "top_p": 0.90,
        "context_length": 8192,
        "rationale": "Authentische menschliche Diktion ohne Stereotypen.",
    },
    "uncensored": {
        "label": "Uncensored (Heretic 9B)",
        "temperature": 0.70,
        "top_p": 0.90,
        "context_length": 16384,
        "rationale": "Volle redaktionelle Freiheit, keine moralisierenden Refusals.",
    },
    "cloud_heavy": {
        "label": "Cloud High-End (Claude Sonnet 4.5)",
        "temperature": 0.40,
        "top_p": 0.90,
        "context_length": 64000,
        "rationale": "Höchste Code- und Reasoning-Präzision in der Cloud.",
    },
    "cloud_opus": {
        "label": "Cloud Flagship (Claude Opus 4.6)",
        "temperature": 0.50,
        "top_p": 0.90,
        "context_length": 64000,
        "rationale": "Tiefenphilosophie, komplexe Strategien und Mammut-Dokumente.",
    },
    "cloud_fast": {
        "label": "Cloud High-Speed (Gemini 3 Flash)",
        "temperature": 0.60,
        "top_p": 0.90,
        "context_length": 32768,
        "rationale": "Sehr schnelle Cloud-Antworten bei minimaler Latenz.",
    },
}


# ---------------------------------------------------------------------------
# Konfiguration (Valves)
# ---------------------------------------------------------------------------

class Valves(BaseModel):
    priority: int = Field(
        default=10,
        description="Filter-Reihenfolge. Muss HÖHER sein als der PII-Filter (der auf 0 läuft), "
                    "damit die PII-Metadaten bereits zur Verfügung stehen.",
    )

    # --- Lokale Modelle (LM Studio auf Workstation via Tailscale/LAN) ---
    MODEL_LOCAL_REASONING: str = Field(
        default="LMStudio.deepseek-r1-distill-qwen-14b",
        description="Lokales Modell für Logik, Mathe & Chain-of-Thought",
    )
    MODEL_LOCAL_CODING: str = Field(
        default="LMStudio.qwen2.5-coder-14b-instruct",
        description="Lokales Modell für Programmierung & Skripte",
    )
    MODEL_LOCAL_WRITING: str = Field(
        default="LMStudio.google/gemma-4-12b-qat",
        description="Lokales Modell für Text, Schreiben & Standard-Chat (Human Master)",
    )
    MODEL_LOCAL_UNCENSORED: str = Field(
        default="LMStudio.qwen3.8-9b-distill-uncensored-heretic-i1",
        description="Lokales unzensiertes Modell für freies Denken & sensible Recherche",
    )

    # --- Cloud Modelle (OpenRouter auf Minisforum Server) ---
    MODEL_CLOUD_HEAVY: str = Field(
        default="openrouter.anthropic/claude-sonnet-4.5",
        description="Cloud High-End Modell für hochkomplexes Coding & Architektur",
    )
    MODEL_CLOUD_OPUS: str = Field(
        default="openrouter.anthropic/claude-opus-4.6",
        description="Cloud Flagship Modell für tiefste Synthesen",
    )
    MODEL_CLOUD_FAST: str = Field(
        default="openrouter.google/gemini-3-flash-preview",
        description="Schnelles Cloud Modell für mittlere, unkritische Anfragen",
    )

    # --- Datenschutz & Privacy Gate ---
    STRICT_LOCAL_ON_ANY_PII: bool = Field(
        default=False,
        description="Wenn True: Jede PII (auch vom Filter maskierte) erzwingt sofort ein lokales Modell.",
    )
    CRITICAL_PII_TYPES: list[str] = Field(
        default_factory=lambda: ["IBAN", "CREDIT_CARD", "SSN_US", "URL_WITH_AUTH", "TAX_ID_DE"],
        description="PII-Kategorien, die NIEMALS in die Cloud dürfen (selbst wenn maskiert).",
    )

    # --- Automatische Hyperparameter-Anpassung ---
    APPLY_OPTIMAL_SAMPLING_PARAMS: bool = Field(
        default=True,
        description="Infiltriert die für das Modellprofil optimalen Temperature- und Top-P-Werte.",
    )

    # --- Schwellenwerte ---
    COMPLEXITY_WORD_THRESHOLD: int = Field(
        default=120,
        description="Wortanzahl, ab der ein Prompt als hochkomplex eingestuft wird.",
    )
    CODE_COMPLEXITY_LINE_THRESHOLD: int = Field(
        default=25,
        description="Zeilenanzahl Code, ab der Code-Aufgaben an Cloud High-End delegiert werden.",
    )


class UserValves(BaseModel):
    enabled: bool = Field(
        default=True,
        description="Model Router für diese:n Nutzer:in aktivieren.",
    )
    prefer_local: bool = Field(
        default=False,
        description="Nutzer-Präferenz: Wenn möglich immer lokale Modelle bevorzugen.",
    )


# ---------------------------------------------------------------------------
# Filter-Klasse
# ---------------------------------------------------------------------------

class Filter:
    Valves = Valves
    UserValves = UserValves

    def __init__(self):
        self.valves = Valves()

    def _extract_last_user_message(self, body: dict) -> tuple[int, str]:
        """Ermittelt Index und Text der letzten User-Nachricht."""
        msgs = body.get("messages") or []
        for i in range(len(msgs) - 1, -1, -1):
            m = msgs[i]
            if isinstance(m, dict) and m.get("role") == "user":
                content = m.get("content")
                if isinstance(content, str):
                    return i, content
        return -1, ""

    def _parse_manual_overrides(self, text: str) -> tuple[str, Optional[str], Optional[str]]:
        """
        Prüft auf explizite Tags wie #r1, #code, #write, #heretic, #local, #cloud, #opus.
        Entfernt das gefundene Tag aus dem Text und liefert (clean_text, target_profile, forced_location).
        """
        t = text
        target_profile = None
        forced_location = None

        patterns = [
            (r"#r1\b|/r1\b|#reasoning\b", "reasoning", "local"),
            (r"#code\b|/coder\b|#coder\b", "coding", None),
            (r"#write\b|#text\b|#human\b", "writing", "local"),
            (r"#heretic\b|#uncensored\b", "uncensored", "local"),
            (r"#opus\b", "cloud_opus", "cloud"),
            (r"#sonnet\b|#claude\b", "cloud_heavy", "cloud"),
            (r"#flash\b", "cloud_fast", "cloud"),
            (r"#local\b|/local\b", None, "local"),
            (r"#cloud\b|/cloud\b", None, "cloud"),
        ]

        for pattern, profile, loc in patterns:
            if re.search(pattern, t, flags=re.IGNORECASE):
                target_profile = profile
                forced_location = loc
                t = re.sub(pattern, "", t, flags=re.IGNORECASE).strip()
                break

        return t, target_profile, forced_location

    def _detect_intent(self, text: str) -> tuple[str, bool]:
        """
        Analysiert den Intent des Prompts und liefert (intent_type, is_high_complexity).
        intent_type: 'coding' | 'reasoning' | 'uncensored' | 'writing' | 'general'
        """
        t = text.lower()
        word_count = len(text.split())
        code_lines = len(re.findall(r"(\n\s*(?:def|class|function|import|const|let|var|SELECT|UPDATE|DELETE|\{|\}))", text))

        # 1. Unzensiert / Tabuthemen / Freies Denken / Philosophie ohne Filter
        uncensored_triggers = [
            r"unzensiert", r"heretic", r"ohne filter", r"tabu",
            r"keine zensur", r"kontrovers", r"ohne moralapostel",
            r"rohfassung ohne belehrung", r"tabulose darstellung"
        ]
        if any(re.search(p, t) for p in uncensored_triggers):
            return "uncensored", False

        # 2. Coding & Entwicklung
        code_triggers = [
            r"```", r"\bdef\s+", r"\bclass\s+", r"\bfunction\b", r"\bimport\s+",
            r"refactor", r"debug", r"bugfix", r"sql", r"dockerfile", r"regex",
            r"(schreibe|erstelle|baue)\s+(ein|eine|einen)?\s*(python|typescript|bash|powershell|sql|script|skript|programm|funktion|code|logik|algorithmus)",
            r"\b(code|coding|skript|script|programm|algorithmus|funktion|abrechnungs-logik|logik|klasse|datenbank|abfrage)\b",
            r"api endpoint", r"pull request", r"stack trace", r"unittest"
        ]
        is_coding = any(re.search(p, t) for p in code_triggers) or code_lines >= 3
        if is_coding:
            is_complex = (
                code_lines >= self.valves.CODE_COMPLEXITY_LINE_THRESHOLD
                or word_count >= self.valves.COMPLEXITY_WORD_THRESHOLD
                or any(k in t for k in ["architektur", "design pattern", "microservice", "fullstack", "optimierung"])
            )
            return "coding", is_complex

        # 3. Deep Reasoning & mathematische / formale Logik
        reasoning_triggers = [
            r"beweise", r"mathematisch", r"schritt für schritt herleiten",
            r"chain of thought", r"formale logik", r"deduktiv",
            r"widerspruchsbeweis", r"algorithmus analyse", r"strategie evaluierung"
        ]
        if any(re.search(p, t) for p in reasoning_triggers):
            return "reasoning", True

        # 4. Schreiben, Lektorat & Veredelung
        writing_triggers = [
            r"stilistisch", r"aufsatz", r"erörterung", r"lektorat", r"text-master",
            r"menschlich formulieren", r"anti-ki", r"umschreiben", r"sprachrhythmus",
            r"bildungsdeutsch", r"korrekturlesen", r"überarbeite den text", r"/oberstufe"
        ]
        if any(re.search(p, t) for p in writing_triggers):
            return "writing", False

        # 5. Generelle Komplexität
        is_complex = word_count >= self.valves.COMPLEXITY_WORD_THRESHOLD
        return "general", is_complex

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        """
        Interzeptiert den Request vor dem Absenden an das LLM:
        - Wertet PII-Metadaten und Prompt-Inhalt aus
        - Schreibt body['model'] auf das optimale Modell um
        - Infiltriert ggf. modellspezifische Parameter (temperature, top_p)
        """
        if not isinstance(body, dict):
            return body

        # UserValves Check
        if __user__ and isinstance(__user__, dict):
            uv = __user__.get("valves")
            if isinstance(uv, UserValves) and not uv.enabled:
                return body
            prefer_local_user = bool(getattr(uv, "prefer_local", False))
        else:
            prefer_local_user = False

        # 1. PII-Metadaten vom pii_filter abrufen
        metadata = body.get("metadata") or {}
        pii_counters = metadata.get("pii_counters") or {}
        pii_map = metadata.get("pii_map") or {}
        total_pii_count = sum(pii_counters.values()) or len(pii_map)

        # Audit-Liste der behandelten PII-Elemente für UI-Transparenz
        pii_elements = []
        for token, original in pii_map.items():
            match = re.search(r"\[\[([A-Z_]+)_\d+\]\]", token)
            cat = match.group(1) if match else "PII"
            pii_elements.append({
                "token": token,
                "kategorie": cat,
                "original": original,
                "status": "Im Prompt geschwärzt ➔ In Antwort wiederhergestellt",
            })

        # 2. Letzte User-Nachricht extrahieren
        user_idx, raw_user_text = self._extract_last_user_message(body)
        if user_idx == -1 or not raw_user_text:
            return body

        # 3. Manuelle Overrides (#r1, #code, #local, #cloud etc.) prüfen
        clean_text, manual_profile, forced_location = self._parse_manual_overrides(raw_user_text)
        if clean_text != raw_user_text:
            body["messages"][user_idx]["content"] = clean_text

        # 4. Privacy Gate Prüfung
        has_critical_pii = any(k in pii_counters for k in self.valves.CRITICAL_PII_TYPES)
        force_local_privacy = False
        privacy_reason = ""

        if self.valves.STRICT_LOCAL_ON_ANY_PII and total_pii_count > 0:
            force_local_privacy = True
            privacy_reason = f"Datenschutz-Regel: PII vorhanden ({total_pii_count} Tokens) -> Lokal erzwungen"
        elif has_critical_pii:
            force_local_privacy = True
            found_crit = [k for k in self.valves.CRITICAL_PII_TYPES if k in pii_counters]
            privacy_reason = f"Datenschutz-Sperre: Kritische PII ({found_crit}) -> LM Studio Workstation zwingend"

        # 5. Intent & Komplexität ermitteln
        intent, is_complex = self._detect_intent(clean_text)

        # 6. Routing-Entscheidung treffen
        selected_model = ""
        applied_profile = "writing"
        routing_reason = ""

        # A: Manueller Profil-Override hat Vorrang (außer Datenschutz sperrt Cloud)
        if manual_profile:
            if manual_profile == "reasoning":
                selected_model = self.valves.MODEL_LOCAL_REASONING
                applied_profile = "reasoning"
                routing_reason = "Manueller Override: #r1 / Reasoning gewählt"
            elif manual_profile == "coding":
                if forced_location == "cloud" and not force_local_privacy:
                    selected_model = self.valves.MODEL_CLOUD_HEAVY
                    applied_profile = "cloud_heavy"
                    routing_reason = "Manueller Override: Cloud Coder gewählt"
                else:
                    selected_model = self.valves.MODEL_LOCAL_CODING
                    applied_profile = "coding"
                    routing_reason = "Manueller Override: Lokaler Coder gewählt"
            elif manual_profile == "writing":
                selected_model = self.valves.MODEL_LOCAL_WRITING
                applied_profile = "writing"
                routing_reason = "Manueller Override: #write / Human Master gewählt"
            elif manual_profile == "uncensored":
                selected_model = self.valves.MODEL_LOCAL_UNCENSORED
                applied_profile = "uncensored"
                routing_reason = "Manueller Override: #heretic / Unzensiert gewählt"
            elif manual_profile == "cloud_opus":
                if not force_local_privacy:
                    selected_model = self.valves.MODEL_CLOUD_OPUS
                    applied_profile = "cloud_opus"
                    routing_reason = "Manueller Override: #opus gewählt"
                else:
                    selected_model = self.valves.MODEL_LOCAL_REASONING
                    applied_profile = "reasoning"
                    routing_reason = f"#opus angefordert, aber wegen {privacy_reason} auf DeepSeek-R1 (WS) umgeleitet"
            elif manual_profile in ("cloud_heavy", "cloud_fast"):
                if not force_local_privacy:
                    selected_model = self.valves.MODEL_CLOUD_HEAVY if manual_profile == "cloud_heavy" else self.valves.MODEL_CLOUD_FAST
                    applied_profile = manual_profile
                    routing_reason = f"Manueller Override: {manual_profile} gewählt"
                else:
                    selected_model = self.valves.MODEL_LOCAL_CODING if intent == "coding" else self.valves.MODEL_LOCAL_REASONING
                    applied_profile = "coding" if intent == "coding" else "reasoning"
                    routing_reason = f"Cloud angefordert, aber wegen {privacy_reason} auf Workstation umgeleitet"

        # B: Automatisches Routing
        if not selected_model:
            # Fall 1: Datenschutz forciert lokale Ausführung
            if force_local_privacy:
                if intent == "coding":
                    selected_model = self.valves.MODEL_LOCAL_CODING
                    applied_profile = "coding"
                elif intent == "reasoning":
                    selected_model = self.valves.MODEL_LOCAL_REASONING
                    applied_profile = "reasoning"
                elif intent == "uncensored":
                    selected_model = self.valves.MODEL_LOCAL_UNCENSORED
                    applied_profile = "uncensored"
                else:
                    selected_model = self.valves.MODEL_LOCAL_WRITING
                    applied_profile = "writing"
                routing_reason = privacy_reason

            # Fall 2: Manueller #local Tag oder Nutzer-Präferenz
            elif forced_location == "local" or prefer_local_user:
                if intent == "coding":
                    selected_model = self.valves.MODEL_LOCAL_CODING
                    applied_profile = "coding"
                elif intent == "reasoning":
                    selected_model = self.valves.MODEL_LOCAL_REASONING
                    applied_profile = "reasoning"
                elif intent == "uncensored":
                    selected_model = self.valves.MODEL_LOCAL_UNCENSORED
                    applied_profile = "uncensored"
                else:
                    selected_model = self.valves.MODEL_LOCAL_WRITING
                    applied_profile = "writing"
                routing_reason = "Lokale Ausführung gewählt (0 Cloud-Credits)"

            # Fall 3: Unzensierte Anfragen -> Immer Heretic auf Workstation
            elif intent == "uncensored":
                selected_model = self.valves.MODEL_LOCAL_UNCENSORED
                applied_profile = "uncensored"
                routing_reason = "Intent: Unzensiert / Tabuthemen -> Heretic 9B auf Workstation"

            # Fall 4: High-End Coding & Deep Reasoning (Cloud)
            elif (intent == "coding" and is_complex) or (forced_location == "cloud" and intent == "coding"):
                selected_model = self.valves.MODEL_CLOUD_HEAVY
                applied_profile = "cloud_heavy"
                routing_reason = "High-End Coding & Architektur -> Claude Sonnet 4.5 (Cloud)"

            # Fall 5: Standard Coding & Skripte -> Lokaler Coder (schnell, gratis)
            elif intent == "coding":
                selected_model = self.valves.MODEL_LOCAL_CODING
                applied_profile = "coding"
                routing_reason = "Standard Coding & Skripte -> Qwen 2.5 Coder 14B auf Workstation"

            # Fall 6: Mathematische Herleitungen & Logik
            elif intent == "reasoning":
                selected_model = self.valves.MODEL_LOCAL_REASONING
                applied_profile = "reasoning"
                routing_reason = "Deep Reasoning & Logik -> DeepSeek-R1 Distill 14B auf Workstation"

            # Fall 7: Sehr lange / hochkomplexe Textanalyse ohne PII-Sperre
            elif is_complex and not total_pii_count:
                selected_model = self.valves.MODEL_CLOUD_HEAVY
                applied_profile = "cloud_heavy"
                routing_reason = "Hohe Textkomplexität ohne PII -> Claude Sonnet 4.5 (Cloud)"

            # Fall 8: Standard Writing, Lektorat, Chat, Routine
            else:
                selected_model = self.valves.MODEL_LOCAL_WRITING
                applied_profile = "writing"
                routing_reason = "Writing, Chat & Routine -> Gemma 4 12B auf Workstation (0 Cloud-Credits)"

        # 7. Modell im Request überschreiben
        original_model = body.get("model", "")
        body["model"] = selected_model

        # 8. Hyperparameter-Injektion (Temperature & Top-P)
        profile_data = PROFILES.get(applied_profile, {})
        if self.valves.APPLY_OPTIMAL_SAMPLING_PARAMS and profile_data:
            body["temperature"] = profile_data["temperature"]
            body["top_p"] = profile_data["top_p"]

        # 9. Audit- & Debug-Metadaten für die Open-WebUI Sprechblasen-Info
        if "metadata" not in body:
            body["metadata"] = {}
        body["metadata"]["router_decision"] = {
            "original_model": original_model,
            "routed_to": selected_model,
            "target_node": "Workstation (LM Studio via Tailscale)" if "LMStudio" in selected_model else "Cloud Provider (OpenRouter)",
            "profile": applied_profile,
            "temperature": body.get("temperature"),
            "top_p": body.get("top_p"),
            "reason": routing_reason,
            "pii_detected": total_pii_count,
            "critical_pii_blocked": has_critical_pii,
            "pii_behandelte_elemente": pii_elements if pii_elements else [],
        }

        # Separater pii_audit Key für direkte Sichtbarkeit in der Info-Box
        if pii_elements:
            body["metadata"]["pii_audit"] = {
                "anzahl_behandelt": len(pii_elements),
                "status": "Erfolgreich maskiert & zur Re-Hydrierung vorgemerkt",
                "elemente": pii_elements,
            }

        log.info(f"[Model Router] '{original_model}' -> '{selected_model}' [{routing_reason}] (T={body.get('temperature')}, P={body.get('top_p')})")
        return body
