-- MYSQL_USER is initially granted ALL by the image entrypoint. Narrow it after
-- the administrator has imported the seed data; analysis must never own data.
REVOKE ALL PRIVILEGES ON supplychain.* FROM 'supplymind_ro'@'%';
GRANT SELECT ON supplychain.* TO 'supplymind_ro'@'%';
