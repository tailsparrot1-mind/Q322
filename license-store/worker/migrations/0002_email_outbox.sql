CREATE TABLE IF NOT EXISTS email_outbox (
  order_id TEXT PRIMARY KEY REFERENCES orders(id),
  license_id TEXT NOT NULL UNIQUE REFERENCES licenses(id),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sending','sent','failed')),
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  sent_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_email_outbox_pending ON email_outbox(status,next_attempt_at);
