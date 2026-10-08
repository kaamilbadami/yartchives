import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "persona_external_discovery.py"
SPEC = importlib.util.spec_from_file_location("persona_external_discovery", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)


class PersonaExternalDiscoveryTests(unittest.TestCase):
    def test_parse_json_text_accepts_fenced_json(self):
        parsed = mod._parse_json_text('```json\n{\"discoveries\": []}\n```')
        self.assertEqual(parsed, {"discoveries": []})

    def test_discovery_surface_is_never_authoritative(self):
        with mock.patch.object(mod.requests, "get") as get:
            self.assertFalse(mod._validate_authoritative_url("https://www.linkedin.com/jobs/view/123", 1))
        get.assert_not_called()

    def test_reachable_employer_url_is_authoritative_even_when_access_forbidden(self):
        response = mock.Mock(status_code=403)
        with mock.patch.object(mod.requests, "get", return_value=response):
            self.assertTrue(mod._validate_authoritative_url("https://careers.example.com/jobs/123", 1))

    def test_rate_limit_retries_after_retry_after(self):
        rate_limited = mock.Mock(status_code=429, headers={"Retry-After": "1"}, text="rate limited")
        success = mock.Mock(
            status_code=200,
            headers={},
            json=lambda: {
                "output": [
                    {"type": "web_search_call"},
                    {"type": "message", "content": [{"type": "output_text", "text": '{"discoveries": []}'}]},
                ]
            },
        )
        persona = {"id": "KB"}
        with mock.patch.object(mod.requests, "post", side_effect=[rate_limited, success]) as post, \
             mock.patch.object(mod.time, "sleep") as sleep:
            rows = mod.discover(
                persona,
                endpoint="https://example.openai.azure.com",
                api_key="secret",
                deployment="gpt-test",
                max_results=12,
                timeout=1,
                max_search_calls=3,
            )
        self.assertEqual(rows, [])
        sleep.assert_called_once_with(1.0)
        request_json = post.call_args_list[0].kwargs["json"]
        self.assertEqual(request_json["reasoning"], {"effort": "low"})
        self.assertEqual(request_json["max_tool_calls"], 3)
        self.assertEqual(request_json["max_output_tokens"], 6000)

    def test_search_budget_is_independent_of_result_count(self):
        success = mock.Mock(
            status_code=200,
            headers={},
            json=lambda: {
                "output": [
                    {"type": "web_search_call"},
                    {"type": "message", "content": [{"type": "output_text", "text": '{"discoveries": []}'}]},
                ]
            },
        )
        with mock.patch.object(mod.requests, "post", return_value=success) as post:
            mod.discover(
                {"id": "KB"},
                endpoint="https://example.openai.azure.com",
                api_key="secret",
                deployment="gpt-test",
                max_results=50,
                timeout=1,
                max_search_calls=2,
            )
        self.assertEqual(post.call_args.kwargs["json"]["max_tool_calls"], 2)

    def test_logs_billable_web_search_requests(self):
        success = mock.Mock(
            status_code=200,
            headers={},
            json=lambda: {
                "output": [
                    {"type": "web_search_call"},
                    {"type": "message", "content": [{"type": "output_text", "text": '{"discoveries": []}'}]},
                ],
                "tool_usage": {"web_search": {"num_requests": 4}},
                "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
            },
        )
        with mock.patch.object(mod.requests, "post", return_value=success), \
             mock.patch("builtins.print") as printed:
            mod.discover(
                {"id": "KB"},
                endpoint="https://example.openai.azure.com",
                api_key="secret",
                deployment="gpt-test",
                max_results=1,
                timeout=1,
                max_search_calls=8,
            )
        metrics = [json.loads(call.args[0]) for call in printed.call_args_list if call.args]
        self.assertTrue(any(item.get("billable_web_search_requests") == 4 for item in metrics))
        self.assertTrue(any(item.get("total_tokens") == 120 for item in metrics))

    def test_response_text_prefers_top_level_output_text(self):
        payload = {
            "output_text": '{"discoveries": []}',
            "output": [{"type": "web_search_call", "id": "search"}],
        }
        self.assertEqual(mod._response_text(payload), '{"discoveries": []}')

    def test_response_text_reads_output_message_only(self):
        payload = {
            "output": [
                {"type": "web_search_call", "id": "search"},
                {"type": "message", "content": [{"type": "output_text", "text": "{\"discoveries\": []}"}]},
            ]
        }
        self.assertEqual(mod._response_text(payload), '{"discoveries": []}')


if __name__ == "__main__":
    unittest.main()
