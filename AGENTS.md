# Repository guidance

This repository ships native Codex and Grok plugins. Claude Code remains in
the sibling `gering/claude-plugins` repository and is a behavioral reference,
not a runtime distributed here.

## Working rules

- Read `TASK.md` and `docs/architecture.md` before changing architecture or
  porting a plugin.
- Keep shared workflow semantics agent-neutral. Put launch, resume, prompt,
  manifest, installation, and tool behavior in the relevant runtime adapter.
- Do not use `${CLAUDE_PLUGIN_ROOT}`, Claude-only tool names, or Claude session
  commands in Codex or Grok adapters.
- Do not edit the sibling `claude-plugins` checkout from this repository.
- Treat a dirty upstream Claude worktree as excluded unless the user explicitly
  authorizes importing uncommitted changes.
- Preserve existing project knowledge and worktrees. Adoption and migration
  workflows are read-only by default.
- Update `docs/parity.md` and `.agents/upstream/claude-plugins.json` only after
  the corresponding validation succeeds.
- Never claim parity because files were copied. Require mapped behavior,
  documented differences, and runtime evidence.

## Validation

Run the deterministic foundation check after structural changes:

```bash
python3 scripts/check-structure.py
```

Validate every Codex and Grok manifest when changing plugin metadata:

```bash
python3 /path/to/plugin-creator/scripts/validate_plugin.py plugins/<plugin>
grok plugin validate plugins/<plugin>
```

Do not run deployment commands or mutating fixture tests against external
projects. The initial `muellmann-app.de` fixture is read-only.
