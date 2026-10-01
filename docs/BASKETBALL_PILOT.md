# Basketball Pilot Capability Audit

This branch is isolated from the Baseball production service. Railway Baseball remains on `main`.

## Goal

Before building QuantBet Basketball, verify with a small number of API-Sports requests:

1. available basketball leagues;
2. historical game score shape, especially Q1/Q2/Q3/Q4 splits;
3. pre-match odds inventory;
4. whether FT, HT, Q1, Q2, Q3 and Q4 total markets are actually exposed;
5. which leagues/bookmakers can support the full pilot coverage.

## Run

The probe accepts either `API_BASKETBALL_KEY` or the existing `API_BASEBALL_KEY`, because API-Sports uses the same `x-apisports-key` authentication pattern.

```bash
BASKETBALL_AUDIT_MAX_REQUESTS=12 python scripts/basketball_capability_probe.py
```

Default endpoint:

```
https://v1.basketball.api-sports.io
```

The probe is intentionally capped at 12 requests and prints only compact capability summaries.

## Safety

- no database writes;
- no picks;
- no production deployment required;
- no live analysis;
- no recurring polling;
- no changes to Baseball `main`.
