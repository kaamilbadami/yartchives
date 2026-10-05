CREATE TABLE IF NOT EXISTS ai_profile_usage (
  usage_date TEXT NOT NULL,
  client_id TEXT NOT NULL,
  request_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (usage_date, client_id)
);

CREATE INDEX IF NOT EXISTS idx_ai_profile_usage_date
  ON ai_profile_usage(usage_date);
