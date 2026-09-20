# count-words

Counts words in `msg`.

Inputs:
- `msg` (string) — text to count, passed as `ARGS` JSON `{"msg":"..."}` or plain CLI args. `text` also accepted as alias.

Outputs:
- `stdout`: word count as integer (e.g. `2`)

Run:
```bash
bash tasks/count-words/run.sh '{"msg":"hello world"}'
bash tasks/count-words/run.sh "hello world"
python -m src.action --task count-words --args '{"msg":"hi"}'
```
