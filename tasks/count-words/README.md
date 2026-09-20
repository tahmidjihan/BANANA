# count-words

Counts words in `msg` and outputs the count.

## Inputs
- `$1` JSON: `{"msg":"hello world"}` (also accepts `{"text":"..."}`)
- Or plain args: `hello world foo`

## Outputs
- Word count to stdout (integer), e.g. `2`
- Empty/whitespace-only input outputs `0`

## Examples
```bash
tasks/count-words/run.sh '{"msg":"hello world"}'  # -> 2
tasks/count-words/run.sh 'hello world foo'        # -> 3
tasks/count-words/run.sh '{"msg":""}'             # -> 0
```
