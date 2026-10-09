# fail-demo

Test task for Phase 7 failure handling. Always exits non-zero.

**Purpose:** prove retry, error classification, and the run log work.

## Inputs

JSON arg on `$1` / stdin:

| key | type | default | meaning |
|---|---|---|---|
| `code` | int | `1` | exit code to fail with |

## Outputs

- stdout: nothing
- stderr: `fail-demo: failing on purpose with exit code <code>`
- exit code: `code`

## meta.json

`{"retries": 2, "timeout": 10}` — retried twice, so a run takes 3 attempts.