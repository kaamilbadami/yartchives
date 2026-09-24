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
    assert "payload?.interactive === true" in app
    assert 'data.productionStatus = "true"' in apply_next
