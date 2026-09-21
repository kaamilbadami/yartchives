from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_site_deploy_status_contract():
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "app.js").read_text(encoding="utf-8")
    deploy = (ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(encoding="utf-8")

    assert 'meta name="yartchives-deployed-at" content="__YARTCHIVES_DEPLOYED_AT__"' in index
    assert 'id="siteMeta"' in index
    assert 'Site updated ${age}' in app
    assert 'meta[name="yartchives-deployed-at"]' in app
    assert 'DEPLOYED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"' in deploy
    assert '__YARTCHIVES_DEPLOYED_AT__' in deploy
