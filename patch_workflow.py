import re

with open(".github/workflows/update-feed.yml", "r") as f:
    content = f.read()

content = content.replace('\"collection\"', '"collection"')
content = content.replace('\"enrichment\"', '"enrichment"')
content = content.replace('\"link repair\"', '"link repair"')
content = content.replace('\"ATS reconciliation\"', '"ATS reconciliation"')
content = content.replace('\"validation\"', '"validation"')
content = content.replace('\"audit\"', '"audit"')

with open(".github/workflows/update-feed.yml", "w") as f:
    f.write(content)
