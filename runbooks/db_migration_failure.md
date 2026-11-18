# Runbook: Database migration failure

**Applies to:** SQL errors right after a deploy, such as `column ... does not exist`
(SQLSTATE 42703), `relation ... does not exist` (42P01) or not-null violations (23502).

## 1. Confirm
- Find the first SQL error and the deploy just before it. Check the startup logs for a migration.
- Note which endpoints fail. Schema errors fail fast and only on the code paths that touch the
  changed table. Reads that do not use it keep working.

## 2. Decide how to restore service
- **Destructive migrations (drop or rename) do not roll back with the code.** If the previous
  version also uses what was dropped, a code rollback fails the same way.
- Restore the schema first: re-add the column (or revert the migration), then roll back the code
  if needed. Never delete data to make errors go away.

## 3. Mitigate
- Re-add the dropped column with a default and backfill later, or revert the migration.
- Pause further deploys of the service until the fix is out.

## 4. Follow up
- Use expand/contract: add new columns first, ship code that stops using the old one, and drop it
  in a later release once nothing reads or writes it.
- Add a check in CI that runs the previous release's queries against the new schema.
