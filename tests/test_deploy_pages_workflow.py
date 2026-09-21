from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pages_deploy_recovers_after_automerge_site_changes():
    workflow = (ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(encoding="utf-8")

    assert "- Auto-merge autonomous agent PRs" in workflow
    assert "fetch-depth: 0" in workflow
    assert 'SOURCE_HEAD_SHA: ${{ github.event.workflow_run.head_sha }}' in workflow
    assert 'git diff --name-only "$SOURCE_HEAD_SHA" "$CURRENT_SHA"' in workflow
    assert "scripts/build_apply_next_inspections\\.py" in workflow
    assert "Auto-merge did not change deploy-relevant paths; skipping Pages deployment." in workflow
    assert workflow.count("if: steps.should_deploy.outputs.deploy == 'true'") >= 5
