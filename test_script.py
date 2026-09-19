import sys
sys.path.insert(0, "./scripts")
from scripts.migrate_cached_requirements import migrate_entry
from scripts.posting_requirements import EXTRACTOR_VERSION
print(EXTRACTOR_VERSION)
