# strata-mcp delegation (paste into your project AGENTS.md)

`strata-mcp` is a cheap local worker (`delegate_task`). Prefer it for bounded,
well-specified grunt work — boilerplate, mechanical edits, a self-contained
function, a file transform — instead of spending your own context. Set
acceptance criteria, let it work, then decide whether to accept; validate
however you like, including a second `delegate_task`. For files, grant
`read_dirs_allowed` / `write_dirs_allowed` (fenced) and check `files_written`.
Don't delegate judgement-heavy work, or anything you couldn't check.
