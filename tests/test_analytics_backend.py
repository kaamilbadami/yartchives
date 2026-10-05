import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AnalyticsBackendTests(unittest.TestCase):
    def test_worker_enforces_privacy_boundary(self):
        worker = (ROOT / "analytics" / "worker.mjs").read_text(encoding="utf-8")
        self.assertIn('payload.schema !== SCHEMA', worker)
        self.assertIn('origin_not_allowed', worker)
        self.assertIn('unexpected_field', worker)
        self.assertIn('payload_too_large', worker)
        self.assertIn('INSERT INTO usage_batches', worker)
        self.assertNotRegex(worker, r'\b(email|resume|full_name|ip_address|user_agent)\b')

    def test_schema_has_rollup_and_retention_indexes_without_identity_fields(self):
        schema = (ROOT / "analytics" / "migrations" / "0001_usage.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS usage_batches", schema)
        self.assertIn("CREATE TABLE IF NOT EXISTS daily_usage", schema)
        self.assertIn("idx_usage_batches_received_at", schema)
        self.assertIn("idx_usage_batches_visitor_id", schema)
        self.assertNotRegex(schema, r'\b(email|resume|search|location|job_id|job_title|company|ip_address|user_agent)\b')

    def test_ai_profile_quota_schema_is_anonymous_and_bounded(self):
        schema = (ROOT / "analytics" / "migrations" / "0002_ai_profile_usage.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS ai_profile_usage", schema)
        self.assertIn("PRIMARY KEY (usage_date, client_id)", schema)
        self.assertNotRegex(schema, r"\b(email|resume|location|job_id|ip_address|user_agent)\b")

    def test_deploy_is_credential_gated_and_self_provisions_d1(self):
        workflow = (ROOT / ".github" / "workflows" / "deploy-analytics.yml").read_text(encoding="utf-8")
        self.assertIn("secrets.CLOUDFLARE_ACCOUNT_ID", workflow)
        self.assertIn("secrets.CLOUDFLARE_API_TOKEN", workflow)
        self.assertIn('WRANGLER="npx --yes wrangler@4.143.0"', workflow)
        self.assertIn("$WRANGLER d1 list --json", workflow)
        self.assertIn("d1 create yartchives-analytics --location enam", workflow)
        self.assertIn("d1 migrations apply yartchives-analytics", workflow)
        self.assertIn("wrangler@4.143.0 deploy", workflow)
        self.assertIn("yartchives-analytics-endpoint", workflow)
        self.assertIn("/health", workflow)
        self.assertIn("secrets.AZURE_OPENAI_API_KEY", workflow)
        self.assertIn("secrets.AZURE_OPENAI_ENDPOINT", workflow)
        self.assertIn("secrets.AZURE_OPENAI_DEPLOYMENT", workflow)
        self.assertIn("wrangler@4.143.0 secret put AZURE_OPENAI_API_KEY", workflow)
        self.assertNotIn("git push", workflow)

    def test_pages_consumes_endpoint_artifact_instead_of_endpoint_secret(self):
        pages = (ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(encoding="utf-8")
        self.assertIn("Deploy analytics backend", pages)
        self.assertIn("yartchives-analytics-endpoint", pages)
        self.assertIn("steps.analytics.outputs.endpoint", pages)
        self.assertNotIn("secrets.YARTCHIVES_ANALYTICS_ENDPOINT", pages)

    def test_wrangler_template_has_one_runtime_database_placeholder(self):
        config = (ROOT / "analytics" / "wrangler.template.jsonc").read_text(encoding="utf-8")
        self.assertEqual(config.count("__YARTCHIVES_ANALYTICS_D1_DATABASE_ID__"), 1)
        self.assertIn('"ALLOWED_ORIGIN": "https://kaamilbadami.github.io"', config)
        self.assertIn('"17 6 * * *"', config)


if __name__ == "__main__":
    unittest.main()
