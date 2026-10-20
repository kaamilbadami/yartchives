from scripts.domain_discovery import enrich_domains
import json
universe = json.load(open("employer_universe.json"))
employers_to_enrich = {"employers": []}
for emp in universe["employers"]:
    has_domain_hint = bool(emp.get("domain_hints")) or any(
        bool(m.get("domain_hints"))
        for m in (emp.get("seed_metadata", {})).values()
        if isinstance(m, dict)
    )
    if not has_domain_hint:
        employers_to_enrich["employers"].append(emp)
print(f"To enrich: {len(employers_to_enrich['employers'])}")
updated = enrich_domains(employers_to_enrich)
for emp in updated["employers"]:
    if "domain_hints" in emp:
        for original in universe["employers"]:
            if original["id"] == emp["id"]:
                original["domain_hints"] = emp["domain_hints"]

with open("employer_universe.json", "w", encoding="utf-8") as f:
    json.dump(universe, f, indent=2, ensure_ascii=False)
    f.write("\n")
