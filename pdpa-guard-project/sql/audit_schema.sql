-- PDPA Guard audit schema. Idempotent. Run as the database owner / admin.
-- Staff roles get NO access to this schema; views call pdpa_audit.tok() with the
-- view owner's rights, so staff can neither read the audit trail nor use tok() as an oracle.

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS pdpa_audit;

CREATE TABLE IF NOT EXISTS pdpa_audit.secrets (
    name  text PRIMARY KEY,
    value text NOT NULL
);

CREATE TABLE IF NOT EXISTS pdpa_audit.events (
    id            bigserial PRIMARY KEY,
    ts            timestamptz NOT NULL DEFAULT now(),
    app_user      text,
    db_role       text,
    purpose       text,
    stmt_type     text,
    sql_text      text,
    tables        text[] NOT NULL DEFAULT '{}',
    rows          integer NOT NULL DEFAULT 0,
    denied        boolean NOT NULL DEFAULT false,
    reason        text,
    unmasked_nric integer NOT NULL DEFAULT 0,
    duration_ms   real
);
CREATE INDEX IF NOT EXISTS events_ts_idx ON pdpa_audit.events (ts);

-- Row-level change log (who changed which record, old/new values).
-- NOTE: this table itself contains personal data: protect it and apply retention (s.24, s.25).
CREATE TABLE IF NOT EXISTS pdpa_audit.changes (
    id       bigserial PRIMARY KEY,
    ts       timestamptz NOT NULL DEFAULT now(),
    app_user text,
    db_role  text,
    db_user  text,
    tbl      text NOT NULL,
    op       text NOT NULL,
    old_row  jsonb,
    new_row  jsonb
);
CREATE INDEX IF NOT EXISTS changes_ts_idx ON pdpa_audit.changes (ts);

CREATE TABLE IF NOT EXISTS pdpa_audit.findings (
    id         bigserial PRIMARY KEY,
    ts         timestamptz NOT NULL DEFAULT now(),
    rule_id    text NOT NULL,
    obligation text,
    severity   text NOT NULL,
    app_user   text,
    db_role    text,
    tbl        text,
    event_id   bigint,
    detail     text,
    status     text NOT NULL DEFAULT 'open',
    UNIQUE (rule_id, event_id)
);

CREATE TABLE IF NOT EXISTS pdpa_audit.notifications (
    id         bigserial PRIMARY KEY,
    ts         timestamptz NOT NULL DEFAULT now(),
    to_role    text NOT NULL,
    message    text NOT NULL,
    finding_id bigint
);

CREATE TABLE IF NOT EXISTS pdpa_audit.breach_cases (
    id         bigserial PRIMARY KEY,
    ts         timestamptz NOT NULL DEFAULT now(),
    finding_id bigint,
    status     text NOT NULL DEFAULT 'open',
    body       jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS pdpa_audit.policy_state (
    id         integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    applied_at timestamptz,
    policy_name text,
    policy_yaml text
);

-- Deterministic pseudonymisation (HMAC-SHA256). Same key as the Python tokeniser.
CREATE OR REPLACE FUNCTION pdpa_audit.tok(val text) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pdpa_audit, public, pg_temp
AS $$
    SELECT CASE WHEN val IS NULL THEN NULL
           ELSE 'tok_' || left(encode(hmac(lower(btrim(val)),
                    (SELECT value FROM pdpa_audit.secrets WHERE name = 'token_key'), 'sha256'), 'hex'), 12)
           END
$$;
REVOKE ALL ON FUNCTION pdpa_audit.tok(text) FROM PUBLIC;

CREATE OR REPLACE FUNCTION pdpa_audit.log_change() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pdpa_audit, pg_temp
AS $$
BEGIN
    INSERT INTO pdpa_audit.changes (app_user, db_role, db_user, tbl, op, old_row, new_row)
    VALUES (current_setting('pdpa.app_user', true), current_setting('pdpa.db_role', true), session_user,
            TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, TG_OP,
            CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) END,
            CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END);
    RETURN NULL;
END
$$;

-- Retention sweep helper: tables with a retention_until column. Returns rows past retention.
CREATE OR REPLACE FUNCTION pdpa_audit.overdue(tbl regclass, col text DEFAULT 'retention_until')
RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
    EXECUTE format('SELECT count(*) FROM %s WHERE NULLIF(%I, '''')::date < current_date', tbl, col) INTO n;
    RETURN n;
END
$$;
