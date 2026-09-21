#!/usr/bin/env bash
set -euo pipefail

base="${1:?base SHA/ref required}"
head="${2:-HEAD}"

changed_paths="$(git diff --name-only "$base" "$head")"
printf '%s\n' "$changed_paths"

if printf '%s\n' "$changed_paths" | grep -Eq '^(data/listings\.json$|data/workday-inspections\.json$|sources\.json$|direct_sources\.json$|employer_universe\.json$|data/employer-seeds/|audit/samples/|scripts/(build_feed|careers_resolver|direct_|parallel_ats_collect|repair_links|provider_links|jobright_links|source_links|reconcile_workday_duplicates|coverage_|benchmark_quality|source_contribution_audit|employer_|fortune_500_seed|state_of_ats_seed|refresh_employer_universe|update_workday_inspections)\.py$|\.github/workflows/(update-feed|coverage-audit|coverage-automation|refresh-inspections)\.yml$)'; then
  echo "health=true"
else
  echo "health=false"
fi
