# slow-demo

Test task for Phase 7 timeout handling. Sleeps past its own timeout.

**Purpose:** prove a hung task is killed and classified as `timeout`, not left to block the pipeline.

## Inputs

JSON arg on `$1` / stdin:

| key | type | default | meaning |
|---|---|---|---|
| `sleep` | int | `30` | seconds to sleep |

## Outputs

- stdout: `slow-demo: sleeping <n>s`, then `slow-demo: done` if it survives
- exit code: `124` on timeout (matches coreutils convention)

## meta.json

`{"retries": 0, "timeout": 3}` — timeout of 3s, no retries, so the run fails fast and deterministically.