CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
--TABLES
CREATE TABLE IF NOT EXISTS users (
    username TEXT NOT NULL UNIQUE,
    unique_id UUID NOT NULL PRIMARY KEY DEFAULT uuid_generate_v4(),
	email VARCHAR(50) NOT NULL UNIQUE,
    fullname VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    hashed_password TEXT,
    disabled BOOLEAN DEFAULT FALSE,
    changed_by UUID REFERENCES users(unique_id) ON DELETE CASCADE --for keeping track of who made the change, should be null exept durinf update
);

CREATE TABLE IF NOT EXISTS roles (
    unique_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    role VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);


CREATE TABLE IF NOT EXISTS user_roles (
    user_role_id SERIAL PRIMARY KEY, 
    user_id UUID REFERENCES users(unique_id) ON DELETE CASCADE NOT NULL,
    role_id UUID REFERENCES roles(unique_id) ON DELETE CASCADE NOT NULL, 
    assigned_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ,
    effective_from TIMESTAMPTZ DEFAULT now(),
    UNIQUE (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(unique_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    device_id UUID UNIQUE, 
    active BOOLEAN DEFAULT TRUE
);


CREATE TABLE IF NOT EXISTS refresh_tokens (
    token_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE NOT NULL,
    refresh_token TEXT NOT NULL,
    refresh_token_expires_at TIMESTAMPTZ NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    revoked BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS session_audit_logs (
    log_id SERIAL PRIMARY KEY,
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE NOT NULL ,
    action TEXT NOT NULL, -- e.g., 'deactivated', 'revoked', etc.
    reason TEXT,          -- optional description
    performed_at TIMESTAMPTZ DEFAULT now(), -- when the action happened
    performed_by UUID REFERENCES users(unique_id) NOT NULL,     -- optional: who did the action (admin, user, system)
    source_ip TEXT NOT NULL         -- optional: from which IP the action was triggered
);

CREATE TABLE IF NOT EXISTS user_audit_logs (
    log_id SERIAL PRIMARY KEY, 
    user_id UUID REFERENCES users(unique_id) ON DELETE CASCADE NOT NULL,
    action TEXT NOT NULL,
    reason TEXT,
    performed_at TIMESTAMPTZ DEFAULT now(), -- when the action happened
    performed_by UUID REFERENCES users(unique_id) NOT NULL,     -- optional: who did the action (admin, user, system)
    source_ip TEXT
);

CREATE TABLE IF NOT EXISTS user_role_audit_logs (
    log_id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(unique_id) ON DELETE CASCADE NOT NULL,
    action TEXT,
    old_role TEXT, 
    old_role_id UUID REFERENCES roles(unique_id),
    new_role TEXT,
    new_role_id UUID REFERENCES roles(unique_id),
    performed_by UUID REFERENCES users(unique_id) NOT NULL,
    performed_at TIMESTAMPTZ DEFAULT now(),
    reason TEXT
);

CREATE TABLE permissions (
    permission_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    permission_name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE role_permissions (
    role_id UUID REFERENCES roles(unique_id) ON DELETE CASCADE,
    permission_id UUID REFERENCES permissions(permission_id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);
-----------------------------------------------------------------------------------------------------------------------------------
--VIEWS
CREATE OR REPLACE VIEW active_sessions_view AS
    SELECT u.unique_id AS user_id, u.username, s.created_at, s.expires_at AS session_expires_at, s.ip_address, s.user_agent, rt.refresh_token, rt.refresh_token_expires_at, rt.token_id, s.id AS session_id
    FROM sessions s
    JOIN refresh_tokens rt ON rt.session_id = s.id
    JOIN users u ON u.unique_id = s.user_id
    WHERE s.active = TRUE AND revoked = FALSE AND s.expires_at > now() AND used = FALSE;

CREATE OR REPLACE VIEW sessions_view AS
    SELECT u.unique_id AS user_id, u.username, s.created_at, s.expires_at AS session_expires_at, s.ip_address, s.user_agent, rt.refresh_token, rt.refresh_token_expires_at, rt.token_id, s.id AS session_id
    FROM sessions s
    JOIN refresh_tokens rt ON rt.session_id = s.id
    JOIN users u ON u.unique_id = s.user_id;

CREATE OR REPLACE VIEW user_roles_permission_view AS
SELECT 
    s.unique_id,
    s.username,
    s.email,
    s.fullname,
    s.created_at,
    r.role,
    ur.role_id,
    p.permission_name,
    ur.assigned_at
FROM users s
JOIN user_roles ur ON ur.user_id = s.unique_id
JOIN roles r ON ur.role_id = r.unique_id
JOIN role_permissions rp on rp.role_id = r.unique_id
JOIN permissions p on p.permission_id = rp.permission_id;


----------------------------------------------------------------------------------------------------------------------------------
--FUNCTIONS
CREATE OR REPLACE FUNCTION insert_add_token(
    p_id UUID,
    p_user_id UUID,
    p_created_at TIMESTAMPTZ,
    p_expires_at TIMESTAMPTZ,
    p_ip_address TEXT, 
    p_user_agent TEXT,
    p_refresh_token TEXT,
    p_refresh_token_expires_at TIMESTAMPTZ,
    p_device_id TEXT DEFAULT NULL
)
RETURNS TABLE (session_id UUID, token_id UUID) AS $$
DECLARE
    v_session_id UUID;
    v_refresh_token_id UUID;

BEGIN
    INSERT INTO sessions ( id, user_id, created_at, expires_at, ip_address, user_agent)
    VALUES (p_id, p_user_id, p_created_at, p_expires_at,p_ip_address, p_user_agent)

    RETURNING id INTO v_session_id;
  
    INSERT INTO refresh_tokens (
        session_id, refresh_token, refresh_token_expires_at
    )
    VALUES (
        v_session_id, p_refresh_token, p_refresh_token_expires_at
    )

    RETURNING refresh_tokens.token_id INTO v_refresh_token_id;

    RETURN QUERY SELECT v_session_id, v_refresh_token_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION inactivate_session(
	p_session_id UUID,
    p_ip_address TEXT
)
RETURNS VOID AS $$
DECLARE
    v_exists BOOLEAN;
BEGIN --check if the session exists
    SELECT EXISTS (
        SELECT 1 FROM sessions WHERE id = p_session_id
    ) INTO v_exists;
    IF NOT v_exists THEN
        RAISE EXCEPTION 'Session ID % not found.', p_session_id;
    END IF;

	UPDATE sessions SET active = FALSE WHERE id = p_session_id;
	UPDATE refresh_tokens SET revoked = TRUE WHERE session_id = p_session_id;
    --INSERT INTO session_audit_logs (session_id, action, reason, performed_by, source_ip) VALUES (p_session_id, 'desactivated', 'Session inactivated manually.',p_user_id, p_ip_address);
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_audit_user_on_user_disabled() --function to update audi table when change to user status
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO user_audit_logs(
        user_id, 
        action,
        reason,
        perfromed_by,
        source_ip
    ) VALUES (
        NEW.unique_id,
        'User Disabled Change',
        'Disabled changed from ' || OLD.disabled || ' to ' || NEW.disabled,
        NEW.updated_by,
        NEW.source_ip
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION rotate_refresh_token(
    p_old_id UUID,
    p_session_id UUID,
    p_refresh_token TEXT,
    p_refresh_token_expires_at TIMESTAMPTZ
)
RETURNS UUID AS $$
DECLARE
    v_new_refresh_id UUID;
BEGIN

    UPDATE refresh_tokens
    SET used = TRUE
    WHERE token_id = p_old_id;

    INSERT INTO refresh_tokens (session_id, refresh_token, refresh_token_expires_at)
    VALUES (p_session_id, p_refresh_token, p_refresh_token_expires_at)
    RETURNING token_id INTO v_new_refresh_id;

    RETURN v_new_refresh_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION disable_refresh_token(
    p_refresh_token UUID
)
RETURNS VOID AS $$
BEGIN
    UPDATE refresh_tokens
    SET revoked = TRUE
    WHERE token_id = p_refresh_token;
END;
$$ LANGUAGE plpgsql

CREATE OR REPLACE FUNCTION log_user_role_change ()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO user_role_audit_logs (
            user_id, 
            action, 
            new_role, 
            new_role_id, 
            performed_by, 
            reason) 
        VALUES (
            NEW.user_id, 
            'role assigned',
            (SELECT role FROM roles WHERE unique_id = NEW.role_id),
            NEW.role_id,
            current_setting('app.current_user_id', true)::uuid,
            current_setting('app.role_change_reason', true)
            );
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO user_role_audit_logs(
            user_id, 
            action, 
            old_role, 
            old_role_id,  
            performed_by, 
            reason
            )
        VALUES(
            OLD.user_id,
            'role removed',
             (SELECT role FROM roles WHERE unique_id = OLD.role_id),
            OLD.role_id,
            current_setting('app.current_user_id', true)::uuid,
            current_setting('app.role_change_reason', true)
        );
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql; 

-------------------------------------------------------------------------------------------------------------------------
--TRIGGERS
CREATE TRIGGER trigger_log_user_status_change
AFTER UPDATE OF disabled ON users
FOR EACH ROW
WHEN (OLD.disabled IS DISTINCT FROM NEW.disabled)
EXECUTE FUNCTION update_audit_user_on_user_disabled();

CREATE TRIGGER trigger_log_user_role_insert
AFTER INSERT  ON user_roles
FOR EACH ROW
EXECUTE FUNCTION log_user_role_change();

CREATE TRIGGER trigger_log_user_role_delete
AFTER DELETE ON user_roles
FOR EACH ROW
EXECUTE FUNCTION log_user_role_change();
----------------------------------------------------------------------------------------------------------------------------