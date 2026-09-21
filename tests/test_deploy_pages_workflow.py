from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_automerge_explicitly_dispatches_pages_from_resulting_main():
    deploy = (ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(encoding="utf-8")
    automerge = (ROOT / ".github" / "workflows" / "auto-merge-agent-prs.yml").read_text(encoding="utf-8")

    assert "- Auto-merge autonomous agent PRs" not in deploy
    assert "workflow_dispatch:" in deploy
    assert "SOURCE_HEAD_SHA" not in deploy
    assert "steps.should_deploy" not in deploy

    assert "- name: Capture main before merge" in automerge
    assert 'BEFORE_SHA: ${{ steps.main_before.outputs.sha }}' in automerge
    assert "git fetch origin main" in automerge
    assert 'AFTER_SHA="$(git rev-parse origin/main)"' in automerge
    assert 'git diff --name-only "$BEFORE_SHA" "$AFTER_SHA"' in automerge
    assert "scripts/build_apply_next_inspections\\.py" in automerge
    assert 'gh workflow run deploy-pages.yml --repo "$REPOSITORY" --ref main' in automerge
    assert automerge.index("python scripts/auto_merge_agent_prs.py") < automerge.index("gh workflow run deploy-pages.yml")


def test_pages_workflow_still_deploys_and_verifies_current_main():
    workflow = (ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(encoding="utf-8")

    assert "ref: main" in workflow
    assert "fetch-depth: 0" in workflow
    assert "scripts/build_apply_next_inspections.py data/workday-inspections.json _site/data/apply-next-inspections.json" in workflow
    assert "Verify live deployment" in workflow
    assert "LIVE_SHA" in workflow
    assert 'build_sha=%s\\n' in workflow
