CREATE TABLE IF NOT EXISTS usage_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  received_at TEXT NOT NULL DEFAULT (datetime('now')),
  schema_version TEXT NOT NULL,
  visitor_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  first_seen_day TEXT NOT NULL,
  returning_visitor INTEGER NOT NULL CHECK (returning_visitor IN (0, 1)),
  sequence INTEGER NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT NOT NULL,
  build_sha TEXT NOT NULL DEFAULT '',
  site_open INTEGER NOT NULL DEFAULT 0,
  apply_next_open INTEGER NOT NULL DEFAULT 0,
  profile_created INTEGER NOT NULL DEFAULT 0,
  recommendations_shown INTEGER NOT NULL DEFAULT 0,
  apply_clicked INTEGER NOT NULL DEFAULT 0,
  saved INTEGER NOT NULL DEFAULT 0,
  hidden INTEGER NOT NULL DEFAULT 0,
  feedback_submitted INTEGER NOT NULL DEFAULT 0,
  apply_next_timing INTEGER NOT NULL DEFAULT 0,
  timings_json TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_usage_batches_received_at ON usage_batches(received_at);
CREATE INDEX IF NOT EXISTS idx_usage_batches_visitor_id ON usage_batches(visitor_id);
CREATE INDEX IF NOT EXISTS idx_usage_batches_session_id ON usage_batches(session_id);

CREATE TABLE IF NOT EXISTS daily_usage (
  usage_date TEXT PRIMARY KEY,
  unique_visitors INTEGER NOT NULL DEFAULT 0,
  returning_visitors INTEGER NOT NULL DEFAULT 0,
  sessions INTEGER NOT NULL DEFAULT 0,
  apply_next_sessions INTEGER NOT NULL DEFAULT 0,
  recommendations_shown INTEGER NOT NULL DEFAULT 0,
  apply_clicked INTEGER NOT NULL DEFAULT 0,
  saved INTEGER NOT NULL DEFAULT 0,
  hidden INTEGER NOT NULL DEFAULT 0,
  feedback_submitted INTEGER NOT NULL DEFAULT 0
);
