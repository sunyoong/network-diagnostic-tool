CREATE TABLE IF NOT EXISTS schema_migrations (
    version varchar(100) PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_accounts (
    id uuid PRIMARY KEY,
    username varchar(50) NOT NULL UNIQUE,
    email varchar(320) UNIQUE,
    display_name varchar(100) NOT NULL,
    password_hash text NOT NULL,
    role varchar(20) NOT NULL CHECK (role IN ('ADMIN','OPERATOR','VIEWER')),
    status varchar(20) NOT NULL CHECK (status IN ('PENDING','ACTIVE','LOCKED','DISABLED')),
    must_change_password boolean NOT NULL DEFAULT true,
    failed_login_count integer NOT NULL DEFAULT 0,
    locked_until timestamptz,
    last_login_at timestamptz,
    password_changed_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid REFERENCES user_accounts(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    disabled_at timestamptz,
    deleted_at timestamptz,
    version integer NOT NULL DEFAULT 1
);

CREATE TABLE user_password_history (
    id bigserial PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
    password_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_sessions (
    id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
    token_hash varchar(64) NOT NULL UNIQUE,
    csrf_token_hash varchar(64) NOT NULL,
    client_key varchar(64),
    user_agent_summary varchar(255),
    created_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    idle_expires_at timestamptz NOT NULL,
    absolute_expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    revoke_reason varchar(50)
);

CREATE TABLE account_action_tokens (
    id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
    action_type varchar(30) NOT NULL, token_hash varchar(64) NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
    used_at timestamptz, created_by uuid REFERENCES user_accounts(id) ON DELETE SET NULL
);

CREATE TABLE diagnostic_runs (
    id uuid PRIMARY KEY, user_id uuid REFERENCES user_accounts(id) ON DELETE SET NULL,
    diagnostic_type varchar(16) NOT NULL, success boolean NOT NULL, result_code varchar(40) NOT NULL,
    api_status_code smallint NOT NULL, error_message varchar(500), duration_ms integer NOT NULL,
    client_key varchar(64), client_ip inet, source varchar(20) NOT NULL DEFAULT 'WEB', app_version varchar(40),
    started_at timestamptz NOT NULL, completed_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE http_diagnostic_results (
    run_id uuid PRIMARY KEY REFERENCES diagnostic_runs(id) ON DELETE CASCADE,
    requested_url text NOT NULL, target_host varchar(253) NOT NULL, method varchar(8) NOT NULL,
    timeout_ms integer NOT NULL, follow_redirects boolean NOT NULL, query_redacted boolean NOT NULL DEFAULT false,
    final_url text, reachable boolean NOT NULL, status_code smallint, reason_phrase varchar(120), resolved_ip inet,
    response_time_ms integer, content_length bigint, content_type varchar(255), server_header varchar(255),
    redirect_count smallint NOT NULL DEFAULT 0
);

CREATE TABLE tcp_diagnostic_results (
    run_id uuid PRIMARY KEY REFERENCES diagnostic_runs(id) ON DELETE CASCADE,
    host varchar(253) NOT NULL, port integer NOT NULL, timeout_ms integer NOT NULL, resolved_ips inet[] NOT NULL DEFAULT '{}',
    is_open boolean NOT NULL, connection_result varchar(20) NOT NULL, connection_time_ms integer, message varchar(500) NOT NULL
);

CREATE TABLE dns_diagnostic_results (
    run_id uuid PRIMARY KEY REFERENCES diagnostic_runs(id) ON DELETE CASCADE,
    domain varchar(253) NOT NULL, record_type varchar(10) NOT NULL, records text[] NOT NULL DEFAULT '{}',
    record_count integer NOT NULL DEFAULT 0, records_redacted boolean NOT NULL DEFAULT false,
    ttl integer, resolver varchar(255), lookup_time_ms integer
);

CREATE TABLE audit_events (
    id bigserial PRIMARY KEY, run_id uuid REFERENCES diagnostic_runs(id) ON DELETE SET NULL,
    actor_user_id uuid REFERENCES user_accounts(id) ON DELETE SET NULL, event_type varchar(50) NOT NULL,
    severity varchar(10) NOT NULL, client_key varchar(64), details jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL
);

CREATE TABLE auth_audit_events (
    id bigserial PRIMARY KEY, actor_user_id uuid REFERENCES user_accounts(id) ON DELETE SET NULL,
    target_user_id uuid REFERENCES user_accounts(id) ON DELETE SET NULL, event_type varchar(50) NOT NULL,
    outcome varchar(10) NOT NULL, reason_code varchar(50), client_key varchar(64), session_id uuid,
    details jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL
);

CREATE INDEX ix_runs_user_created ON diagnostic_runs (user_id, created_at DESC);
CREATE INDEX ix_sessions_active_user ON user_sessions (user_id, absolute_expires_at);
CREATE INDEX ix_password_history_user_created ON user_password_history (user_id, created_at DESC);
