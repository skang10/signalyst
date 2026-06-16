# Self-Healing Seed Data (Upsert) Design

## Background

`seed_profiles()` and `seed_connectors()` (`backend/src/db/seed.py`) are insert-only:
they only write a row if `db.get(Model, id)` returns `None`. Both run on every backend
startup (`api/main.py` lifespan) and in test setup (`tests/conftest.py`).

This caused a real bug: the local dev DB's `oil` `MarketProfile` row was created before
`regime_thresholds`, `primary_ticker`, and `default_connector_params` were added to
`seed.py`. Because the row already existed, those fields were never backfilled and
stayed at their column defaults (`{}` / `""`), which silently broke regime/direction
inference and data-source fetching for the `oil` profile.

## Scope

Convert `seed_profiles()` and `seed_connectors()` from insert-only to upsert, so
`seed.py` is the single source of truth and existing rows self-heal on the next
restart whenever `seed.py` changes.

## Behavior

For each item in `_build_profiles()` / `_BUILTIN_CONNECTOR_SPECS`:

- If no row exists for that `id` → insert (unchanged from today).
- If a row exists → update specific fields to match the in-code definition.

### `MarketProfile` (all fields except `id`)

Update: `name`, `description`, `default_connectors`, `default_connector_params`,
`default_featurizer_config`, `regime_labels`, `regime_thresholds`, `primary_ticker`.

There is no edit API for `MarketProfile` (`api/routes/profiles.py` is read-only), so
there is no user-entered data on these rows that an upsert could clobber.

### `Connector` (only the 4 builtin ids in `_BUILTIN_CONNECTOR_SPECS`)

Update: `name`, `description`, `type`.

Leave `spec`, `code`, `tests`, `is_active`, `created_at` untouched. These fields are
used by user-created custom connectors (`ConnectorType.SPEC`, created via
`POST /api/connectors`) and are not set by `_BUILTIN_CONNECTOR_SPECS`. Updating only
the three fields above avoids touching them even in the unlikely case a row's `id`
collides.

## Out of Scope

- Deleting profiles/connectors that are removed from the seed definitions in the
  future — none currently are, and adding deletion logic now would be speculative and
  risks deleting user-created custom connectors on an id collision.
- Any change to the data-agent caching behavior (tracked separately).

## Testing

For both `seed_profiles` and `seed_connectors`, add a test that:

1. Pre-inserts a row for an id that `seed.py` also defines, with field values that
   differ from the seed definition (simulating a stale row).
2. Runs the seed function.
3. Asserts the row's fields now match the seed definition (for `Connector`, only the
   three updated fields; `is_active`/`spec`/etc. are asserted unchanged).

The existing insert-path behavior (seeding into an empty table) continues to be
covered by the current test setup in `tests/conftest.py`.
