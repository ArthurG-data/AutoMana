-- ============================================================================
-- PostgreSQL Users and Permissions Report
-- ============================================================================
-- Run this script with: psql -U postgres -d automana -f check_db_users.sql

\echo '========================================================================='
\echo '📊 PostgreSQL Users and Permissions Report'
\echo '========================================================================='

-- 1. ALL DATABASE USERS/ROLES
\echo ''
\echo '1️⃣  ALL DATABASE USERS/ROLES:'
\echo '-------------------------------------------------------------------------'
SELECT 
    usename AS "User",
    usesuper AS "Superuser",
    usecreatedb AS "Can Create DB",
    usecanlogin AS "Can Login",
    valuntil AS "Valid Until"
FROM pg_user 
ORDER BY usename;

-- 2. ROLE MEMBERSHIP (Group Memberships)
\echo ''
\echo '2️⃣  ROLE MEMBERSHIP (Group Memberships):'
\echo '-------------------------------------------------------------------------'
SELECT 
    member.rolname AS "Member",
    role.rolname AS "Role"
FROM pg_roles as member
JOIN pg_auth_members ON member.oid = pg_auth_members.member
JOIN pg_roles as role ON role.oid = pg_auth_members.role
ORDER BY member.rolname, role.rolname;

-- 3. DATABASE PRIVILEGES
\echo ''
\echo '3️⃣  DATABASE PRIVILEGES:'
\echo '-------------------------------------------------------------------------'
SELECT 
    grantee,
    privilege_type,
    is_grantable
FROM information_schema.database_privileges
WHERE grantee != 'pg_database_owner'
ORDER BY grantee, privilege_type;

-- 4. TABLE PRIVILEGES
\echo ''
\echo '4️⃣  TABLE PRIVILEGES:'
\echo '-------------------------------------------------------------------------'
SELECT 
    grantee,
    table_schema,
    table_name,
    string_agg(privilege_type, ', ' ORDER BY privilege_type) AS "Privileges",
    max(is_grantable) AS "With Grant"
FROM information_schema.table_privileges
WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
GROUP BY grantee, table_schema, table_name
ORDER BY grantee, table_schema, table_name;

-- 5. SCHEMA PRIVILEGES
\echo ''
\echo '5️⃣  SCHEMA PRIVILEGES:'
\echo '-------------------------------------------------------------------------'
SELECT 
    grantee,
    table_schema,
    privilege_type,
    is_grantable
FROM information_schema.schema_privileges
WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
ORDER BY grantee, table_schema, privilege_type;

-- 6. DETAILED USER ATTRIBUTES
\echo ''
\echo '6️⃣  DETAILED USER ATTRIBUTES:'
\echo '-------------------------------------------------------------------------'
SELECT 
    rolname,
    rolsuper,
    rolinherit,
    rolcreaterole,
    rolcreatedb,
    rolcanlogin,
    rolreplication,
    rolbypassrls
FROM pg_roles
WHERE rolname NOT LIKE 'pg_%'
ORDER BY rolname;

-- 7. CURRENT USER AND CURRENT DATABASE
\echo ''
\echo '7️⃣  CONNECTION INFO:'
\echo '-------------------------------------------------------------------------'
SELECT 
    current_user AS "Current User",
    current_database() AS "Current Database",
    pg_postmaster_start_time() AS "PostgreSQL Start Time";

\echo ''
\echo '========================================================================='
\echo '� CHECKING FOR SPECIFIC USERS'
\echo '========================================================================='

-- Check if app_readonly exists
\echo ''
\echo 'Checking for app_readonly user...'
SELECT 
    rolname AS "User",
    rolsuper AS "Superuser",
    rolcreatedb AS "Can Create DB",
    rolcanlogin AS "Can Login"
FROM pg_roles
WHERE rolname = 'app_readonly';

-- Check if app_ro exists
\echo ''
\echo 'Checking for app_ro user...'
SELECT 
    rolname AS "User",
    rolsuper AS "Superuser",
    rolcreatedb AS "Can Create DB",
    rolcanlogin AS "Can Login"
FROM pg_roles
WHERE rolname = 'app_ro';

\echo ''
\echo '========================================================================='
\echo '🔒 GRANTING READ-ONLY ACCESS TO app_ro FOR ALL DATABASE OBJECTS'
\echo '========================================================================='

-- Grant USAGE on all schemas
\echo ''
\echo 'Granting USAGE on all schemas to app_ro...'
GRANT USAGE ON SCHEMA public, card_catalog, ops, pricing TO app_ro;

-- Grant SELECT on all existing tables in all schemas
\echo 'Granting SELECT on all tables to app_ro...'
GRANT SELECT ON ALL TABLES IN SCHEMA public, card_catalog, ops, pricing TO app_ro;

-- Grant SELECT on all existing views in all schemas
\echo 'Granting SELECT on all views to app_ro...'
GRANT SELECT ON ALL TABLES IN SCHEMA public, card_catalog, ops, pricing TO app_ro;

-- Grant USAGE on all sequences (for nextval, currval queries)
\echo 'Granting USAGE on all sequences to app_ro...'
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public, card_catalog, ops, pricing TO app_ro;

-- Set default privileges for future tables/views/sequences
\echo ''
\echo 'Setting default privileges for future objects...'
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO app_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO app_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA card_catalog GRANT SELECT ON TABLES TO app_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA card_catalog GRANT USAGE ON SEQUENCES TO app_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA ops GRANT SELECT ON TABLES TO app_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA ops GRANT USAGE ON SEQUENCES TO app_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA pricing GRANT SELECT ON TABLES TO app_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA pricing GRANT USAGE ON SEQUENCES TO app_ro;

\echo ''
\echo '========================================================================='
\echo '✅ Read-only access granted! app_ro can now read all database objects'
\echo '========================================================================='
