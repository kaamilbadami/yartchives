import re
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
class Tests(unittest.TestCase):
 def test_contract(self):
  w=(ROOT/'.github/workflows/reconcile-merged-pr-issues.yml').read_text()
  self.assertIn('types: [closed]',w); self.assertIn('github.event.pull_request.merged == true',w); self.assertIn('issues: write',w)
  ref=re.compile(r'(?im)\\b(?:updates?|refs?|references?|related\\s+to)\\s+#(\\d+)\\b')
  done=re.compile(r'(?im)^\\s*Completes acceptance criteria for #(\\d+)\\s*$')
  self.assertEqual(ref.findall('Updates #449'),['449']); self.assertEqual(done.findall('Updates #449'),[]); self.assertEqual(done.findall('Completes acceptance criteria for #449'),['449'])
if __name__=='__main__': unittest.main()
