# strata-mcp delegation (paste into your project AGENTS.md)

Delegate by default. `strata-mcp` (`delegate_task`) is a cheap local worker that
does the work; you plan, spec, and validate. Your output tokens are what the
user pays; the worker is free, so minimise your output. Delegate anything
bounded, whether you'd produce it (code from a spec, edits, transforms,
boilerplate, checks) or ingest it (reviewing, auditing, summarising, searching) —
ingestion costs the context you read, which the worker reads for nothing. If you
catch yourself producing or reading such work directly, stop and hand it over.
Do it yourself ONLY when delegating costs MORE than it saves: judgement or design
calls, work you cannot check, or a spec as costly to write as the work — because
then you pay to spec it and pay again to redo a wrong result. A task is not yours
because its hardest part is judgement: decompose it, delegate the mechanical
parts (gather, lint, list, extract), keep only the uncheckable call. Never
pre-digest and forward a summary; grant `read_dirs_allowed` and let the worker
read its own context. Fence tight — narrowest `read_dirs_allowed` /
`write_dirs_allowed`, `allowed_commands` an exact menu not a shell — and make the
worker prove its own output by running the tests/linters/typecheck from that
menu; read `commands_run` and `files_written` for pass/fail, not the diff,
reading full output only when nothing is checkable. On a block or reject, do not
take the work back by reflex: re-delegate with a widened fence (add the suggested
command, grant the needed dir) or a bounded diagnosis task ("find why X fails") —
diagnosis delegates too. Step in only for what no fence can reach (network,
secrets the scrubbed env lacks), and open only as narrowly as the fix needs. Let
the worker reason by default; Before setting a level, call `list_models` and pick `reasoning_effort` from the
chosen model's advertised `reasoning_levels`; for mechanical one-shape tasks
(rename, reformat, find-replace) use the smallest level, or omit it entirely.
When unsure leave thinking on, since needless thinking is merely slow but missing
thinking is a wrong answer you pay to fix. Check `list_models`: a stronger model
lets you spec looser and keep less.
Final judgement is yours; never trust the worker's self-reported status — the
quant will claim it checked when it didn't.
