# reverse-text

Reverses the `msg` text and outputs it.

## Inputs
- `$1` JSON: `{"msg":"hello"}` (also accepts `{"text":"..."}`)
- Or plain args: `hello world`

## Outputs
- Reversed text to stdout, e.g. `olleh`

## Examples
```bash
tasks/reverse-text/run.sh '{"msg":"hello"}'  # -> olleh
tasks/reverse-text/run.sh 'hello world'      # -> dlrow olleh
tasks/reverse-text/run.sh '{"msg":""}'       # -> (empty)
```
