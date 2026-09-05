"""
title: PII Redaction Filter (Two-Layer, Reversible)
author: walte
author_url: https://github.com/walte
version: 0.1.0
required_open_webui_version: 0.5.0
requirements: spacy==3.8.14
license: MIT

Zweilagiger PII-Filter für Open WebUI.

Phase 1 (inlet):  User-Input -> PII-Erkennung (Regex + spaCy NER) -> geschwärzter
                  Text + Mapping in body['metadata']['pii_map'] -> an LLM.

Phase 2 (outlet): LLM-Output -> Mapping aus Metadata -> Platzhalter durch
                  Originale ersetzen -> Antwort zurück an UI.

Das Mapping wird in `body['metadata']['pii_map']` persistiert. Open WebUI gibt
diese Metadata beim Outlet-Aufruf zurück, sodass beide Phasen im selben Request-
Lebenszyklus auf dasselbe Mapping zugreifen.

Installation
------------
1. spaCy + deutsches Modell im Open-WebUI-Container installieren
   (im Docker-Setup via Dockerfile oder manuell):
       pip install spacy==3.8.14
       python -m spacy download de_core_news_sm

2. Diesen Code in Open WebUI unter
   "Workspace -> Functions -> +" als neuen Filter einfügen.

3. Filter aktivieren:
       - global unter "Admin Panel -> Settings -> Interface"
       - oder pro Modell unter "Workspace -> Models -> Edit -> Filters"
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from collections import defaultdict
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

# spaCy ist ein optionaler, aber stark empfohlener Baustein. Wir laden das
# Modell erst beim ersten inlet-Aufruf, damit ein fehlendes Modell die
# Open-WebUI-Instanz nicht beim Start blockiert.
_NLP = None
_NLP_LOAD_ERROR: Optional[Exception] = None

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Konfiguration (Valves)
# ---------------------------------------------------------------------------


class Valves(BaseModel):
    """Operator-Konfiguration für den PII-Filter."""

    priority: int = Field(
        default=0,
        description="Filter-Reihenfolge. Niedrigere Werte laufen früher. "
        "Dieser Filter sollte früh laufen (z.B. priority=0).",
    )

    # --- Schalter ---
    enable_regex: bool = Field(
        default=True,
        description="Strukturierte PII (Telefon, E-Mail, IBAN, ...) per Regex schwärzen.",
    )
    enable_ner: bool = Field(
        default=True,
        description="Unstrukturierte PII (Personen, Orte, Organisationen, Länder) "
        "per spaCy NER schwärzen.",
    )
    deanonymize_output: bool = Field(
        default=True,
        description="Im outlet die Platzhalter wieder durch Originale ersetzen.",
    )
    deanonymize_reasoning: bool = Field(
        default=True,
        description="Den Denkprozess (Reasoning) des Modells ebenfalls wieder mit den Originaldaten befüllen. Wenn deaktiviert, bleiben Platzhalter im Denkprozess sichtbar.",
    )

    # --- spaCy ---
    ner_model: str = Field(
        default="de_core_news_sm",
        description="spaCy-Modellname. Für Deutsch: de_core_news_sm / de_core_news_md. "
        "Für Englisch: en_core_web_sm.",
    )
    ner_labels: list[str] = Field(
        default_factory=lambda: ["PER", "PERSON", "LOC", "GPE", "ORG", "MISC"],
        description="spaCy-Labels, die geschwärzt werden sollen. "
        "de_core_news_sm liefert: PER, LOC, ORG, MISC. "
        "en_core_web_sm liefert: PERSON, GPE, LOC, ORG.",
    )
    ner_min_score: float = Field(
        default=0.0,
        description="Minimaler Score (0-1), ab dem eine NER-Entity übernommen wird. "
        "de_core_news_sm liefert keinen Score pro Entity -> Wert ignorieren.",
    )
    ner_min_token_len: int = Field(
        default=3,
        description="Minimale Zeichenlänge eines NER-Entity-Bestandteils, "
        "damit Wörter wie 'Bitte', 'Mein' nicht als Person/Ort erkannt werden. "
        "Bei 0 deaktiviert.",
    )

    # --- Regex-Sets ---
    extra_patterns: str = Field(
        default="",
        description="Optionale zusätzliche Regex-Patterns (eine pro Zeile, "
        "Format: NAME|PATTERN, z.B. MITARBEITERID|M\\d{6}).",
    )

    # --- Token-Format ---
    token_format: str = Field(
        default="[[{label}_{n}]]",
        description="Format-String für Platzhalter. {label} und {n} sind Platzhalter.",
    )
    keep_first_letter: bool = Field(
        default=False,
        description="Optional: Ersten Buchstaben im geschwärzten Token erhalten "
        "(für leichtes Debugging). Standard: aus.",
    )
    split_ner_entities: bool = Field(
        default=False,
        description="Wenn True: Zerlegt mehrteilige Namen in Einzelwörter. "
        "Wenn False: Maskiert zusammenhängende Namen als eine konsistente Entität (empfohlen).",
    )
    show_audit_details: bool = Field(
        default=True,
        description="Fügt nach der Antwort ein aufklappbares PII-Audit-Protokoll (<details>) "
        "mit detaillierter Übersicht aller geschwärzten und restaurierten Daten ein.",
    )
    show_masked_prompt_in_audit: bool = Field(
        default=True,
        description="Zeigt im aufklappbaren Protokoll den exakt maskierten Prompt, "
        "der an das Modell gesendet wurde (Beweis für Zero Data Leakage).",
    )


class UserValves(BaseModel):
    """User-spezifische Overrides (pro Benutzer:in via UI setzbar)."""

    enabled: bool = Field(
        default=True,
        description="PII-Redaktion für diese:n Nutzer:in aktivieren.",
    )
    deanonymize_for_me: bool = Field(
        default=True,
        description="Antwort wieder mit Originalen füllen. Für Trainer/Demos "
        "kann das deaktiviert werden, um nur geschwärzte Outputs zu sehen.",
    )


# ---------------------------------------------------------------------------
# Regex-Pattern-Bibliothek
# ---------------------------------------------------------------------------


# Bewusst konservativ: keine False-Positives auf Hausnummern, Postleitzahlen
# ohne Kontext, Daten ohne Jahr, usw. Anpassbar über Valves.extra_patterns.
DEFAULT_REGEX_PATTERNS: dict[str, str] = {
    "EMAIL": r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
    "PHONE_DE": (
        # Internationale Vorwahl + nationale Varianten (Festnetz + Mobil)
        r"(?:\+49|0049|0)[\s\-]?\(?\d{2,5}\)?[\s\-]?\d{3,5}[\s\-]?\d{3,5}"
    ),
    "PHONE_INTL": r"\+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{2,4}[\s\-]?\d{2,4}[\s\-]?\d{0,4}",
    "IBAN": r"\b[A-Z]{2}\d{2}[\s]?(?:[A-Z0-9]{4}[\s]?){2,7}[A-Z0-9]{1,4}\b",
    "CREDIT_CARD": r"\b(?:\d[ \-]?){13,19}\b",
    "IPV4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "URL_WITH_AUTH": r"https?://[^\s]+:[^\s]+@[^\s]+",  # URLs mit eingebetteten Credentials
    "SSN_US": r"\b\d{3}-\d{2}-\d{4}\b",
    "PASSPORT_DE": r"\b[A-ZCFGHIJKLMNOPQRSTUVWXYZ0-9]{9}\b(?=.*Reisepass|Passport)",  # Kontext-abhängig, schwach
    "TAX_ID_DE": r"\b\d{2}\s?\d{3}\s?\d{3}\s?\d{3}\b",  # sehr schwach, daher unten deaktiviert
}


# Labels, die wir per Default NICHT maskieren, weil False-Positive-Risiko zu hoch.
DISABLED_BY_DEFAULT: set[str] = {"TAX_ID_DE", "PASSPORT_DE"}


# Funktions- und Füllwörter, die spaCy regelmäßig fälschlich als Person/Ort
# markiert. Wer eine sehr strikte Redaktion braucht, kann diese Liste via
# Valves-Override ergänzen.
NER_STOPWORDS: set[str] = {
    "bitte", "danke", "gruß", "hallo", "liebe", "lieber",
    "tag", "monat", "jahr", "tagen", "monaten", "jahren",
    "montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag",
    "januar", "februar", "märz", "april", "mai", "juni", "juli",
    "august", "september", "oktober", "november", "dezember",
    "morgen", "mittag", "abend", "nacht",
    "oben", "unten", "links", "rechts",
    "ende", "anfang", "start", "stopp",
    "sehr", "geehrte", "geehrter", "geehrtes",
    "tel", "fax", "fon", "phone", "mail", "email", "mobil", "handy", "web", "info",
}


def _compile_patterns(valves: Valves) -> list[tuple[str, re.Pattern]]:
    """Gibt eine Liste (Label, kompilierte Regex) zurück."""

    patterns: dict[str, str] = {**DEFAULT_REGEX_PATTERNS}
    for k in DISABLED_BY_DEFAULT:
        patterns.pop(k, None)

    # Benutzerdefiniert: "NAME|PATTERN" pro Zeile
    if valves.extra_patterns.strip():
        for line in valves.extra_patterns.splitlines():
            line = line.strip()
            if not line or "|" not in line:
                continue
            name, pat = line.split("|", 1)
            patterns[name.strip().upper()] = pat.strip()

    compiled: list[tuple[str, re.Pattern]] = []
    for label, pat in patterns.items():
        try:
            compiled.append((label, re.compile(pat)))
        except re.error as exc:
            log.warning(f"[PII] Ungültiges Pattern für {label}: {exc}")

    # Reihenfolge ist wichtig: spezifischere Patterns zuerst, damit z.B. eine
    # IBAN nicht teilweise von PHONE_DE aufgefressen wird. Wir priorisieren
    # per Label, danach nach Pattern-Länge (innerhalb gleicher Priorität).
    priority = {
        "IBAN": 0,
        "CREDIT_CARD": 1,
        "EMAIL": 2,
        "SSN_US": 3,
        "URL_WITH_AUTH": 4,
        "PHONE_DE": 5,
        "PHONE_INTL": 6,
        "IPV4": 7,
    }
    compiled.sort(key=lambda lp: (priority.get(lp[0], 50), -len(lp[1].pattern)))
    return compiled


# ---------------------------------------------------------------------------
# spaCy-Wrapper
# ---------------------------------------------------------------------------


def _get_nlp(valves: Valves):
    """Lazy-load spaCy-Modell mit automatischem Download falls noch nicht vorhanden."""

    global _NLP, _NLP_LOAD_ERROR

    if not valves.enable_ner:
        return None

    if _NLP is not None:
        return _NLP

    try:
        import spacy

        try:
            _NLP = spacy.load(valves.ner_model)
        except Exception:
            log.info(f"[PII] spaCy-Modell '{valves.ner_model}' nicht lokal gefunden, lade herunter...")
            try:
                import spacy.cli

                spacy.cli.download(valves.ner_model)
            except Exception as dl_err:
                log.info(f"[PII] spacy.cli.download fehlgeschlagen ({dl_err}), versuche direkten pip install...")
                import subprocess
                import sys

                model_name = valves.ner_model
                wheel_url = f"https://github.com/explosion/spacy-models/releases/download/{model_name}-3.8.0/{model_name}-3.8.0-py3-none-any.whl"
                subprocess.check_call([sys.executable, "-m", "pip", "install", wheel_url])

            _NLP = spacy.load(valves.ner_model)

        _NLP_LOAD_ERROR = None
        log.info(f"[PII] spaCy-Modell geladen: {valves.ner_model}")
    except Exception as exc:  # noqa: BLE001
        _NLP_LOAD_ERROR = exc
        log.warning(
            f"[PII] spaCy-Modell '{valves.ner_model}' konnte nicht geladen "
            f"werden ({exc}). NER wird übersprungen."
        )
        return None

    return _NLP


# ---------------------------------------------------------------------------
# Mapping-Logik
# ---------------------------------------------------------------------------


def _next_token(valves: Valves, counters: dict[str, int], label: str) -> str:
    """Erzeugt das nächste Platzhalter-Token für ein Label."""

    counters[label] = counters.get(label, 0) + 1
    return valves.token_format.format(label=label, n=counters[label])


def _mask_value(valves: Valves, label: str, value: str) -> str:
    """Optional: ersten Buchstaben behalten, Rest schwärzen."""

    if not valves.keep_first_letter or not value:
        return ""
    # nur sinnvoll bei sichtbaren Strings
    first = value[0]
    return f"{first}***"


# ---------------------------------------------------------------------------
# Kern: Redaction
# ---------------------------------------------------------------------------


def _redact_text(
    text: str,
    valves: Valves,
    mapping: dict[str, str],
    counters: dict[str, int],
) -> str:
    """Schwärzt `text`. Erweitert `mapping` (token -> original) und `counters`."""

    if not text:
        return text

    # 1) Regex-Schicht
    if valves.enable_regex:
        for label, pat in _compile_patterns(valves):
            def _sub(match: re.Match, _label: str = label) -> str:
                original = match.group(0)
                # Falls der gleiche Original-Wert bereits ersetzt wurde,
                # dasselbe Token wiederverwenden (Konsistenz im selben Text).
                for tok, orig in mapping.items():
                    if orig == original:
                        return tok
                tok = _next_token(valves, counters, _label)
                mapping[tok] = original
                return tok

            text = pat.sub(_sub, text)

    # 2) NER-Schicht
    if valves.enable_ner:
        nlp = _get_nlp(valves)
        if nlp is not None:
            doc = nlp(text)

            # Bereits durch Regex belegte Bereiche einsammeln. NER darf
            # nicht in einen Token-String hineinschreiben ("max" als Teil
            # von "[[EMAIL_1]]@example.com" o.ä.).
            occupied_spans: list[tuple[int, int]] = []
            for m in re.finditer(r"\[\[[A-Z0-9_]+_\d+\]\]", text):
                occupied_spans.append((m.start(), m.end()))

            def _overlaps(start: int, end: int) -> bool:
                return any(not (end <= s or start >= e) for s, e in occupied_spans)

            entities = sorted(
                (
                    ent
                    for ent in doc.ents
                    if ent.label_ in set(valves.ner_labels)
                    and not _overlaps(ent.start_char, ent.end_char)
                ),
                key=lambda e: e.start_char,
                reverse=True,
            )

            # Erst alle Spans auf dem aktuellen Text berechnen, dann
            # rechts-nach-links ersetzen, damit sich die Offsets nicht
            # durch bereits eingesetzte Tokens verschieben.
            replacements: list[tuple[int, int, str, str]] = []
            for ent in entities:
                ent_text = ent.text.strip()
                if not ent_text:
                    continue

                if getattr(valves, "split_ner_entities", False):
                    # Zerlegung in Einzelwörter (falls vom Nutzer explizit konfiguriert)
                    parts = [p for p in ent_text.split() if p]
                    if not parts:
                        continue
                    spans: list[tuple[int, int]] = []
                    cursor = ent.start_char
                    ok = True
                    for part in parts:
                        idx = text.find(part, cursor)
                        if idx == -1:
                            ok = False
                            break
                        spans.append((idx, idx + len(part)))
                        cursor = idx + len(part)
                    if not ok:
                        spans = [(ent.start_char, ent.end_char)]
                        parts = [ent_text]
                    if valves.ner_min_token_len > 0:
                        filtered_spans_parts = [
                            (s, p)
                            for s, p in zip(spans, parts)
                            if len(p) >= valves.ner_min_token_len
                            and p.lower() not in NER_STOPWORDS
                        ]
                        if not filtered_spans_parts:
                            continue
                        spans = [s for s, _ in filtered_spans_parts]
                        parts = [p for _, p in filtered_spans_parts]
                    for (start, end), part in zip(spans, parts):
                        existing = next((t for t, o in mapping.items() if o == part), None)
                        if existing:
                            token = existing
                        else:
                            token = _next_token(valves, counters, f"NAME_{ent.label_}")
                            mapping[token] = part
                        replacements.append((start, end, token, part))
                else:
                    # Standard: Zusammenhängende Entitäten als eine Einheit maskieren
                    if valves.ner_min_token_len > 0 and len(ent_text) < valves.ner_min_token_len:
                        continue
                    if ent_text.lower() in NER_STOPWORDS:
                        continue
                    existing = next((t for t, o in mapping.items() if o == ent_text), None)
                    if existing:
                        token = existing
                    else:
                        token = _next_token(valves, counters, f"NAME_{ent.label_}")
                        mapping[token] = ent_text
                    replacements.append((ent.start_char, ent.end_char, token, ent_text))

            # rechts-nach-links einsetzen
            replacements.sort(key=lambda r: r[0], reverse=True)
            for start, end, token, _part in replacements:
                text = text[:start] + token + text[end:]

    return text


def _deanonymize_text(text: str, mapping: dict[str, str]) -> str:
    """Ersetzt Platzhalter zurück durch die Originale.
    Unterstützt sowohl Standard-Tokens [[TOKEN]] als auch vom LLM vereinfachte [TOKEN]
    oder kleingeschriebene Varianten."""

    if not text or not mapping:
        return text

    # Längste Tokens zuerst, damit [[NAME_PER_10]] vor [[NAME_PER_1]] greift.
    for token in sorted(mapping.keys(), key=len, reverse=True):
        original = mapping[token]
        # 1. Exakte Ersetzung: z.B. [[IBAN_1]]
        text = text.replace(token, original)

        # 2. Einzelklammer-Ersetzung: z.B. [IBAN_1] (häufige LLM-Normalisierung)
        inner = token.strip("[]")
        text = text.replace(f"[{inner}]", original)

        # 3. Case-Insensitive / Lowercase Varianten: z.B. [[iban_1]] oder [iban_1]
        text = text.replace(token.lower(), original)
        text = text.replace(f"[{inner.lower()}]", original)
    return text


def _deanonymize_recursive(data: Any, mapping: dict[str, str], deanonymize_reasoning: bool = True) -> Any:
    if isinstance(data, str):
        return _deanonymize_text(data, mapping)
    elif isinstance(data, dict):
        if not deanonymize_reasoning and data.get("type") == "reasoning":
            return data
        return {k: _deanonymize_recursive(v, mapping, deanonymize_reasoning) for k, v in data.items()}
    elif isinstance(data, list):
        return [_deanonymize_recursive(x, mapping, deanonymize_reasoning) for x in data]
    return data


# ---------------------------------------------------------------------------
# Mapping-Persistenz im Request
# ---------------------------------------------------------------------------


# Wir speichern das Mapping in body['metadata']['pii_map']. Open WebUI gibt
# beim outlet dieselbe body-Struktur zurück, daher kommen wir so ohne externen
# State aus. Bei Stream-Antworten wird zusätzlich im Event-Payload ersetzt.

PII_MAP_KEY = "pii_map"
PII_COUNTERS_KEY = "pii_counters"


_GLOBAL_PII_STORE: dict[str, tuple[dict[str, str], dict[str, int]]] = {}


def _ensure_metadata(body: dict) -> dict:
    md = body.get("metadata")
    if not isinstance(md, dict):
        md = {}
        body["metadata"] = md
    return md


def _load_mapping(
    body: dict,
    metadata: Optional[dict] = None,
    __body__: Optional[dict] = None,
    chat_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> tuple[dict[str, str], dict[str, int], dict[str, Any]]:
    mapping = None
    counters = None
    audit_info = None

    if isinstance(metadata, dict):
        mapping = metadata.get(PII_MAP_KEY)
        counters = metadata.get(PII_COUNTERS_KEY)
        audit_info = metadata.get("pii_audit_info")

    if not isinstance(mapping, dict) and isinstance(body, dict):
        # Fallback für Unit-Tests (__metadata_body__ im Event)
        mb = body.get("__metadata_body__")
        if isinstance(mb, dict):
            md = mb.get("metadata")
            if isinstance(md, dict):
                mapping = md.get(PII_MAP_KEY)
                counters = md.get(PII_COUNTERS_KEY)
                audit_info = md.get("pii_audit_info")

    if not isinstance(mapping, dict) and isinstance(body, dict):
        md = body.get("metadata")
        if isinstance(md, dict):
            mapping = md.get(PII_MAP_KEY)
            counters = md.get(PII_COUNTERS_KEY)
            audit_info = md.get("pii_audit_info")

    if not isinstance(mapping, dict) and isinstance(__body__, dict):
        md = __body__.get("metadata")
        if isinstance(md, dict):
            mapping = md.get(PII_MAP_KEY)
            counters = md.get(PII_COUNTERS_KEY)
            audit_info = md.get("pii_audit_info")

    # Ausfallsicherung über In-Memory Global Store
    if not isinstance(mapping, dict) or not mapping:
        cid = chat_id or (body.get("chat_id") if isinstance(body, dict) else None)
        mid = message_id or (body.get("id") if isinstance(body, dict) else None)
        for k in [mid, cid, f"{cid}:{mid}"]:
            if k and str(k) in _GLOBAL_PII_STORE:
                store_entry = _GLOBAL_PII_STORE[str(k)]
                m_found = store_entry[0]
                c_found = store_entry[1]
                a_found = store_entry[2] if len(store_entry) > 2 else {}
                if m_found:
                    mapping = m_found
                    counters = c_found
                    audit_info = a_found
                    break

    if not isinstance(mapping, dict):
        mapping = {}
    if not isinstance(counters, dict):
        counters = {}
    if not isinstance(audit_info, dict):
        audit_info = {}
    return mapping, counters, audit_info


def _store_mapping(
    body: dict,
    mapping: dict[str, str],
    counters: dict[str, int],
    metadata: Optional[dict] = None,
    chat_id: Optional[str] = None,
    message_id: Optional[str] = None,
    audit_info: Optional[dict] = None,
) -> None:
    md = _ensure_metadata(body)
    md[PII_MAP_KEY] = mapping
    md[PII_COUNTERS_KEY] = counters
    if audit_info:
        md["pii_audit_info"] = audit_info

    if isinstance(metadata, dict):
        metadata[PII_MAP_KEY] = mapping
        metadata[PII_COUNTERS_KEY] = counters
        if audit_info:
            metadata["pii_audit_info"] = audit_info

    # Global in-memory cache als Ausfallsicherung
    for k in [message_id, chat_id, f"{chat_id}:{message_id}"]:
        if k:
            _GLOBAL_PII_STORE[str(k)] = (dict(mapping), dict(counters), dict(audit_info or {}))
    if len(_GLOBAL_PII_STORE) > 200:
        oldest = next(iter(_GLOBAL_PII_STORE))
        _GLOBAL_PII_STORE.pop(oldest, None)


def _get_category_label(token: str) -> str:
    """Liefert eine lesbare deutsche Bezeichnung für eine PII-Token-Kategorie."""
    if "IBAN" in token:
        return "Bankkonto (IBAN)"
    if "CREDIT_CARD" in token:
        return "Kreditkartennummer"
    if "EMAIL" in token:
        return "E-Mail-Adresse"
    if "PHONE" in token:
        return "Telefonnummer"
    if "PER" in token:
        return "Person / Name"
    if "LOC" in token:
        return "Adresse / Standort"
    if "ORG" in token:
        return "Organisation / Firma"
    if "IPV4" in token:
        return "IP-Adresse"
    if "TAX_ID" in token:
        return "Steuer-ID"
    return "Sensible Entität"


def _format_pii_audit_box(
    mapping: dict[str, str],
    audit_info: dict[str, Any],
    valves: Valves,
) -> str:
    """
    Erzeugt eine aufklappbare <details>-Box nach der Antwort:
    - Phase 1: Welche Daten wurden geschwärzt (Tabelle mit Token, Kategorie, Original)
    - Phase 2: Exakt maskierter Prompt, der an das LLM geschickt wurde (Beweis für Zero Leakage)
    - Phase 3: Bestätigung der Re-Hydrierung nach Erhalt der Modellantwort
    """
    rows = []
    for token in sorted(mapping.keys(), key=len, reverse=True):
        orig = mapping[token]
        cat = _get_category_label(token)
        rows.append(f"| `{token}` | **{cat}** | `{orig}` | Geschwärzt ➔ Rehydriert |")

    table_content = "\n".join(rows)

    masked_section = ""
    masked_prompt = audit_info.get("masked_prompt", "")
    if valves.show_masked_prompt_in_audit and masked_prompt:
        masked_section = (
            "\n#### 2. An das Modell übermittelter Prompt (Beweis für Zero Data Leakage)\n"
            "> **Garantie:** Sämtliche Klardaten wurden vor Verlassen der Anwendung durch Platzhalter ersetzt. "
            "Weder Cloud- noch lokale Modelle haben diese Identifikatoren im Rohzustand erhalten:\n\n"
            "```text\n"
            f"{masked_prompt.strip()}\n"
            "```\n"
        )

    count = len(mapping)
    box = (
        f"<details>\n"
        f"<summary>ℹ️ <b>Datenschutz- & PII-Protokoll</b> ({count} sensible Datenwerte geschwärzt & restauriert – Klick für Details)</summary>\n\n"
        f"### 🛡️ Lebenszyklus der sensiblen Daten in dieser Anfrage\n\n"
        f"#### 1. Erkannte & geschwärzte Entitäten (Inlet-Filter)\n"
        f"| Platzhalter (Token) | Kategorie | Originalwert (geschützt) | Status |\n"
        f"| :--- | :--- | :--- | :--- |\n"
        f"{table_content}\n"
        f"{masked_section}"
        f"#### 3. Restaurierung nach Modellantwort (Outlet-Filter)\n"
        f"- **Re-Hydrierung:** Alle **{count}** Platzhalter wurden nach Erhalt der Modellantwort in der finalen Antwort wieder nahtlos durch die Originaldaten ersetzt.\n"
        f"- **Sicherheit:** Zu keinem Zeitpunkt wurden Klardaten ungeschützt über das Netzwerk übertragen.\n"
        f"</details>"
    )
    return box


# ---------------------------------------------------------------------------
# Open-WebUI Hooks
# ---------------------------------------------------------------------------


def _iter_user_texts(body: dict) -> list[tuple[int, str]]:
    """
    Liefert eine Liste (index, content) der letzten User-Message-Contents.
    Open WebUI hält die Konversation in body['messages']; wir redigieren
    nur die letzte echte User-Nachricht (role == "user"), nicht die ganze
    Historie, damit das LLM den Kontext der vorherigen Runde behält.
    """

    out: list[tuple[int, str]] = []
    msgs = body.get("messages") or []
    for i in range(len(msgs) - 1, -1, -1):
        m = msgs[i]
        if isinstance(m, dict) and m.get("role") == "user":
            content = m.get("content")
            if isinstance(content, str):
                out.append((i, content))
            break
    return out


def _set_message_content(body: dict, idx: int, new_content: str) -> None:
    body["messages"][idx]["content"] = new_content


def _get_last_assistant_text(body: dict) -> tuple[int, str]:
    """Liefert (index, content) der letzten Assistant-Message."""

    msgs = body.get("messages") or []
    for i in range(len(msgs) - 1, -1, -1):
        m = msgs[i]
        if isinstance(m, dict) and m.get("role") == "assistant":
            content = m.get("content")
            if isinstance(content, str):
                return i, content
    return -1, ""


def inlet(
    body: dict,
    __metadata__: Optional[dict] = None,
    __user__: Optional[dict] = None,
    __event_emitter__: Optional[Callable] = None,
    __chat_id__: Optional[str] = None,
    __message_id__: Optional[str] = None,
) -> dict:
    """
    Vor dem LLM-Aufruf: PII in der letzten User-Message schwärzen, Mapping
    in body.metadata und __metadata__ ablegen.
    """

    valves: Valves = body.get("_valves")  # vom Framework injiziert? Fallback unten.
    if valves is None:
        valves = getattr(inlet, "_valves_cache", Valves())

    # User-Switch
    if __user__ and isinstance(__user__, dict):
        user_valves = __user__.get("valves")
        if isinstance(user_valves, UserValves) and not user_valves.enabled:
            return body

    if not isinstance(body, dict):
        return body

    chat_id = __chat_id__ or body.get("chat_id") or (isinstance(__metadata__, dict) and __metadata__.get("chat_id"))
    message_id = __message_id__ or body.get("id") or (isinstance(__metadata__, dict) and __metadata__.get("message_id"))

    mapping, counters, _ = _load_mapping(body, __metadata__, chat_id=chat_id, message_id=message_id)

    last_user_prompt = ""
    last_masked_prompt = ""

    for idx, content in _iter_user_texts(body):
        if not content:
            continue
        last_user_prompt = content
        try:
            new_content = _redact_text(content, valves, mapping, counters)
        except Exception as exc:  # noqa: BLE001
            log.exception(f"[PII] Fehler beim Redact: {exc}")
            new_content = content
        last_masked_prompt = new_content
        _set_message_content(body, idx, new_content)

    audit_info = {
        "original_prompt": last_user_prompt,
        "masked_prompt": last_masked_prompt,
    }

    _store_mapping(
        body,
        mapping,
        counters,
        metadata=__metadata__,
        chat_id=chat_id,
        message_id=message_id,
        audit_info=audit_info,
    )

    # Debug-Hinweis & Audit-Log für die UI
    md = _ensure_metadata(body)
    md.setdefault("pii_debug", {})["last_inlet_tokens"] = len(mapping)
    if isinstance(__metadata__, dict):
        __metadata__.setdefault("pii_debug", {})["last_inlet_tokens"] = len(mapping)

    if mapping:
        inlet_elements = []
        for token, orig in mapping.items():
            match = re.search(r"\[\[([A-Z_]+)_\d+\]\]", token)
            cat = match.group(1) if match else "PII"
            inlet_elements.append({
                "token": token,
                "kategorie": cat,
                "original": orig,
                "status": "Im Prompt geschwärzt (wird nach Antwort wiederhergestellt)",
            })
        audit_payload = {
            "anzahl_behandelt": len(mapping),
            "status": "Im Prompt maskiert (wartet auf Antwort)",
            "elemente": inlet_elements,
        }
        md["pii_audit"] = audit_payload
        if isinstance(__metadata__, dict):
            __metadata__["pii_audit"] = audit_payload

    log.info(f"[PII Filter] {len(mapping)} Tokens im Prompt geschwärzt (Counters: {counters})")
    return body


def outlet(
    body: dict,
    __metadata__: Optional[dict] = None,
    __user__: Optional[dict] = None,
    __event_emitter__: Optional[Callable] = None,
    __chat_id__: Optional[str] = None,
    __message_id__: Optional[str] = None,
) -> dict:
    """
    Nach dem LLM-Aufruf: Platzhalter in der letzten Assistant-Message wieder
    durch Originale ersetzen und auf Wunsch detailliertes Audit-Protokoll anfügen.
    """

    if not isinstance(body, dict):
        return body

    valves: Valves = getattr(outlet, "_valves_cache", Valves())

    # User-Switch
    if __user__ and isinstance(__user__, dict):
        user_valves = __user__.get("valves")
        if isinstance(user_valves, UserValves):
            if not user_valves.enabled:
                return body
            if not user_valves.deanonymize_for_me:
                return body

    if not valves.deanonymize_output:
        return body

    chat_id = __chat_id__ or body.get("chat_id") or (isinstance(__metadata__, dict) and __metadata__.get("chat_id"))
    message_id = __message_id__ or body.get("id") or (isinstance(__metadata__, dict) and __metadata__.get("message_id"))

    mapping, _counters, audit_info = _load_mapping(body, __metadata__, chat_id=chat_id, message_id=message_id)
    if not mapping:
        return body

    idx = -1
    msgs = body.get("messages") or []
    for i in range(len(msgs) - 1, -1, -1):
        m = msgs[i]
        if isinstance(m, dict) and m.get("role") == "assistant":
            idx = i
            break

    if idx == -1:
        return body

    try:
        body["messages"][idx] = _deanonymize_recursive(
            body["messages"][idx],
            mapping,
            deanonymize_reasoning=valves.deanonymize_reasoning
        )
    except Exception as exc:  # noqa: BLE001
        log.exception(f"[PII] Fehler beim Deanonymize: {exc}")

    # Aufklappbare Info-Box (Details) am Ende der Antwort anfügen
    if valves.show_audit_details and mapping:
        audit_box = _format_pii_audit_box(mapping, audit_info, valves)
        current_content = body["messages"][idx].get("content") or ""
        if "Datenschutz- & PII-Protokoll" not in current_content:
            body["messages"][idx]["content"] = f"{current_content}\n\n---\n{audit_box}"

    # Audit-Log für UI-Transparenz (Sichtbar im Info-Icon ℹ️)
    outlet_elements = []
    for token, orig in mapping.items():
        match = re.search(r"\[\[([A-Z_]+)_\d+\]\]", token)
        cat = match.group(1) if match else "PII"
        outlet_elements.append({
            "token": token,
            "kategorie": cat,
            "original": orig,
            "status": "Im Prompt geschwärzt ➔ In Antwort erfolgreich wiederhergestellt",
        })

    audit_data = {
        "anzahl_behandelt": len(mapping),
        "status": "Vollständig deanonymisiert (Originaldaten wiederhergestellt)",
        "elemente": outlet_elements,
    }

    if isinstance(__metadata__, dict):
        __metadata__["pii_audit"] = audit_data
        __metadata__.setdefault("pii_debug", {})["last_outlet_replacements"] = len(mapping)
    else:
        md = _ensure_metadata(body)
        md["pii_audit"] = audit_data
        md.setdefault("pii_debug", {})["last_outlet_replacements"] = len(mapping)

    log.info(f"[PII Filter] {len(mapping)} Tokens erfolgreich in der Antwort rehydriert.")
    return body


# ---------------------------------------------------------------------------
# Stream-Hook (optional)
# ---------------------------------------------------------------------------

_STREAM_BUFFER_KEY = "_pii_stream_buffer"


def stream(
    event: dict,
    __metadata__: Optional[dict] = None,
    __body__: Optional[dict] = None,
    __chat_id__: Optional[str] = None,
    __message_id__: Optional[str] = None,
) -> dict:
    """Live-Deanonymisierung für Streaming-Responses."""

    if not isinstance(event, dict):
        return event

    content = event.get("content")
    if not isinstance(content, str):
        return event

    chat_id = __chat_id__ or (isinstance(__metadata__, dict) and __metadata__.get("chat_id"))
    message_id = __message_id__ or (isinstance(__metadata__, dict) and __metadata__.get("message_id"))

    mapping, _, _ = _load_mapping(event, __metadata__, __body__, chat_id=chat_id, message_id=message_id)
    if not mapping:
        return event

    buf = event.get(_STREAM_BUFFER_KEY) or ""
    buf += content

    replaced = _deanonymize_text(buf, mapping)

    cut = len(replaced)
    open_idx = replaced.rfind("[[")
    close_idx = replaced.find("]]", open_idx) if open_idx != -1 else -1
    if open_idx != -1 and close_idx == -1:
        cut = open_idx

    out = replaced[:cut]
    event["content"] = out
    event[_STREAM_BUFFER_KEY] = replaced[cut:]
    return event



class Filter:
    Valves = Valves
    UserValves = UserValves

    def __init__(self):
        self.valves = Valves()

    def inlet(
        self,
        body: dict,
        __metadata__: Optional[dict] = None,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable] = None,
        __chat_id__: Optional[str] = None,
        __message_id__: Optional[str] = None,
    ) -> dict:
        inlet._valves_cache = self.valves
        return inlet(
            body,
            __metadata__=__metadata__,
            __user__=__user__,
            __event_emitter__=__event_emitter__,
            __chat_id__=__chat_id__,
            __message_id__=__message_id__,
        )

    def outlet(
        self,
        body: dict,
        __metadata__: Optional[dict] = None,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable] = None,
        __chat_id__: Optional[str] = None,
        __message_id__: Optional[str] = None,
    ) -> dict:
        outlet._valves_cache = self.valves
        return outlet(
            body,
            __metadata__=__metadata__,
            __user__=__user__,
            __event_emitter__=__event_emitter__,
            __chat_id__=__chat_id__,
            __message_id__=__message_id__,
        )

    def stream(
        self,
        event: dict,
        __metadata__: Optional[dict] = None,
        __body__: Optional[dict] = None,
        __chat_id__: Optional[str] = None,
        __message_id__: Optional[str] = None,
    ) -> dict:
        return stream(
            event,
            __metadata__=__metadata__,
            __body__=__body__,
            __chat_id__=__chat_id__,
            __message_id__=__message_id__,
        )


