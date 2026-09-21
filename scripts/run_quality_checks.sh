#!/usr/bin/env bash
set -euo pipefail

phase="${1:-all}"

run_python() {
  python -m py_compile scripts/auto_merge_agent_prs.py scripts/build_feed.py scripts/careers_resolver.py scripts/direct_ct_workday.py scripts/parallel_ats_collect.py scripts/posting_requirements.py scripts/workday_inspector.py scripts/icims_inspector.py scripts/greenhouse_inspector.py scripts/update_workday_inspections.py scripts/reconcile_workday_duplicates.py scripts/enrich_feed.py scripts/repair_links.py scripts/provider_links.py scripts/jobright_links.py scripts/source_links.py scripts/validate_feed.py scripts/audit_feed.py scripts/coverage_audit.py scripts/coverage_contract.py scripts/benchmark_quality.py scripts/source_contribution_audit.py scripts/employer_universe.py scripts/employer_seed_from_benchmark.py scripts/fortune_500_seed.py scripts/state_of_ats_seed.py scripts/refresh_employer_universe.py scripts/update_readme_status.py
  python -m unittest discover -s tests -p "test_*.py" -v
}

run_frontend() {
  node --check analytics.js
  node --check frontend-utils.js
  node --check app.js
  node --check enhancements.js
  node --check ui.js
  node --check ux.js
  node --check location-display.js
  node --check share.js
  node --check apply-next.js
  node --check apply-next-readiness.js
  node --check apply-next-competition.js
  node --check apply-next-location.js
  node --check apply-next-location-preferences.js
  node --check apply-next-location-profile-ui.js
  node --check apply-next-presentation.js
  node --check apply-next-ui.js
  node --check apply-next-profile-setup.js
  node tests/analytics.test.cjs
  node tests/deploy-assets.test.cjs
  node tests/frontend-utils.test.cjs
  node tests/location-display.test.cjs
  node tests/apply-next.test.cjs
  node tests/apply-next-readiness.test.cjs
  node tests/apply-next-competition.test.cjs
  node tests/apply-next-location.test.cjs
  node tests/apply-next-location-preferences.test.cjs
  node tests/apply-next-location-profile-ui.test.cjs
  node tests/apply-next-presentation.test.cjs
  node tests/apply-next-presentation-browser.test.cjs
  node tests/apply-next-ui.test.cjs
  node tests/apply-next-profile-setup.test.cjs
}

run_feed() {
  python scripts/enrich_feed.py data/listings.json
  python scripts/repair_links.py data/listings.json --offline
  python scripts/reconcile_workday_duplicates.py data/listings.json
  python scripts/validate_feed.py data/listings.json --minimum-jobs 500 --minimum-healthy-sources 8
  python scripts/audit_feed.py data/listings.json
}

run_benchmark() {
  python scripts/coverage_audit.py audit/samples/northeast-midatlantic-cs-2026-09-17.json \
    --feed data/listings.json
}

case "$phase" in
  python) run_python ;;
  frontend) run_frontend ;;
  feed) run_feed ;;
  benchmark) run_benchmark ;;
  all)
    run_python
    run_frontend
    run_feed
    run_benchmark
    ;;
  *)
    echo "Unknown quality phase: $phase" >&2
    exit 2
    ;;
esac
