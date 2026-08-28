# Database migrations

Alembic owns the schema. `Base.metadata.create_all()` is never called anywhere
in this codebase — every schema change, without exception, ships as a migration.

All commands are run from `backend/` with the virtual environment active.

## Everyday commands

```bash
alembic upgrade head                       # apply all pending migrations
alembic current                            # show the applied revision
alembic history --verbose                  # list the migration chain
alembic downgrade -1                       # roll back one revision
alembic upgrade head --sql > upgrade.sql   # emit SQL without connecting (DBA review)
```

## Adding a schema change

1. Edit or add the model under `app/models/`.
2. Export it from `app/models/__init__.py` so `app/db/base.py` registers it.
3. Autogenerate the revision:

   ```bash
   alembic revision --autogenerate -m "add employees table"
   ```

4. **Read the generated file.** Autogenerate is a first draft, not an oracle. It
   reliably misses:
   - table and column renames (it emits a drop plus an add — which destroys data),
   - `CHECK` constraints and partial indexes,
   - server-side defaults that need backfilling,
   - any data migration the schema change implies.
5. Confirm `downgrade()` actually reverses `upgrade()`.
6. Apply and verify:

   ```bash
   alembic upgrade head
   alembic downgrade -1 && alembic upgrade head   # prove the migration round-trips
   ```

## Conventions
- **Naming.** `app/db/base_class.py` sets a metadata naming convention, so every
  index and constraint has a deterministic name. Never rely on an auto-generated
  anonymous constraint name — it cannot be dropped reliably in a downgrade.
- **Additive first.** In production, prefer expand → migrate → contract: add the
  new column nullable, backfill it, then make it `NOT NULL` in a later release.
  A single migration that adds a `NOT NULL` column to a populated table will fail.
- **One concern per revision.** Small revisions are far easier to roll back.
