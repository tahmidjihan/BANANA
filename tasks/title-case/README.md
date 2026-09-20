# title-case

Converts `msg` to title case.

Inputs:
- `msg` (string) — text to convert, passed as `ARGS` JSON `{"msg":"..."}` or plain CLI args. `text` also accepted as alias.

Outputs:
- `stdout`: title-cased text (e.g. `Hello World`)

Run:
```bash
bash tasks/title-case/run.sh '{"msg":"hello world"}'
bash tasks/title-case/run.sh "hello world"
python -m src.action --task title-case --args '{"msg":"hi"}'
```
