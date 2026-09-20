# Offline Sync Foundation

MTM's offline sync and production database backups are separate systems.

- **Offline sync** moves safe, device-local changes to the production Django API after connectivity returns.
- **Database backup** copies production PostgreSQL to an independent backup or snapshot destination.

The frontend installs as a PWA and precaches only the application shell and static assets. Its service worker does not cache authenticated API responses and never stores JWTs.

## Local data isolation

IndexedDB has `offline_cache`, `sync_queue`, and `sync_metadata` stores. Every record is namespaced by the authenticated user ID and role. An explicit logout deletes that scope's cache, metadata, and queued work. If a token expires, queued work remains only in that account's scope until the same account signs in again. The server resolves the actual school from the authenticated administrator, so a client scope can never choose a tenant.

## Queue and retry policy

Each queued mutation has a client-generated UUID, module/entity/action, relative API path, method, safe payload, timestamps, retry count, status, failure category, and optional last-known version. The queue never accepts payload keys that resemble passwords, tokens, authorisation values, secrets, database URLs, or Supabase credentials.

Operations have a durable per-scope sequence and run sequentially in creation order. Connectivity combines browser online/offline events with a lightweight `/api/health/` reachability check. The app checks on browser events and once per minute while open. Network and server failures retry with exponential backoff up to five times. Authentication, permission, conflict, and validation failures become visible sync issues and require review. **Sync Now** and the issue-level Retry button perform a deliberate retry.

## Idempotency and conflicts

Inventory create operations accept a client `Idempotency-Key` UUID. Django records the completed response against the resolved school, authenticated user, method, path, and a payload hash. A retry with the same operation returns the original response, while reuse for different content returns HTTP 409. No request body is stored in the idempotency table.

Future offline-enabled updates should send the record's `updated_at` value as `lastKnownVersion`. The API should return a conflict response when that version differs, and the client must retain the failed operation for explicit review. It must never silently overwrite server changes.

## Inventory offline scope

Inventory caches categories, items, variants, recent movements, and its summary after a successful online load. Cached Inventory is clearly marked with its last synchronization time. Pending stock movements are overlaid on the last server quantity and marked provisional.

School administrators can queue stock movements for existing server-synchronized items and variants while offline. They can also queue a new category, item, and initial variants. Local records use `local:<UUID>` IDs. A completed category or item stores a local-to-server ID mapping, and dependent queued records are held until that mapping exists. The original UUID is always sent as `Idempotency-Key`.

Server-side stock validation, tenant resolution, permissions, and transaction locks remain authoritative. A rejected movement remains in the queue with a safe server message and can be retried or discarded; it is never silently removed. Existing record edits, deactivations, and destructive actions remain online-only.

Finance is deliberately online-only: payments, receipts, fees, assignments, ledger entries, expenses, reversals, and cashbook actions must never enter the sync queue.

## Attendance offline scope

Attendance stores only a selected class roster: enrollment and student display identifiers, the year, term, school-local date, and current attendance state. A whole-class save is one queued, idempotent bulk operation. The server verifies that the submission exactly matches the current active roster for that class and date, so a transferred, deactivated, or wrong-school student cannot be recorded from stale local data.

Each roster entry retains its server `updated_at` value. A reconnect that finds an attendance value changed elsewhere returns a conflict and preserves the local operation for review. The user can discard it to use the refreshed server roster. The client intentionally does not provide a blind force-overwrite action.
