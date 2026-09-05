"""
Test Suite für den Hybrid Model Router Filter (Open WebUI)
Testet:
- Datenschutz-Sperre bei PII
- Intent-Erkennung (Coding, Reasoning, Writing, Uncensored)
- Automatische Parameter-Injektion (Temperature, Top-P)
- Manuelle Overrides (#r1, #code, #opus etc.) und Tag-Bereinigung
- Vorrang von Datenschutz vor manuellem #cloud Override
"""

import unittest
from model_router import Filter, Valves, UserValves, PROFILES


class TestModelRouter(unittest.TestCase):
    def setUp(self):
        self.router = Filter()

    def test_default_writing_and_routine_goes_to_gemma(self):
        """Einfacher Text / Routine soll auf die Workstation zu Gemma 4 gehen (0 Cloud-Credits)."""
        body = {
            "model": "default-ui-model",
            "messages": [
                {"role": "user", "content": "Kannst du diesen Absatz bitte verständlicher formulieren?"}
            ],
            "metadata": {}
        }
        res = self.router.inlet(body)
        self.assertEqual(res["model"], "LMStudio.google/gemma-4-12b-qat")
        self.assertEqual(res["temperature"], PROFILES["writing"]["temperature"])
        self.assertEqual(res["top_p"], PROFILES["writing"]["top_p"])
        self.assertEqual(res["metadata"]["router_decision"]["profile"], "writing")

    def test_coding_standard_goes_to_local_coder(self):
        """Standard-Coding-Aufgaben gehen an Qwen 2.5 Coder auf der Workstation."""
        body = {
            "model": "default-ui-model",
            "messages": [
                {"role": "user", "content": "Schreibe ein Python-Skript, das eine CSV-Datei einliest und sortiert."}
            ],
            "metadata": {}
        }
        res = self.router.inlet(body)
        self.assertEqual(res["model"], "LMStudio.qwen2.5-coder-14b-instruct")
        self.assertEqual(res["temperature"], PROFILES["coding"]["temperature"])
        self.assertEqual(res["top_p"], PROFILES["coding"]["top_p"])

    def test_coding_complex_goes_to_claude_sonnet(self):
        """Sehr komplexe Coding-/Architektur-Aufgaben ohne PII gehen an Claude Sonnet 4.5 in der Cloud."""
        body = {
            "model": "default-ui-model",
            "messages": [
                {"role": "user", "content": "Entwirf eine Microservice-Architektur für verteilte Transaktionen mit Saga Pattern und Event Sourcing in Go und Dockerfile."}
            ],
            "metadata": {}
        }
        res = self.router.inlet(body)
        self.assertEqual(res["model"], "openrouter.anthropic/claude-sonnet-4.5")
        self.assertEqual(res["temperature"], PROFILES["cloud_heavy"]["temperature"])
        self.assertEqual(res["top_p"], PROFILES["cloud_heavy"]["top_p"])

    def test_reasoning_goes_to_deepseek_r1(self):
        """Mathematische Herleitungen & Logik gehen an DeepSeek-R1 mit erzwungenem Denkspielraum."""
        body = {
            "model": "default-ui-model",
            "messages": [
                {"role": "user", "content": "Beweise schritt für schritt, dass die Wurzel aus 2 irrational ist."}
            ],
            "metadata": {}
        }
        res = self.router.inlet(body)
        self.assertEqual(res["model"], "LMStudio.deepseek-r1-distill-qwen-14b")
        self.assertEqual(res["temperature"], 0.60)
        self.assertEqual(res["top_p"], 0.95)

    def test_uncensored_intent_goes_to_heretic(self):
        """Sensible / tabulose / kontroverse Themen gehen an Heretic 9B ohne Zensur."""
        body = {
            "model": "default-ui-model",
            "messages": [
                {"role": "user", "content": "Schreibe eine unzensierte Analyse historischer Kriegsgreuel ohne moralisierende Floskeln."}
            ],
            "metadata": {}
        }
        res = self.router.inlet(body)
        self.assertEqual(res["model"], "LMStudio.qwen3.8-9b-distill-uncensored-heretic-i1")
        self.assertEqual(res["temperature"], 0.70)
        self.assertEqual(res["top_p"], 0.90)

    def test_critical_pii_blocks_cloud_and_forces_local_workstation(self):
        """Kritische PII (z.B. IBAN) sperrt Cloud komplett und forciert LM Studio auf der Workstation."""
        body = {
            "model": "default-ui-model",
            "messages": [
                {"role": "user", "content": "Erstelle eine Abrechnungs-Logik für [[IBAN_1]] und Betrag [[MONEY_1]]."}
            ],
            "metadata": {
                "pii_counters": {
                    "IBAN": 1
                },
                "pii_map": {
                    "[[IBAN_1]]": "DE89370400440532013000"
                }
            }
        }
        res = self.router.inlet(body)
        self.assertEqual(res["model"], "LMStudio.qwen2.5-coder-14b-instruct")
        self.assertTrue(res["metadata"]["router_decision"]["critical_pii_blocked"])
        self.assertIn("Datenschutz-Sperre", res["metadata"]["router_decision"]["reason"])
        self.assertEqual(len(res["metadata"]["router_decision"]["pii_behandelte_elemente"]), 1)
        elem = res["metadata"]["router_decision"]["pii_behandelte_elemente"][0]
        self.assertEqual(elem["token"], "[[IBAN_1]]")
        self.assertEqual(elem["original"], "DE89370400440532013000")
        self.assertIn("pii_audit", res["metadata"])

    def test_cloud_override_blocked_by_critical_pii(self):
        """Selbst wenn der User #cloud oder #opus angibt, schlägt die PII-Sperre zu."""
        body = {
            "model": "default-ui-model",
            "messages": [
                {"role": "user", "content": "#opus Bitte analysiere die Buchungen von [[CREDIT_CARD_1]]."}
            ],
            "metadata": {
                "pii_counters": {
                    "CREDIT_CARD": 1
                }
            }
        }
        res = self.router.inlet(body)
        # Darf NICHT Claude Opus sein!
        self.assertNotEqual(res["model"], "openrouter.anthropic/claude-opus-4.6")
        self.assertEqual(res["model"], "LMStudio.deepseek-r1-distill-qwen-14b")
        self.assertTrue(res["metadata"]["router_decision"]["critical_pii_blocked"])

    def test_manual_tag_stripping_and_override(self):
        """Prüft, ob Tags wie #r1 aus dem Content entfernt werden und das Modell korrekt gesetzt wird."""
        body = {
            "model": "default-ui-model",
            "messages": [
                {"role": "user", "content": "#r1 Wie viele Primzahlen gibt es unter 100?"}
            ],
            "metadata": {}
        }
        res = self.router.inlet(body)
        self.assertEqual(res["model"], "LMStudio.deepseek-r1-distill-qwen-14b")
        # Tag muss entfernt worden sein
        self.assertEqual(res["messages"][0]["content"], "Wie viele Primzahlen gibt es unter 100?")


    def test_manual_gpt_override(self):
        """Prüft, ob #gpt oder #openai zu OpenAI GPT-5.2 in der Cloud mit Profil cloud_gpt geroutet wird."""
        body = {
            "model": "default-ui-model",
            "messages": [
                {"role": "user", "content": "#gpt Berechne die Wahrscheinlichkeit bei einem Münzwurf."}
            ],
            "metadata": {}
        }
        res = self.router.inlet(body)
        self.assertEqual(res["model"], "openrouter.openai/gpt-5.2")
        self.assertEqual(res["metadata"]["router_decision"]["profile"], "cloud_gpt")
        self.assertEqual(res["temperature"], PROFILES["cloud_gpt"]["temperature"])
        self.assertEqual(res["top_p"], PROFILES["cloud_gpt"]["top_p"])
        self.assertEqual(res["messages"][0]["content"], "Berechne die Wahrscheinlichkeit bei einem Münzwurf.")

    def test_known_inactive_model_fallback(self):
        """Prüft, ob bekannte defekte Modelle (404/400) automatisch auf funktionierende Alternativen fallen."""
        # Valve absichtlich auf inaktives Modell stellen
        self.router.valves.MODEL_CLOUD_FAST = "openrouter.google/gemini-3-pro-preview"
        body = {
            "model": "default-ui-model",
            "messages": [
                {"role": "user", "content": "#flash Erstelle eine Zusammenfassung"}
            ],
            "metadata": {}
        }
        res = self.router.inlet(body)
        # Muss auf gemini-3-flash-preview umgeleitet worden sein
        self.assertEqual(res["model"], "openrouter.google/gemini-3-flash-preview")
        self.assertIn("Auto-Fallback", res["metadata"]["router_decision"]["reason"])


if __name__ == "__main__":
    unittest.main()

