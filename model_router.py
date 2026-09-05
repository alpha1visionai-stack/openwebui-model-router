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
   - Coding: Routing an Qwen 2.5 Coder 14B (lokal) oder Qwen 3.5 397B MoE (Cloud bei High-Complexity).
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
        "label": "Cloud High-End (Qwen 3.5 397B MoE)",
        "temperature": 0.20,
        "top_p": 0.85,
        "context_length": 64000,
        "rationale": "Höchste Code- und Reasoning-Präzision in der Cloud (Alibaba Qwen 3.5 397B MoE).",
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
    "cloud_gpt": {
        "label": "Cloud High-End (OpenAI GPT-5.2)",
        "temperature": 0.30,
        "top_p": 0.90,
        "context_length": 64000,
        "rationale": "OpenAI GPT-5.2 für analytische Aufgaben, Data-Science & GPT-spezifische Workflows.",
    },
}

# ---------------------------------------------------------------------------
# Bekannte inaktive / fehlerhafte Modelle (Automatisches Fallback zur Fehlervermeidung)
# ---------------------------------------------------------------------------

KNOWN_INACTIVE_MODELS: dict[str, str] = {
    # 404 Nicht gefunden: Auf OpenRouter existiert kein google/gemini-3-pro-preview Endpunkt
    "openrouter.google/gemini-3-pro-preview": "openrouter.google/gemini-3-flash-preview",
    "google/gemini-3-pro-preview": "google/gemini-3-flash-preview",
    # 400 Deaktivierte Presets auf OpenRouter
    "openrouter.@preset/deepseek-v4": "openrouter.~deepseek/deepseek-v4-flash-latest",
    "@preset/deepseek-v4": "~deepseek/deepseek-v4-flash-latest",
    "openrouter.@preset/claude-code-google": "openrouter.anthropic/claude-sonnet-4.5",
    "@preset/claude-code-google": "anthropic/claude-sonnet-4.5",
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

    # --- Cloud Modelle (OpenRouter / Fall-spezifisch flexibel konfigurierbar) ---
    MODEL_CLOUD_HEAVY: str = Field(
        default="Cortecs.qwen3.5-397b-a17b",
        description="Fall 1: High-End Coding & Systemarchitektur in der Cloud (Alibaba Qwen 3.5 397B MoE)",
    )
    MODEL_CLOUD_OPUS: str = Field(
        default="openrouter.anthropic/claude-opus-4.6",
        description="Fall 2: Deep Reasoning, Philosophie & Strategie in der Cloud",
    )
    MODEL_CLOUD_WRITING: str = Field(
        default="openrouter.anthropic/claude-sonnet-4.5",
        description="Fall 3: Komplexe Textanalyse & Redaktion in der Cloud (lange Prompts)",
    )
    MODEL_CLOUD_FAST: str = Field(
        default="openrouter.google/gemini-3-flash-preview",
        description="Fall 4: Schnelle unkritische Cloud-Abfragen (High-Speed)",
    )
    MODEL_CLOUD_GPT: str = Field(
        default="openrouter.openai/gpt-5.2",
        description="Fall 5: Analytik, Data-Science & OpenAI-spezifische Aufgaben",
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
    MAX_LOCAL_CONTEXT_TOKENS: int = Field(
        default=7000,
        description="Maximale geschätzte Tokenanzahl (gesamter Chat-Verlauf inkl. System-Prompt), die an lokale Modelle gesendet werden darf. Übersteigt der Request diesen Schwellenwert (z. B. bei Coding-Agenten wie OpenCode mit großen System-Prompts), wird automatisch an Cloud Heavy delegiert, um 'Context size exceeded' Fehler auf der Workstation zu verhindern (sofern keine kritische PII vorliegt).",
    )


    # --- Manuelle Auswahl & Pinning (Option 4) ---
    RESPECT_MANUAL_LOCAL_SELECTION: bool = Field(
        default=True,
        description="Wenn True: Wenn der Benutzer im WebUI explizit ein internes Modell (z. B. LMStudio...) gewählt hat, wird dieses 1:1 beibehalten und nicht umgeroutet.",
    )
    LOCAL_MODEL_PREFIXES: list[str] = Field(
        default_factory=lambda: ["LMStudio.", "local.", "ollama.", "text-master", "heretic-uncensored"],
        description="Präfixe oder Bezeichnungen von Modellen, die als interne/lokale Modelle gelten.",
    )

    # --- UI & Transparenz ---
    SHOW_ROUTING_BANNER: bool = Field(
        default=True,
        description="Fügt am Anfang jeder KI-Antwort ein transparentes Routing- & Datenschutz-Banner ein.",
    )
    ROUTING_BANNER_COLLAPSIBLE: bool = Field(
        default=False,
        description="Wenn True: Rendert das Banner als aufklappbare <details>-Box. Wenn False: Rendert ein kompaktes Zitat-Banner (>).",
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
    respect_manual_local: bool = Field(
        default=True,
        description="Interne Modellauswahl respektieren: Wenn du oben ein internes Modell wählst, wird es direkt verwendet.",
    )
    preferred_cloud_model: str = Field(
        default="",
        description="Optionale Nutzer-Präferenz: Eigenes bevorzugtes Cloud-Modell (z.B. openrouter.openai/gpt-5.2), das standardmäßig für alle Cloud-Routings genutzt wird.",
    )


# In-Memory Cache zur Ausfallsicherung zwischen Inlet und Outlet
_GLOBAL_ROUTER_STORE: dict[str, dict[str, Any]] = {}


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
            (r"#direct\b|/direct\b|#keep\b|/keep\b|#lock\b|/lock\b|#raw\b", "direct", "direct"),
            (r"#r1\b|/r1\b|#reasoning\b", "reasoning", "local"),
            (r"#code\b|/coder\b|#coder\b", "coding", None),
            (r"#write\b|#text\b|#human\b", "writing", "local"),
            (r"#heretic\b|#uncensored\b", "uncensored", "local"),
            (r"#opus\b", "cloud_opus", "cloud"),
            (r"#gpt5\b|#gpt-5\b|#gpt\b|#openai\b", "cloud_gpt", "cloud"),
            (r"#sonnet\b|#claude\b", "cloud_heavy", "cloud"),
            (r"#flash\b|#gemini\b", "cloud_fast", "cloud"),
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

    def _profile_for_model(self, model_id: str, default_intent: str) -> str:
        """Ermittelt das am besten passende Sampling-Profil (Temperature, Top-P) für ein beliebiges Modell."""
        m = (model_id or "").lower()
        if "coder" in m or "coding" in m or m == self.valves.MODEL_LOCAL_CODING.lower():
            return "coding"
        elif "r1" in m or "reason" in m or m == self.valves.MODEL_LOCAL_REASONING.lower():
            return "reasoning"
        elif "heretic" in m or "uncensor" in m or m == self.valves.MODEL_LOCAL_UNCENSORED.lower():
            return "uncensored"
        elif "gemma" in m or m == self.valves.MODEL_LOCAL_WRITING.lower():
            return "writing"
        elif "opus" in m:
            return "cloud_opus"
        elif "sonnet" in m or "claude" in m:
            return "cloud_heavy"
        elif "gpt" in m or "openai" in m:
            return "cloud_gpt"
        elif "flash" in m or "gemini" in m:
            return "cloud_fast"
        return default_intent if default_intent in PROFILES else "writing"

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
            r"(schreibe|erstelle|baue)\s+(ein|eine|einen)?\s*(python|typescript|bash|powershell|sql|script|skript|programm|funktion|code|logik|algorithmus|datei)",
            r"\b(code|coding|skript|script|programm|algorithmus|funktion|abrechnungs-logik|logik|klasse|datenbank|abfrage|python-datei)\b",
            r"\b\w+\.(py|js|ts|jsx|tsx|sh|sql|json|html|css|yaml|yml)\b",
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

    def inlet(
        self,
        body: dict,
        __metadata__: Optional[dict] = None,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable] = None,
        __chat_id__: Optional[str] = None,
        __message_id__: Optional[str] = None,
    ) -> dict:
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
            respect_manual_local = bool(getattr(uv, "respect_manual_local", self.valves.RESPECT_MANUAL_LOCAL_SELECTION))
            user_cloud_pref = str(getattr(uv, "preferred_cloud_model", "")).strip()
        else:
            prefer_local_user = False
            respect_manual_local = self.valves.RESPECT_MANUAL_LOCAL_SELECTION
            user_cloud_pref = ""

        # Gewähltes Originalmodell aus dem Request ermitteln
        original_model = body.get("model", "")
        is_selected_local = bool(
            original_model and (
                any(original_model.startswith(p) for p in self.valves.LOCAL_MODEL_PREFIXES)
                or "LMStudio" in original_model
                or original_model in (
                    self.valves.MODEL_LOCAL_CODING,
                    self.valves.MODEL_LOCAL_REASONING,
                    self.valves.MODEL_LOCAL_WRITING,
                    self.valves.MODEL_LOCAL_UNCENSORED,
                )
            )
        )

        # Effektiv konfigurierte Cloud-Zielmodelle pro Fall
        effective_cloud_heavy = user_cloud_pref or self.valves.MODEL_CLOUD_HEAVY
        effective_cloud_opus = user_cloud_pref or self.valves.MODEL_CLOUD_OPUS
        effective_cloud_writing = user_cloud_pref or self.valves.MODEL_CLOUD_WRITING
        effective_cloud_fast = user_cloud_pref or self.valves.MODEL_CLOUD_FAST
        effective_cloud_gpt = user_cloud_pref or self.valves.MODEL_CLOUD_GPT

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

        # Kontextgröße realistisch abschätzen (inkl. Messages, System-Prompt und Tool-Definitionen/Schemas)
        total_prompt_chars = sum(len(str(m.get("content", "") or "")) for m in body.get("messages", []))
        if "tools" in body and body["tools"]:
            try:
                total_prompt_chars += len(json.dumps(body["tools"]))
            except Exception:
                total_prompt_chars += len(str(body["tools"]))
        if "system" in body and body["system"]:
            total_prompt_chars += len(str(body["system"]))
        estimated_context_tokens = total_prompt_chars // 4
        exceeds_local_context = estimated_context_tokens > self.valves.MAX_LOCAL_CONTEXT_TOKENS

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
                    selected_model = effective_cloud_heavy
                    applied_profile = "cloud_heavy"
                    routing_reason = f"Manueller Override: Cloud Coder gewählt -> {selected_model}"
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
                    selected_model = effective_cloud_opus
                    applied_profile = "cloud_opus"
                    routing_reason = f"Manueller Override: #opus gewählt -> {selected_model}"
                else:
                    selected_model = self.valves.MODEL_LOCAL_REASONING
                    applied_profile = "reasoning"
                    routing_reason = f"#opus angefordert, aber wegen {privacy_reason} auf DeepSeek-R1 (WS) umgeleitet"
            elif manual_profile == "cloud_gpt":
                if not force_local_privacy:
                    selected_model = effective_cloud_gpt
                    applied_profile = "cloud_gpt"
                    routing_reason = f"Manueller Override: #gpt / OpenAI gewählt -> {selected_model}"
                else:
                    selected_model = self.valves.MODEL_LOCAL_CODING if intent == "coding" else self.valves.MODEL_LOCAL_REASONING
                    applied_profile = "coding" if intent == "coding" else "reasoning"
                    routing_reason = f"#gpt angefordert, aber wegen {privacy_reason} auf Workstation umgeleitet"
            elif manual_profile in ("cloud_heavy", "cloud_fast"):
                if not force_local_privacy:
                    selected_model = effective_cloud_heavy if manual_profile == "cloud_heavy" else effective_cloud_fast
                    applied_profile = manual_profile
                    routing_reason = f"Manueller Override: {manual_profile} gewählt -> {selected_model}"
                else:
                    selected_model = self.valves.MODEL_LOCAL_CODING if intent == "coding" else self.valves.MODEL_LOCAL_REASONING
                    applied_profile = "coding" if intent == "coding" else "reasoning"
                    routing_reason = f"Cloud angefordert, aber wegen {privacy_reason} auf Workstation umgeleitet"
            elif manual_profile == "direct":
                if force_local_privacy and not is_selected_local:
                    selected_model = self.valves.MODEL_LOCAL_CODING if intent == "coding" else self.valves.MODEL_LOCAL_WRITING
                    applied_profile = "coding" if intent == "coding" else "writing"
                    routing_reason = f"#direct gewählt, aber wegen {privacy_reason} sicherheitshalber auf Workstation umgeleitet"
                else:
                    selected_model = original_model or self.valves.MODEL_LOCAL_WRITING
                    applied_profile = self._profile_for_model(selected_model, intent)
                    routing_reason = f"Manueller Override: #direct Tag -> Gewähltes Modell '{selected_model}' 1:1 beibehalten"

        # A2: Respektiere explizit gewählte interne Modelle (Option 4)
        elif respect_manual_local and is_selected_local:
            selected_model = original_model
            applied_profile = self._profile_for_model(selected_model, intent)
            routing_reason = f"Interne Modellauswahl respektiert: '{selected_model}' (Lokale Workstation)"

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
            # Oder wenn der Chat-Kontext das lokale Kontextfenster übersteigt (z. B. OpenCode Agent)
            elif (intent == "coding" and (is_complex or (exceeds_local_context and not force_local_privacy))) or (forced_location == "cloud" and intent == "coding"):
                selected_model = effective_cloud_heavy
                applied_profile = "cloud_heavy"
                if exceeds_local_context and not is_complex:
                    routing_reason = f"Coding-Agent / Großer Kontext (~{estimated_context_tokens} Tokens > Limit {self.valves.MAX_LOCAL_CONTEXT_TOKENS}) -> {selected_model} (Cloud)"
                else:
                    routing_reason = f"High-End Coding & Architektur -> {selected_model} (Cloud)"

            # Fall 5: Standard Coding & Skripte -> Lokaler Coder (schnell, gratis)
            elif intent == "coding":
                if exceeds_local_context and not force_local_privacy:
                    selected_model = effective_cloud_heavy
                    applied_profile = "cloud_heavy"
                    routing_reason = f"Coding-Kontext übersteigt lokales Limit (~{estimated_context_tokens} Tokens) -> {selected_model} (Cloud)"
                else:
                    selected_model = self.valves.MODEL_LOCAL_CODING
                    applied_profile = "coding"
                    routing_reason = f"Standard Coding & Skripte -> {self.valves.MODEL_LOCAL_CODING} auf Workstation"

            # Fall 6: Mathematische Herleitungen & Logik
            elif intent == "reasoning":
                if forced_location == "cloud":
                    selected_model = effective_cloud_opus
                    applied_profile = "cloud_opus"
                    routing_reason = f"Deep Reasoning (Cloud forciert) -> {selected_model}"
                else:
                    selected_model = self.valves.MODEL_LOCAL_REASONING
                    applied_profile = "reasoning"
                    routing_reason = f"Deep Reasoning & Logik -> {self.valves.MODEL_LOCAL_REASONING} auf Workstation"

            # Fall 7: Sehr lange / hochkomplexe Textanalyse (ohne kritische PII-Sperre)
            elif is_complex and not force_local_privacy:
                selected_model = effective_cloud_writing
                applied_profile = "cloud_heavy"
                routing_reason = f"Hohe Textkomplexität (maskiert) -> {selected_model} (Cloud)"

            # Fall 8: Standard Writing, Lektorat, Chat, Routine
            else:
                if exceeds_local_context and not force_local_privacy:
                    selected_model = effective_cloud_writing
                    applied_profile = "cloud_heavy"
                    routing_reason = f"Kontext übersteigt lokales Limit (~{estimated_context_tokens} Tokens) -> {selected_model} (Cloud)"
                else:
                    selected_model = self.valves.MODEL_LOCAL_WRITING
                    applied_profile = "writing"
                    routing_reason = f"Writing, Chat & Routine -> {self.valves.MODEL_LOCAL_WRITING} auf Workstation (0 Cloud-Credits)"
        # 6b. Auto-Fallback für bekannte defekte oder inaktive Modell-IDs
        if selected_model in KNOWN_INACTIVE_MODELS:
            fallback = KNOWN_INACTIVE_MODELS[selected_model]
            log.warning(f"[Model Router] Defektes/inaktives Modell '{selected_model}' abgefangen -> Fallback auf '{fallback}'")
            routing_reason += f" (Auto-Fallback von {selected_model})"
            selected_model = fallback

        # 7. Modell im Request überschreiben
        original_model = body.get("model", "")
        body["model"] = selected_model

        if "metadata" not in body:
            body["metadata"] = {}

        # Nur für interaktive Web-UI Chats (chat_id vorhanden) das custom selected_model_id Event auslösen.
        # Externe API-Clients (OpenCode / Vercel AI SDK / standard OpenAI SDK) erwarten ein striktes
        # OpenAI SSE Chunk Schema (choices: [...]). Ein data: {"selected_model_id": ...} führt dort zu Validierungsfehlern.
        is_interactive_chat = bool(
            __chat_id__
            or (isinstance(__metadata__, dict) and __metadata__.get("chat_id"))
            or body.get("chat_id")
        )
        if is_interactive_chat:
            body["metadata"]["selected_model_id"] = selected_model

        # 8. Hyperparameter-Injektion (Temperature & Top-P)
        profile_data = PROFILES.get(applied_profile, {})
        if self.valves.APPLY_OPTIMAL_SAMPLING_PARAMS and profile_data:
            body["temperature"] = profile_data["temperature"]
            body["top_p"] = profile_data["top_p"]

        # 9. Audit- & Debug-Metadaten für die Open-WebUI Sprechblasen-Info
        decision = {
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
        body["metadata"]["router_decision"] = decision
        if isinstance(__metadata__, dict):
            __metadata__["router_decision"] = decision

        # Ausfallsicherung über In-Memory Store
        cid = __chat_id__ or body.get("chat_id") or (isinstance(__metadata__, dict) and __metadata__.get("chat_id"))
        mid = __message_id__ or body.get("id") or (isinstance(__metadata__, dict) and __metadata__.get("message_id"))
        for k in [mid, cid, f"{cid}:{mid}"]:
            if k:
                _GLOBAL_ROUTER_STORE[str(k)] = decision
        if len(_GLOBAL_ROUTER_STORE) > 200:
            oldest = next(iter(_GLOBAL_ROUTER_STORE))
            _GLOBAL_ROUTER_STORE.pop(oldest, None)

        # Separater pii_audit Key für direkte Sichtbarkeit in der Info-Box
        if pii_elements:
            audit_payload = {
                "anzahl_behandelt": len(pii_elements),
                "status": "Erfolgreich maskiert & zur Re-Hydrierung vorgemerkt",
                "elemente": pii_elements,
            }
            body["metadata"]["pii_audit"] = audit_payload
            if isinstance(__metadata__, dict):
                __metadata__["pii_audit"] = audit_payload

        # Optionaler Status-Event an UI emittieren
        if __event_emitter__:
            try:
                import asyncio
                import inspect
                target_short = "Workstation (LM Studio)" if "LMStudio" in selected_model else "Cloud Provider"
                payload = {
                    "type": "status",
                    "data": {
                        "description": f"🛡️ Hybrid Gateway: {routing_reason} ➔ {selected_model} ({target_short})",
                        "done": True,
                    }
                }
                res = __event_emitter__(payload)
                if inspect.isawaitable(res):
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            loop.create_task(res)
                        else:
                            loop.run_until_complete(res)
                    except Exception:
                        pass
            except Exception as emitter_err:
                log.debug(f"[Model Router] Event emitter notice: {emitter_err}")

        log.info(f"[Model Router] '{original_model}' -> '{selected_model}' [{routing_reason}] (T={body.get('temperature')}, P={body.get('top_p')})")
        return body

    def outlet(
        self,
        body: dict,
        __metadata__: Optional[dict] = None,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable] = None,
        __chat_id__: Optional[str] = None,
        __message_id__: Optional[str] = None,
    ) -> dict:
        """
        Interzeptiert die Modell-Antwort vor der Anzeige in der UI:
        - Liest die Routing-Entscheidung und PII-Metadaten aus
        - Fügt bei aktiviertem SHOW_ROUTING_BANNER eine transparente Callout-Box
          am Anfang der Antwort ein, damit der/die Nutzer:in genau sieht, welches
          Modell geantwortet hat und warum.
        """
        if not isinstance(body, dict):
            return body

        if not self.valves.SHOW_ROUTING_BANNER:
            return body

        decision = None
        if isinstance(__metadata__, dict):
            decision = __metadata__.get("router_decision")

        if not decision and isinstance(body.get("metadata"), dict):
            decision = body["metadata"].get("router_decision")

        if not decision:
            cid = __chat_id__ or body.get("chat_id") or (isinstance(__metadata__, dict) and __metadata__.get("chat_id"))
            mid = __message_id__ or body.get("id") or (isinstance(__metadata__, dict) and __metadata__.get("message_id"))
            for k in [mid, cid, f"{cid}:{mid}"]:
                if k and str(k) in _GLOBAL_ROUTER_STORE:
                    decision = _GLOBAL_ROUTER_STORE[str(k)]
                    break

        if not decision:
            return body

        msgs = body.get("messages") or []
        target_idx = -1
        for i in range(len(msgs) - 1, -1, -1):
            if isinstance(msgs[i], dict) and msgs[i].get("role") == "assistant":
                target_idx = i
                break

        if target_idx == -1:
            return body

        routed_to = decision.get("routed_to", "Unbekannt")
        original_model = decision.get("original_model", "")
        reason = decision.get("reason", "")
        pii_count = decision.get("pii_detected", 0)
        target_node = decision.get("target_node", "")
        is_local = "LMStudio" in routed_to or "Workstation" in target_node

        if self.valves.ROUTING_BANNER_COLLAPSIBLE:
            node_label = "Lokale GPU Workstation (0 Credits)" if is_local else "Cloud Provider (OpenRouter)"
            banner = (
                f"<details>\n"
                f"<summary>🛡️ Routing: {node_label} • {routed_to} • 🔒 {pii_count} PII</summary>\n\n"
                f"- **Ausgeführtes Modell:** `{routed_to}`"
                f"{f' *(ursprünglich gewählt: `{original_model}`)*' if original_model and original_model != routed_to else ''}\n"
                f"- **Ausführungsort:** {'Lokale GPU Workstation (LM Studio via LAN/Tailscale)' if is_local else 'Cloud Provider (OpenRouter)'}\n"
                f"- **Routing-Grund:** {reason}\n"
                f"- **Datenschutz:** {pii_count} PII-Elemente im Prompt geschwärzt & in der Antwort wiederhergestellt\n"
                f"</details>"
            )
        else:
            if is_local:
                banner = (
                    f"> 🛡️ **Hybrid Gateway Routing:** **Lokale GPU Workstation** (`{routed_to}`) • **0 Cloud-Credits**\n"
                    f"> 🔒 **Privacy Gate:** {pii_count} PII-Elemente geschwärzt & wiederhergestellt • *Grund: {reason}*"
                )
            else:
                banner = (
                    f"> ☁️ **Hybrid Gateway Routing:** **Cloud Provider** (`{routed_to}`)\n"
                    f"> 🛡️ **Privacy Gate:** {f'{pii_count} unkritische PII geschwärzt' if pii_count else 'Keine PII erkannt'} • *Grund: {reason}*"
                )

        current_content = msgs[target_idx].get("content") or ""
        if (
            not current_content.startswith("> 🛡️ **Hybrid Gateway Routing")
            and not current_content.startswith("> ☁️ **Hybrid Gateway Routing")
            and not current_content.startswith("<details>\n<summary>🛡️ Routing:")
            and not current_content.startswith("<details>\n<summary>🛡️ <b>Routing:")
        ):
            msgs[target_idx]["content"] = f"{banner}\n\n{current_content}"

        # Synchronize structured output if present (Open WebUI frontend prefers `output` over `content`)
        msg_dict = msgs[target_idx]
        if isinstance(msg_dict.get("output"), list) and msg_dict["output"]:
            for item in msg_dict["output"]:
                if isinstance(item, dict) and item.get("type") == "message":
                    parts = item.get("content")
                    if isinstance(parts, list):
                        for part in parts:
                            if isinstance(part, dict) and part.get("type") == "output_text":
                                ptxt = part.get("text", "")
                                if (
                                    not ptxt.startswith("> 🛡️ **Hybrid Gateway Routing")
                                    and not ptxt.startswith("> ☁️ **Hybrid Gateway Routing")
                                    and not ptxt.startswith("<details>\n<summary>🛡️ Routing:")
                                    and not ptxt.startswith("<details>\n<summary>🛡️ <b>Routing:")
                                ):
                                    part["text"] = f"{banner}\n\n{ptxt}"
                                break

        return body

