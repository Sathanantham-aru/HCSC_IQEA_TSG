-- IQEA — Azure MySQL — per-owner uniqueness on the legacy artifact tables.
--
-- What this fixes: two testers saving a workflow under the same name (e.g.
-- both call it "login_flow") used to silently shadow each other — every
-- name-based lookup picked whichever row had the highest id, REGARDLESS of
-- who saved it, so the other tester's version became unreachable. The app
-- side of this fix already shipped (handler.py's get_all_*_names /
-- get_*_content_by_name now filter by owner, and save_*_to_db now updates a
-- matching (name, owner) row in place instead of appending a duplicate).
-- This script adds the matching DB-level constraint as the backstop: the
-- same tester resaving "login_flow" a second time still works (their own row
-- gets updated), but two DIFFERENT testers can each have their own
-- "login_flow" without either one colliding with the other.
--
-- IDEMPOTENT — safe to run this whole file as many times as you like. Each
-- ALTER below is guarded by a check against INFORMATION_SCHEMA first, so a
-- constraint that already exists (from an earlier partial run — this is
-- exactly what produced "Duplicate key name 'uq_action_name_owner'" the
-- first time this ran) is silently skipped instead of erroring. Plain
-- `ALTER TABLE ... ADD CONSTRAINT` has no built-in IF NOT EXISTS in MySQL,
-- which is why v1 of this file didn't have this guard.
--
-- IMPORTANT — run STEP 1 first. Every row in these tables today was saved
-- before real logins existed, when created_by held the DATABASE ROLE NAME
-- for every row (see utilities/identity.py's history) — so it is possible,
-- though unlikely given the row counts involved, that two OLD rows share
-- both the same name AND the same created_by value. If so, the matching
-- ALTER in STEP 2 will fail with a duplicate-ENTRY error (not the
-- duplicate-KEY-NAME error you just saw — that one was harmless) — that
-- failure is doing its job. Resolve it by renaming/deleting the older
-- duplicate before re-running STEP 2 for that table.
--
-- Before running: USE iqea_azure;


-- ── STEP 0 — see what's already there, given the error you just hit ──
-- Lists every one of the 5 target constraints that currently exists. Cross-
-- reference against the 5 names below (uq_action_name_owner,
-- uq_pagefile_name_owner, uq_testcase_name_owner, uq_testfile_name_owner,
-- uq_featurefile_name_owner) — anything NOT listed here is still pending.
-- Purely informational; STEP 2 below handles the skip/apply logic itself.

SELECT TABLE_NAME, CONSTRAINT_NAME
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
  AND CONSTRAINT_NAME IN (
    'uq_action_name_owner', 'uq_pagefile_name_owner', 'uq_testcase_name_owner',
    'uq_testfile_name_owner', 'uq_featurefile_name_owner'
  );


-- ── STEP 1 — check for conflicts, per table. Expect 0 rows from ALL FIVE. ──
-- If any of these return rows, STEP 2's ALTER for that table will fail with
-- a duplicate-ENTRY error (not the key-name error) — resolve the listed rows
-- first (keep the newest, rename or delete the older one) before retrying.

SELECT action_name, created_by, COUNT(*) AS c
FROM actions GROUP BY action_name, created_by HAVING c > 1;

SELECT pagefile_name, created_by, COUNT(*) AS c
FROM pagefile GROUP BY pagefile_name, created_by HAVING c > 1;

SELECT testcase_name, created_by, COUNT(*) AS c
FROM testcase GROUP BY testcase_name, created_by HAVING c > 1;

SELECT testfile_name, created_by, COUNT(*) AS c
FROM testfile GROUP BY testfile_name, created_by HAVING c > 1;

SELECT featurefile_name, created_by, COUNT(*) AS c
FROM featurefile GROUP BY featurefile_name, created_by HAVING c > 1;


-- ── STEP 2 — add the constraints. Safe to re-run: each block skips itself ──
-- if the constraint is already there. Run all five statements below in one
-- go; whichever ones are pending get added, whichever already exist print a
-- "skipping" notice and do nothing.

SET @exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                 WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'actions'
                   AND CONSTRAINT_NAME = 'uq_action_name_owner');
SET @sql := IF(@exists = 0,
    'ALTER TABLE actions ADD CONSTRAINT uq_action_name_owner UNIQUE (action_name, created_by)',
    'SELECT ''uq_action_name_owner already exists on actions, skipping'' AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                 WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'pagefile'
                   AND CONSTRAINT_NAME = 'uq_pagefile_name_owner');
SET @sql := IF(@exists = 0,
    'ALTER TABLE pagefile ADD CONSTRAINT uq_pagefile_name_owner UNIQUE (pagefile_name, created_by)',
    'SELECT ''uq_pagefile_name_owner already exists on pagefile, skipping'' AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                 WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'testcase'
                   AND CONSTRAINT_NAME = 'uq_testcase_name_owner');
SET @sql := IF(@exists = 0,
    'ALTER TABLE testcase ADD CONSTRAINT uq_testcase_name_owner UNIQUE (testcase_name, created_by)',
    'SELECT ''uq_testcase_name_owner already exists on testcase, skipping'' AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                 WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'testfile'
                   AND CONSTRAINT_NAME = 'uq_testfile_name_owner');
SET @sql := IF(@exists = 0,
    'ALTER TABLE testfile ADD CONSTRAINT uq_testfile_name_owner UNIQUE (testfile_name, created_by)',
    'SELECT ''uq_testfile_name_owner already exists on testfile, skipping'' AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @exists := (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
                 WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'featurefile'
                   AND CONSTRAINT_NAME = 'uq_featurefile_name_owner');
SET @sql := IF(@exists = 0,
    'ALTER TABLE featurefile ADD CONSTRAINT uq_featurefile_name_owner UNIQUE (featurefile_name, created_by)',
    'SELECT ''uq_featurefile_name_owner already exists on featurefile, skipping'' AS note');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;


-- ── Verify afterwards ──
--     SHOW CREATE TABLE actions;      -- look for uq_action_name_owner in the output
--     SHOW CREATE TABLE pagefile;
--     SHOW CREATE TABLE testcase;
--     SHOW CREATE TABLE testfile;
--     SHOW CREATE TABLE featurefile;
--
-- Not touched by this script, deliberately: `screenshot`. Screenshots
-- legitimately accumulate many rows under the same page_name as a recording
-- progresses — that is the intended behaviour, not a collision, so it gets
-- no uniqueness constraint.
