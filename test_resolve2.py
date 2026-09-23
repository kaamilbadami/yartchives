import json
import requests
from scripts.careers_resolver import resolve_employer
universe = json.load(open('employer_universe.json'))
for e in universe['employers']:
    if e['id'] == 'adobe':
        e['seed_metadata']['dummy'] = {'domain_hints': ['adobe.wd5.myworkdayjobs.com']}
        print(resolve_employer(e))
