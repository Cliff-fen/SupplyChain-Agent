-- Local demo credentials only. Provision independent secrets outside Compose.
CREATE ROLE supplymind_ro LOGIN PASSWORD 'supplymind-demo-ro'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
SELECT format('GRANT CONNECT ON DATABASE %I TO supplymind_ro', current_database()) \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO supplymind_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO supplymind_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO supplymind_ro;
ALTER ROLE supplymind_ro SET default_transaction_read_only = on;
