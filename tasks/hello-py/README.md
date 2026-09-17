# hello-py

Python demo task.

Inputs:
- `msg` (string) JSON `{"msg":"hello"}` or plain text via CLI arg.

Outputs:
- `stdout`: `hello-py: <msg> — from python task`
- `stderr`: JSON

Run:
```bash
python tasks/hello-py/run.py '{"msg":"hello"}'
python -m src.action --task hello-py --args '{"msg":"hi"}'
```
