# strata-mcp delegation (paste into your project AGENTS.md)

Delegate by default. `strata-mcp` (`delegate_task`) is a cheap local worker that
does the work; you plan, spec, and validate. Reach for `delegate_task` FIRST for
any bounded, checkable task — boilerplate, mechanical edits, a function from a
spec, a file transform, running tests. Do work yourself ONLY when the local
model would genuinely struggle: judgement-heavy or design decisions, long
multi-step reasoning, anything you can't check, or where writing the spec would
cost as much as doing it. "Faster to do it myself" is never a reason — time is
the cheap currency, your tokens are the expensive one. Check `list_models` to
see what is loaded; a stronger model shrinks what you keep, a weak quant grows
it. Grant `read_dirs_allowed` so the worker gathers its own context instead of
you pre-digesting it. Files: `read_dirs_allowed` / `write_dirs_allowed`
(fenced), check `files_written`. Commands: exact strings in `allowed_commands`
(menu, not shell), check `commands_run`. You set acceptance criteria; a
cross-check `delegate_task` is fine but the final judgement is yours, and never
let the worker self-validate — the quant will claim it checked when it didn't.
