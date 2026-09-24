from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_site_deploy_status_contract():
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "app.js").read_text(encoding="utf-8")
    deploy = (ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(encoding="utf-8")

    assert 'meta name="yartchives-deployed-at" content="__YARTCHIVES_DEPLOYED_AT__"' in index
    assert 'id="siteMeta"' in index
    assert 'aria-live="polite"' in index
    assert "https://api.github.com" in index
    assert 'Ready to test · production ${shortSha} · deployed ${age}' in app
    assert 'Deploying update… · current production ${shortSha}' in app
    assert 'Deployment blocked · production still ${shortSha}' in app
    assert 'actions/workflows/deploy-pages.yml/runs?per_page=1' in app
    assert 'void refreshProductionStatus();' in app
    assert 'meta[name="yartchives-deployed-at"]' in app
    assert 'DEPLOYED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"' in deploy
    assert '__YARTCHIVES_DEPLOYED_AT__' in deploy


def test_interactive_deploy_notification_contract():
    app = (ROOT / "app.js").read_text(encoding="utf-8")
    deploy = (ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(encoding="utf-8")
    apply_next = (ROOT / "apply-next-ui.js").read_text(encoding="utf-8")

    assert "deployment-status.json" in deploy
    assert "commits/$BUILD_SHA/pulls" in deploy
    assert 'startswith("agent/interactive/")' in deploy
    assert "pull-requests: read" in deploy
    assert "DEPLOY_NOTIFICATION_POLL_MS = 30 * 1000" in app
    assert '"Enable deploy alerts"' in app
    assert "Notification.requestPermission()" in app
    assert '"Yartchives update is live"' in app
    assert "requireInteraction: true" in app
    assert 'navigator.serviceWorker.register("./service-worker.js", { scope: "./" })' in app
    assert 'registration.showNotification("Yartchives update is live", options)' in app
    assert 'new notificationImpl("Yartchives update is live", options)' in app
    worker = (ROOT / "service-worker.js").read_text(encoding="utf-8")
    assert 'notificationclick' in worker
    assert 'clients.matchAll' in worker
    assert 'clients.openWindow' in worker
    assert 'addEventListener("push"' in worker
    assert "registration.showNotification" in worker
    assert "web_push === 8030" in worker
    manifest = (ROOT / "manifest.webmanifest").read_text(encoding="utf-8")
    assert '"display": "standalone"' in manifest
    assert '<link rel="manifest" href="manifest.webmanifest" />' in index
    assert "payload?.interactive === true" in app
    assert "cryptoImpl.subtle.generateKey" in app
    assert "registration.pushManager.subscribe" in app
    assert "YARTCHIVES_PUSH_SUBSCRIPTION" in app
    assert "YARTCHIVES_VAPID_PRIVATE_KEY" in app
    assert "settings/secrets/actions" in app
    assert "Send interactive deploy push" in deploy
    assert "github.event_name == 'push'" in deploy
    assert "scripts/send_web_push.py --build-sha" in deploy
    assert "${{ secrets.YARTCHIVES_PUSH_SUBSCRIPTION }}" in deploy
    assert "${{ secrets.YARTCHIVES_VAPID_PRIVATE_KEY }}" in deploy
    assert 'data.productionStatus = "true"' in apply_next
