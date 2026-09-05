"""
Unit-Tests für den Two-Layer Reversible PII Filter (pii_filter.py).
Prüft:
- Regex-Erkennung strukturierter Daten (IBAN, Kreditkarte, E-Mail, Telefon, IPv4)
- Reversibilität im Outlet (Re-Hydrierung)
- Live-Stream Chunk-Buffer Hook (stream)
- Zusammenspiel mit Metadata & PII-Counters für den Model Router
"""

import unittest
from pii_filter import Filter, Valves, UserValves, stream, _STREAM_BUFFER_KEY


class TestPIIFilter(unittest.TestCase):
    def setUp(self):
        self.filter = Filter()

    def test_iban_redaction_and_restore(self):
        iban = "DE44 5001 0517 5409 3201 00"
        text = f"Bitte überweise 500 Euro auf die IBAN {iban}."
        body = {"messages": [{"role": "user", "content": text}]}

        # 1. Inlet
        body = self.filter.inlet(body)
        redacted = body["messages"][0]["content"]
        self.assertNotIn(iban, redacted)
        self.assertIn("[[IBAN_1]]", redacted)
        self.assertIn("pii_map", body.get("metadata", {}))
        self.assertEqual(body["metadata"]["pii_map"]["[[IBAN_1]]"], iban)

        # 2. Outlet
        assistant_reply = f"Überweisung auf [[IBAN_1]] wurde vorgemerkt."
        body["messages"].append({"role": "assistant", "content": assistant_reply})
        body = self.filter.outlet(body, __metadata__=body.get("metadata"))
        restored = body["messages"][1]["content"]
        self.assertIn(iban, restored)
        parts = restored.split("<details>")
        actual_reply = parts[0]
        self.assertNotIn("[[IBAN_1]]", actual_reply)
        self.assertIn("Datenschutz- & PII-Protokoll", restored)

    def test_email_and_phone_redaction(self):
        email = "max.mustermann@unternehmen-gmbh.de"
        phone = "+49 171 1234567"
        text = f"Kontakt: {email} oder telefonisch unter {phone}."
        body = {"messages": [{"role": "user", "content": text}]}

        body = self.filter.inlet(body)
        redacted = body["messages"][0]["content"]
        self.assertNotIn(email, redacted)
        self.assertNotIn(phone, redacted)
        self.assertIn("[[EMAIL_1]]", redacted)
        self.assertTrue("[[PHONE_DE_1]]" in redacted or "[[PHONE_INTL_1]]" in redacted)

    def test_credit_card_and_ipv4(self):
        card = "4111 2222 3333 4444"
        ip = "192.168.178.55"
        text = f"Zahlung mit {card} von IP-Adresse {ip}."
        body = {"messages": [{"role": "user", "content": text}]}

        body = self.filter.inlet(body)
        redacted = body["messages"][0]["content"]
        self.assertNotIn(card, redacted)
        self.assertNotIn(ip, redacted)
        self.assertIn("[[CREDIT_CARD_1]]", redacted)
        self.assertIn("[[IPV4_1]]", redacted)

    def test_stream_split_token_rehydration(self):
        token = "[[IBAN_1]]"
        original = "DE89 3704 0044 0532 0130 00"
        metadata = {"pii_map": {token: original}}

        event1 = {"content": "Konto: [[IB"}
        res1 = stream(event1, __metadata__=metadata)
        self.assertEqual(res1["content"], "Konto: ")
        self.assertEqual(res1.get(_STREAM_BUFFER_KEY), "[[IB")

        event2 = {"content": "AN_1]] bestätigt.", _STREAM_BUFFER_KEY: res1.get(_STREAM_BUFFER_KEY)}
        res2 = stream(event2, __metadata__=metadata)
        self.assertEqual(res2["content"], f"{original} bestätigt.")

    def test_audit_log_generation(self):
        text = "Sende Geld an DE44 5001 0517 5409 3201 00."
        body = {"messages": [{"role": "user", "content": text}]}
        body = self.filter.inlet(body)

        metadata = body.get("metadata", {})
        self.assertIn("pii_audit", metadata)
        audit = metadata["pii_audit"]
        self.assertGreaterEqual(audit["anzahl_behandelt"], 1)
        self.assertTrue(any(e["kategorie"] == "IBAN" for e in audit["elemente"]))

    def test_user_valves_disabled(self):
        text = "Sende Geld an DE44 5001 0517 5409 3201 00."
        body = {"messages": [{"role": "user", "content": text}]}
        user = {"valves": UserValves(enabled=False)}

        body = self.filter.inlet(body, __user__=user)
        self.assertEqual(body["messages"][0]["content"], text)

    def test_stream_openai_delta_deanonymization(self):
        text = "Kontakt: max.mustermann@example.com bitte antworten."
        body = {"messages": [{"role": "user", "content": text}]}
        metadata = {}
        body = self.filter.inlet(body, __metadata__=metadata)

        # Simuliere OpenAI SSE Chunks
        chunk1 = {"choices": [{"delta": {"content": "Ihre Email lautet "}}]}
        chunk2 = {"choices": [{"delta": {"content": "[[EMAIL_1]]"}}]}
        chunk3 = {"choices": [{"delta": {"content": "."}, "finish_reason": "stop"}]}

        res1 = self.filter.stream(chunk1, __metadata__=metadata)
        self.assertEqual(res1["choices"][0]["delta"]["content"], "Ihre Email lautet ")

        res2 = self.filter.stream(chunk2, __metadata__=metadata)
        self.assertEqual(res2["choices"][0]["delta"]["content"], "max.mustermann@example.com")

        res3 = self.filter.stream(chunk3, __metadata__=metadata)
        self.assertEqual(res3["choices"][0]["delta"]["content"], ".")

    def test_stream_tool_calls_arguments_deanonymization(self):
        text = "Erstelle ein Skript mit Email max.mustermann@example.com"
        body = {"messages": [{"role": "user", "content": text}]}
        metadata = {}
        body = self.filter.inlet(body, __metadata__=metadata)

        # Simuliere OpenAI SSE Chunk für tool_calls Arguments
        chunk = {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "function": {
                                    "name": "write_file",
                                    "arguments": '{"content": "EMAIL=\\"[[EMAIL_1]]\\""}'
                                }
                            }
                        ]
                    },
                    "finish_reason": "stop"
                }
            ]
        }

        res = self.filter.stream(chunk, __metadata__=metadata)
        args = res["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"]
        self.assertEqual(args, '{"content": "EMAIL=\\"max.mustermann@example.com\\""}')


if __name__ == "__main__":
    unittest.main()

