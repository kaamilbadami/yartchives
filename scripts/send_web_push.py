#!/usr/bin/env python3
import argparse
import json
import os
import sys


TITLE = "Yartchives update is live"
BODY = "Your interactive change is deployed and ready to test."
VAPID_SUBJECT = "mailto:kaamil.badami@gmail.com"


def push_payload(build_sha: str) -> str:
    tag = f"yartchives-deploy-{build_sha}" if build_sha else "yartchives-deploy-live"
    return json.dumps(
        {
            "title": TITLE,
            "body": BODY,
            "tag": tag,
            "navigate": "./",
            "data": {"url": "./"},
        },
        separators=(",", ":"),
    )


def load_subscription(raw: str) -> dict:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("push subscription must be a JSON object")
    endpoint = payload.get("endpoint")
    keys = payload.get("keys")
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        raise ValueError("push subscription endpoint must be https")
    if not isinstance(keys, dict) or not keys.get("p256dh") or not keys.get("auth"):
        raise ValueError("push subscription keys are incomplete")
    return payload


def send_push(subscription_raw: str, private_key: str, build_sha: str, webpush_impl=None) -> bool:
    if not subscription_raw or not private_key:
        print("Web Push secrets are not configured; skipping deploy push.")
        return False

    subscription = load_subscription(subscription_raw)
    if webpush_impl is None:
        from pywebpush import webpush as webpush_impl

    webpush_impl(
        subscription_info=subscription,
        data=push_payload(build_sha),
        vapid_private_key=private_key,
        vapid_claims={"sub": VAPID_SUBJECT},
        ttl=300,
    )
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Send the verified interactive Yartchives deploy notification.")
    parser.add_argument("--build-sha", default=os.environ.get("BUILD_SHA", ""))
    args = parser.parse_args(argv)

    subscription = os.environ.get("YARTCHIVES_PUSH_SUBSCRIPTION", "")
    private_key = os.environ.get("YARTCHIVES_VAPID_PRIVATE_KEY", "")
    try:
        sent = send_push(subscription, private_key, args.build_sha)
    except Exception as exc:
        print(f"::error::Web Push delivery failed: {exc}", file=sys.stderr)
        return 1

    if sent:
        print(f"Sent Yartchives deploy push for {args.build_sha or 'current build'}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
