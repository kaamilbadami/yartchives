import json

from scripts import send_web_push


def test_push_payload_contract():
    payload = json.loads(send_web_push.push_payload("abc123"))
    assert payload["title"] == "Yartchives update is live"
    assert payload["body"] == "Your interactive change is deployed and ready to test."
    assert payload["tag"] == "yartchives-deploy-abc123"
    assert payload["navigate"] == "./"
    assert payload["data"]["url"] == "./"


def test_send_push_skips_without_secrets():
    assert send_web_push.send_push("", "", "abc123", webpush_impl=lambda **_: None) is False


def test_send_push_validates_and_calls_webpush():
    calls = []

    def fake_webpush(**kwargs):
        calls.append(kwargs)

    subscription = json.dumps({
        "endpoint": "https://push.example.test/subscription",
        "keys": {"p256dh": "public", "auth": "auth"},
    })
    assert send_web_push.send_push(subscription, "private-key", "abc123", webpush_impl=fake_webpush) is True
    assert len(calls) == 1
    assert calls[0]["subscription_info"]["endpoint"].startswith("https://")
    assert calls[0]["vapid_private_key"] == "private-key"
    assert calls[0]["vapid_claims"]["sub"].startswith("https://")
    assert calls[0]["ttl"] == 300


def test_load_subscription_rejects_incomplete_values():
    try:
        send_web_push.load_subscription('{"endpoint":"http://example.test"}')
    except ValueError:
        pass
    else:
        raise AssertionError("invalid subscription should be rejected")
