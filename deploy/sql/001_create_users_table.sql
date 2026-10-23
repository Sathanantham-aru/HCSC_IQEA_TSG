-- IQEA — Azure MySQL — login accounts table.
--
-- Source of truth is utilities/db_utils/models.py::User. This file is the
-- exact DDL MySQL generates from that model (verified locally via
-- `SHOW CREATE TABLE users` after running bootstrap_db.py against the local
-- database), for anyone who would rather run SQL directly than run the
-- Python bootstrap script against Azure.
--
-- Safe to re-run: IF NOT EXISTS means running this twice does nothing the
-- second time. It does NOT alter an existing table — if the columns below
-- ever need to change later, that will be a separate ALTER script, never
-- this file edited in place.
--
-- No other table needs a change for this step. (A later step — adding an
-- `owner` column to `iqea_artifacts` for per-user save collisions — will
-- ship as its own ALTER script when that work starts; nothing to run for
-- it yet.)
--
-- Before running: connect to the iqea_azure database itself, e.g.
--     USE iqea_azure;
-- then run everything below.

CREATE TABLE IF NOT EXISTS `users` (
  `id`            INT NOT NULL AUTO_INCREMENT,
  `username`      VARCHAR(255) NOT NULL,
  `password_hash` VARCHAR(255) NOT NULL,
  `display_name`  VARCHAR(150) DEFAULT NULL,
  `role`          VARCHAR(32)  NOT NULL,       -- 'tester' | 'admin'
  `is_active`     TINYINT(1)   NOT NULL,
  `created_on`    DATETIME DEFAULT (NOW()),
  `created_by`    VARCHAR(255) DEFAULT NULL,   -- username of whoever created this account
  `last_login`    DATETIME DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

-- Verify afterwards:
--     DESCRIBE users;
--     SELECT COUNT(*) FROM users;   -- expect 0 on a fresh run
--
-- Nothing further to seed here — IQEA's login screen creates the first
-- admin account itself the first time anyone opens the app against an
-- empty `users` table.
