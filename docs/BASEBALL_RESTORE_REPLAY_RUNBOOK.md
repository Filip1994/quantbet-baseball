# Baseball restore, replay and operational acceptance runbook

**Scope:** QuantBet Baseball only. Railway project `believable-contentment`.

## Canonical stores

Operational truth is reconstructed from:

1. PostgreSQL migrations and immutable canonical facts;
2. Railway object storage raw API envelopes;
3. source code from the Baseball GitHub repository.

Generated Git JSON files are not an operational dependency.

## Restore procedure

1. Provision a clean PostgreSQL target.
2. Restore the PostgreSQL backup/snapshot.
3. Deploy the exact Baseball application revision associated with the backup.
4. Run `apply_migrations`; migrations are idempotent and forward-only.
5. Confirm the Railway raw bucket configuration points at the preserved Baseball bucket.
6. Run:

   ```bash
   PYTHONPATH=src python scripts/baseball_operational_snapshot.py
   ```

7. Compare canonical counts and lifecycle integrity:
   - fixtures / fixture observations;
   - moneyline observations;
   - registered picks;
   - closing finalizations;
   - result facts;
   - settlements;
   - CLV availability;
   - zero provenance anomalies.
8. Re-run the operational snapshot from a fresh process. Dashboard and bulletin output must be rebuilt from PostgreSQL without any Git-generated scheduler/dashboard state.

## Raw archive verification

A controlled canary performs synchronous S3-compatible writes and then reads a bounded sample back from the bucket. Every sampled object's SHA-256 must equal the checksum stored in canonical PostgreSQL evidence.

A canary is accepted only when:

- collection status is `collected`;
- API requests remain within the explicit canary limit;
- fixture rows are written;
- moneyline rows are written;
- collection errors are zero;
- at least one raw object is read back successfully;
- raw-object checksum failures are zero.

## Activation gate

Scheduled collection remains disabled until the DB-backed operational acceptance report is `READY`.

The gate is fail-closed and requires:

- `PAPER_MODE=true`;
- daily-derived API request budget is safe;
- Railway runtime telemetry exists;
- canonical fixture evidence exists;
- canonical moneyline evidence exists;
- all operational evidence uses remote archive provenance;
- provenance integrity anomalies are zero;
- downstream closing/settlement schema is coherent;
- a bounded controlled canary has passed.

A healthy Railway deployment by itself is not authorization to enable collection.

## Canary execution

Canary execution is intentionally armed separately from scheduled collection.

```bash
BASEBALL_ALLOW_CANARY=true \
PYTHONPATH=src python scripts/baseball_collection_canary.py
```

The default canary is bounded to 12 physical API attempts and at most 4 broad odds requests. Retry attempts count against the physical request limit.

Do not set `BASEBALL_ENABLE_COLLECTION=true` as part of the canary.

## Failure response

If any acceptance criterion is blocked:

1. leave scheduled collection disabled;
2. inspect the DB-backed dashboard alert and criterion detail;
3. correct the underlying evidence/runtime issue;
4. repeat the bounded canary if the failure involved collection/archive evidence;
5. record a fresh acceptance report before activation.
