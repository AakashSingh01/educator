import unittest

from llm import GeminiListener


class _Interactions:
    def __init__(self):
        self.request = None

    def create(self, **request):
        self.request = request
        return {
            "status": "completed",
            "id": "test-interaction",
            "output_text": '{"items":[]}',
            "usage": {
                "total_input_tokens": 100,
                "total_output_tokens": 20,
                "total_thought_tokens": 5,
                "total_tokens": 125,
            },
        }


class _Client:
    def __init__(self):
        self.interactions = _Interactions()


class GeminiListenerTests(unittest.TestCase):
    def test_uses_minimal_thinking_and_records_usage(self):
        client = _Client()
        listener = GeminiListener(
            api_key="test",
            client=client,
            thinking_level="minimal",
        )

        response = listener.chat("Return JSON", max_output_tokens=1800)

        self.assertEqual(response, '{"items":[]}')
        self.assertEqual(
            client.interactions.request["generation_config"],
            {"max_output_tokens": 1800, "thinking_level": "minimal"},
        )
        self.assertEqual(listener.last_response_metadata["status"], "completed")
        self.assertEqual(
            listener.last_response_metadata["usage"]["total_thought_tokens"], 5
        )

    def test_joins_model_output_steps_separated_by_thoughts(self):
        result = {
            "output_text": '["second"]}',
            "steps": [
                {"type": "user_input", "content": []},
                {
                    "type": "model_output",
                    "content": [{"type": "text", "text": '{"items":'}],
                },
                {"type": "thought", "content": []},
                {
                    "type": "model_output",
                    "content": [{"type": "text", "text": '["second"]}'}],
                },
            ],
        }

        self.assertEqual(
            GeminiListener._response_text(result),
            '{"items":["second"]}',
        )


if __name__ == "__main__":
    unittest.main()
