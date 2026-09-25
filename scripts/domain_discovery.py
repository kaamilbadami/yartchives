import json
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

CORPORATE_TLDS = {"com", "co", "net", "org", "io", "ai"}
NON_CORPORATE_SUFFIXES = {"edu", "gov", "mil"}


def normalize_company(name: str) -> str:
    name = name.lower()
    name = re.sub(r"\(.*?\)", "", name)
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    stop_words = {
        "inc", "incorporated", "corp", "corporation", "co", "company",
        "ltd", "limited", "plc", "llc", "group", "holdings", "holding",
        "stores", "insurance", "processing",
    }
    return "".join(word for word in name.split() if word not in stop_words)


def _domain_token(domain: str) -> str:
    host = domain.casefold().removeprefix("www.").split(":", 1)[0]
    labels = [label for label in host.split(".") if label]
    if len(labels) < 2:
        return ""
    return normalize_company(labels[-2])


def _domain_is_plausible(domain: str, aliases: list[str]) -> bool:
    host = domain.casefold().removeprefix("www.").strip(".")
    labels = host.split(".")
    if len(labels) < 2 or labels[-1] in NON_CORPORATE_SUFFIXES or labels[-1] not in CORPORATE_TLDS:
        return False
    token = _domain_token(host)
    if not token:
        return False
    for alias in aliases:
        if not alias:
            continue
        if token == alias:
            return True
        if len(alias) >= 5 and len(token) >= 5:
            if token.startswith(alias) and token[len(alias):] in {"co", "inc"}:
                return True
            if alias.startswith(token) and alias[len(token):] in {"co", "inc"}:
                return True
            if token in alias:
                return True
    return False

def _aliases(name: str) -> list[str]:
    target = normalize_company(name)
    aliases = [target] if target else []
    words = re.findall(r"[A-Za-z0-9]+", name)
    if len(words) > 1:
        initials = "".join(word[0].lower() for word in words)
        if len(initials) >= 2:
            aliases.append(initials)
    match = re.search(r"\(([^)]+)\)", name)
    if match:
        aliases.append(normalize_company(match.group(1)))
    return list(dict.fromkeys(alias for alias in aliases if alias))


def get_company_domain(name: str) -> str | None:
    overrides = {
        "gold.com": "gold.com",
        "guidewell mutual holding": "guidewell.com",
        "fidelity national information (fis)": "fisglobal.com",
        "fifth third bancorp": "53.com",
        "goodyear tire & rubber": "goodyear.com",
        "guardian life ins. co. of america": "guardianlife.com",
        "advanced micro devices": "amd.com",
        "massachusetts mutual life insurance": "massmutual.com",
        "mondelēz international": "mondelezinternational.com",
        "o'reilly automotive": "oreillyauto.com",
        "packaging corp. of america": "packagingcorp.com",
        "plains gp holdings": "plains.com",
        "united services automobile assn.": "usaa.com",
        "westinghouse air brake": "wabteccorp.com",
    }
    if name.lower() in overrides:
        return overrides[name.lower()]

    aliases = _aliases(name)
    if not aliases:
        return None

    query = urllib.parse.quote(name)
    max_retries = 5
    data = None
    url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={query}&utf8=&format=json"
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers={"User-Agent": "YartchivesEmployerDiscovery/1.0 (contact@kaamilbadami.com)"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                break
        except Exception as exc:
            if "429" in str(exc) and attempt < max_retries - 1:
                time.sleep(1 + attempt)
            else:
                break

    if data and data.get("query", {}).get("search"):
        for result in data["query"]["search"][:3]:
            title_norm = normalize_company(result["title"])
            if not any(
                alias == title_norm
                or (len(alias) >= 5 and len(title_norm) >= 5 and (alias in title_norm or title_norm in alias))
                for alias in aliases
            ):
                continue
            title_encoded = urllib.parse.quote(result["title"])
            page_url = f"https://en.wikipedia.org/w/api.php?action=parse&page={title_encoded}&prop=text&format=json"
            for attempt in range(max_retries):
                req = urllib.request.Request(page_url, headers={"User-Agent": "YartchivesEmployerDiscovery/1.0 (contact@kaamilbadami.com)"})
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        page = json.loads(resp.read().decode("utf-8"))
                    html_text = ((page.get("parse") or {}).get("text") or {}).get("*", "")
                    match = re.search(r'Website.*?<a[^>]*href="([^"]+)"', html_text, re.DOTALL | re.IGNORECASE)
                    if match:
                        domain = urllib.parse.urlparse(match.group(1)).netloc.removeprefix("www.")
                        if _domain_is_plausible(domain, aliases):
                            return domain
                    break
                except Exception as exc:
                    if "429" in str(exc) and attempt < max_retries - 1:
                        time.sleep(1 + attempt)
                    else:
                        break

    query_cb = urllib.parse.quote(name)
    url = f"https://autocomplete.clearbit.com/v1/companies/suggest?query={query_cb}"
    data = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers={"User-Agent": "YartchivesEmployerDiscovery/1.0 (contact@kaamilbadami.com)"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                break
        except Exception as exc:
            if "429" in str(exc) and attempt < max_retries - 1:
                time.sleep(1 + attempt)
            else:
                break

    for item in data or []:
        result_name = normalize_company(str(item.get("name") or ""))
        domain = str(item.get("domain") or "").casefold()
        if not result_name or not domain:
            continue
        if not any(
            alias == result_name
            or (len(alias) >= 5 and len(result_name) >= 5 and (alias in result_name or result_name in alias))
            for alias in aliases
        ):
            continue
        if _domain_is_plausible(domain, aliases):
            return domain
    return None


def enrich_domains(seed: dict[str, Any]) -> dict[str, Any]:
    def fetch(emp: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        if emp.get("domain_hints"):
            return emp, None
        domain = get_company_domain(emp["name"])
        print(f"Discovered domain for {emp['name']}: {domain}")
        return emp, domain

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(fetch, emp): emp for emp in seed.get("employers", [])}
        for future in as_completed(futures):
            emp, domain = future.result()
            if domain:
                emp.setdefault("domain_hints", []).append(domain)

    for emp in seed.get("employers", []):
        if "domain_hints" in emp:
            emp["domain_hints"] = sorted(set(emp["domain_hints"]))
    return seed
