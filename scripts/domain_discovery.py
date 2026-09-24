import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

def normalize_company(name: str) -> str:
    name = name.lower()
    name = re.sub(r'\(.*?\)', '', name)
    name = re.sub(r'[^a-z0-9\s]', ' ', name)

    stop_words = [
        'inc', 'incorporated', 'corp', 'corporation',
        'co', 'company', 'ltd', 'limited', 'plc',
        'llc', 'group', 'holdings', 'holding', 'stores',
        'insurance', 'processing'
    ]
    words = name.split()
    words = [w for w in words if w not in stop_words]
    return " ".join(words)


def _domain_is_plausible(domain: str, aliases: list[str]) -> bool:
    if not domain:
        return False
    if domain.endswith(".edu") or domain.endswith(".gov") or domain.endswith(".org"):
        return False
    domain_norm = normalize_company(domain.split('.')[0])
    for alias in aliases:
        if domain_norm == alias:
            return True
        if len(alias) >= 4 and alias in domain_norm:
            if len(domain_norm) <= len(alias) + 2:
                return True
        if len(domain_norm) >= 4 and domain_norm in alias:
            if len(alias) <= len(domain_norm) + 4:
                return True
    return False
    domain_norm = normalize_company(domain.split('.')[0])
    for alias in aliases:
        if domain_norm == alias:
            return True
        # If it's a partial match, it must be highly similar, not "alphabetdeal" for "alphabet"
        if len(alias) >= 4 and alias in domain_norm:
            if len(domain_norm) <= len(alias) + 2:
                return True
        if len(domain_norm) >= 4 and domain_norm in alias:
            if len(alias) <= len(domain_norm) + 4:
                return True
    return False
    domain_norm = normalize_company(domain.split('.')[0])
    for alias in aliases:
        if domain_norm == alias:
            return True
        if len(alias) >= 4 and (alias in domain_norm or domain_norm in alias):
            # Avoid obvious false positives like alphabetdeal.com for alphabet
            if domain_norm.startswith(alias) and len(domain_norm) > len(alias) + 3:
                continue
            return True
    return False

def get_company_domain(name: str) -> str | None:
    overrides = {
        "gold.com": "gold.com",
        "guidewell mutual holding": "guidewell.com"
    }
    if name.lower() in overrides:
        return overrides[name.lower()]

    query = urllib.parse.quote(f"{name}")
    target_norm = normalize_company(name)

    if not target_norm:
        return None

    aliases = [target_norm]
    words = name.split()
    if len(words) > 1:
        initials = "".join([w[0].lower() for w in words if w.isalnum()])
        if initials:
            aliases.append(initials)

    m = re.search(r'\(([^)]+)\)', name)
    if m:
        aliases.append(normalize_company(m.group(1)))

    if "." in name:
        aliases.append(name.split(".")[0].lower())

    url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={query}&utf8=&format=json"
    max_retries = 5
    data = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers={'User-Agent': 'YartchivesEmployerDiscovery/1.0 (contact@kaamilbadami.com)'})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                break
        except Exception as e:
            if '429' in str(e) and attempt < max_retries - 1:
                time.sleep(1 + attempt)
            else:
                break

    if data and data.get('query', {}).get('search'):
        for res in data['query']['search'][:3]:
            title = res['title']
            title_norm = normalize_company(title)

            match_found = False
            for alias in aliases:
                if (alias in title_norm or title_norm in alias or
                    (len(alias) > 5 and len(title_norm) > 5 and
                     (alias[:5] == title_norm[:5]))):
                     match_found = True
                     break

            if match_found:
                title_encoded = urllib.parse.quote(title)
                url_page = f"https://en.wikipedia.org/w/api.php?action=parse&page={title_encoded}&prop=text&format=json"

                for attempt in range(max_retries):
                    req_page = urllib.request.Request(url_page, headers={'User-Agent': 'YartchivesEmployerDiscovery/1.0 (contact@kaamilbadami.com)'})
                    try:
                        with urllib.request.urlopen(req_page, timeout=10) as resp_page:
                            data_page = json.loads(resp_page.read().decode('utf-8'))
                            if 'parse' in data_page and 'text' in data_page['parse']:
                                html_text = data_page['parse']['text']['*']
                                m = re.search(r'Website.*?<a[^>]*href="([^"]+)"', html_text, re.DOTALL | re.IGNORECASE)
                                if m:
                                    domain = urllib.parse.urlparse(m.group(1)).netloc
                                    if domain and not "wikipedia" in domain and not "wikimedia" in domain:
                                        domain = domain.removeprefix("www.")
                                        if _domain_is_plausible(domain, aliases):
                                            return domain
                            break
                    except Exception as e:
                        if '429' in str(e) and attempt < max_retries - 1:
                            time.sleep(1 + attempt)
                        else:
                            break

    query_cb = urllib.parse.quote(name)
    url = f"https://autocomplete.clearbit.com/v1/companies/suggest?query={query_cb}"
    data = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers={'User-Agent': 'YartchivesEmployerDiscovery/1.0 (contact@kaamilbadami.com)'})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                break
        except Exception as e:
            if '429' in str(e) and attempt < max_retries - 1:
                time.sleep(1 + attempt)
            else:
                break

    if data:
        for item in data:
            res_name = item.get('name', '')
            res_norm = normalize_company(res_name)
            if not target_norm or not res_norm:
                continue

            domain = str(item['domain']).lower()
            domain_norm = normalize_company(domain.split('.')[0])

            if _domain_is_plausible(str(item['domain']), aliases):
                return str(item['domain'])

    return None

def enrich_domains(seed: dict[str, Any]) -> dict[str, Any]:
    def fetch(emp: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        if emp.get("domain_hints"):
            return emp, None
        return emp, get_company_domain(emp['name'])

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(fetch, emp): emp for emp in seed.get("employers", [])}
        for future in as_completed(futures):
            emp, domain = future.result()
            if domain:
                if "domain_hints" not in emp:
                    emp["domain_hints"] = []
                emp["domain_hints"].append(domain)

    for emp in seed.get("employers", []):
        if "domain_hints" in emp:
            emp["domain_hints"] = sorted(list(set(emp["domain_hints"])))

    return seed
