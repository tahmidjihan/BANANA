# echo-demo

Simple echo task for Phase 4 testing.

Inputs:
- `msg` (string) — text to echo, or any args string. Passed as `ARGS` JSON or CLI args.

Outputs:
- `stdout`: `echo-demo: <msg>`
- `stderr`: JSON `{"task":"echo-demo","input":"..."}`

Run:
```bash
bash tasks/echo-demo/run.sh "hello"
bash tasks/echo-demo/run.sh '{"msg":"hello"}'
python -m src.action --task echo-demo --args '{"msg":"hi"}'
```
