from pathlib import Path

root = Path('.')
src = root / 'scripts/direct_ct_icims.py'
text = src.read_text()
text = text.replace(
'''"""Add CT CS-relevant sibling jobs from iCIMS career sites already evidenced in-feed.\n\nThis is a targeted gap-filler, not a broad iCIMS crawler. A site becomes eligible\nonly when the normalized feed already contains a Connecticut CS listing with an\nauthoritative public iCIMS URL. We then search that same public career site for\nstudent roles and merge matching CT CS opportunities using the existing direct\nsource upsert semantics.\n"""''',
'''"""Add US CS-relevant sibling jobs from iCIMS career sites already evidenced in-feed.\n\nThis is a provider-family gap-filler, not a broad iCIMS crawler. A site becomes\neligible only when the normalized feed already contains a CS listing with an\nauthoritative public iCIMS URL. We then search that same public career site for\nstudent roles and merge matching US CS opportunities using the existing direct\nsource upsert semantics.\n"""''')
text = text.replace('DEFAULT_STATE = "CT"\n', '')
text = text.replace(
'''def _job_in_scope(job: dict[str, Any], state: str) -> bool:\n    states = {str(value).upper() for value in (job.get("states") or []) if value}\n    profiles = {str(value).lower() for value in (job.get("profiles") or []) if value}\n    return state.upper() in states and "cs" in profiles\n\n\ndef source_from_job(job: dict[str, Any], state: str = DEFAULT_STATE) -> dict[str, Any] | None:\n    if not _job_in_scope(job, state):\n        return None\n''',
'''def _evidences_cs(job: dict[str, Any]) -> bool:\n    return "cs" in {str(value).lower() for value in (job.get("profiles") or []) if value}\n\n\ndef source_from_job(job: dict[str, Any]) -> dict[str, Any] | None:\n    if not _evidences_cs(job):\n        return None\n    if job.get("link_kind") not in {None, "direct"}:\n        return None\n''')
text = text.replace('"key": f"{state.casefold()}-auto-icims-{slug}",', '"key": f"auto-icims-{slug}",')
text = text.replace('        "state": state.upper(),\n', '')
text = text.replace('def discover_sources(feed: dict[str, Any], state: str = DEFAULT_STATE) -> list[dict[str, Any]]:', 'def discover_sources(feed: dict[str, Any]) -> list[dict[str, Any]]:')
text = text.replace('        source = source_from_job(job, state)\n', '        source = source_from_job(job)\n')
marker = '''def extract_sitemap_job_links(raw_xml: str, source: dict[str, Any]) -> list[str]:\n'''
insert = '''def _looks_us(location: str) -> bool:\n    if bf.extract_states(location):\n        return True\n    return bool(\n        re.search(\n            r"\\b(?:United States|USA|U\\.S\\.|US Remote|Remote[- ]?US|Remote[- ]?USA)\\b",\n            location or "",\n            flags=re.I,\n        )\n    )\n\n\n'''
if marker not in text:
    raise SystemExit('sitemap marker not found')
text = text.replace(marker, insert + marker, 1)
text = text.replace('    if not is_target_state(location, source["state"]):\n        return None\n', '    if not _looks_us(location):\n        return None\n')
text = text.replace('    if source["state"] not in job.get("states", []):\n        job["states"] = sorted(set(job.get("states", [])) | {source["state"]})\n', '')
text = text.replace(' direct CT CS-relevant listing(s)', ' direct US CS-relevant listing(s)')
new_src = root / 'scripts/direct_icims.py'
new_src.write_text(text)
src.unlink()

# Update workflow to use the national adapter.
wf = root / '.github/workflows/update-feed.yml'
w = wf.read_text()
w = w.replace('scripts/direct_ct_icims.py', 'scripts/direct_icims.py')
w = w.replace('Add sibling Connecticut iCIMS coverage from evidenced career sites', 'Add sibling US iCIMS coverage from evidenced career sites')
w = w.replace('python scripts/direct_ct_icims.py data/listings.json --old-feed /tmp/yartchives-old-listings.json', 'python scripts/direct_icims.py data/listings.json --old-feed /tmp/yartchives-old-listings.json')
wf.write_text(w)

# Keep strict provider evidence through enrichment.
enrich = root / 'scripts/enrich_feed.py'
e = enrich.read_text()
e = e.replace('    "auto-greenhouse-",\n)', '    "auto-greenhouse-",\n    "auto-icims-",\n)')
enrich.write_text(e)

# Rename/adapt regression tests.
test_old = root / 'tests/test_direct_ct_icims.py'
t = test_old.read_text()
t = t.replace('SCRIPT_DIR / "direct_ct_icims.py"', 'SCRIPT_DIR / "direct_icims.py"')
t = t.replace('"direct_ct_icims"', '"direct_icims"')
t = t.replace('class DirectCtIcimsTests', 'class DirectIcimsTests')
t = t.replace('test_discovers_one_evidenced_ct_cs_icims_site', 'test_discovers_evidenced_cs_icims_sites_nationally')
t = t.replace('        self.assertEqual(len(sources), 1)\n', '        self.assertEqual(len(sources), 2)\n')
t = t.replace('            "key": "ct-auto-icims-careers-gdeb-icims-com",', '            "key": "auto-icims-careers-gdeb-icims-com",')
t = t.replace('            "state": "CT",\n', '')
addition = '''\n    def test_non_us_student_role_is_rejected(self):\n        source = {\n            "key": "auto-icims-careers-example-icims-com",\n            "name": "Example (auto-discovered iCIMS)",\n            "company": "Example",\n            "homepage": "https://careers-example.icims.com/jobs/intro",\n        }\n        inspection = {\n            "status": "inspected",\n            "posting": {\n                "title": "Software Engineering Intern",\n                "date_posted": "2026-09-03",\n                "locations": {"status": "authoritative", "values": ["Toronto, ON, Canada"]},\n            },\n        }\n        job = mod.job_from_inspection(\n            source,\n            "https://careers-example.icims.com/jobs/999/job",\n            inspection,\n            datetime(2026, 9, 17, tzinfo=timezone.utc),\n        )\n        self.assertIsNone(job)\n'''
t = t.replace('\n\nif __name__ == "__main__":\n', addition + '\n\nif __name__ == "__main__":\n')
test_new = root / 'tests/test_direct_icims.py'
test_new.write_text(t)
test_old.unlink()

# Quality compile list should include the production adapter explicitly.
q = root / '.github/workflows/quality.yml'
qt = q.read_text()
qt = qt.replace('scripts/direct_ct_workday.py scripts/posting_requirements.py', 'scripts/direct_ct_workday.py scripts/direct_icims.py scripts/posting_requirements.py')
q.write_text(qt)
