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
- Detection-only references needed by migration audits must carry
  `agent-plugins: allow-claude-reference` on the same line. The marker never
  permits executing or depending on the referenced Claude runtime surface.
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
python3 -m unittest tests/test_check_structure.py -v
```

Validate Grok manifests with its native validator when changing plugin
metadata:

```bash
grok plugin validate plugins/<plugin>
```

The repository structure check validates the Codex manifest contract and
marketplace relationships. For ingestion-sensitive Codex changes, also
register the checkout in an isolated `CODEX_HOME` and confirm that
`codex plugin marketplace list --json` discovers `gering-agent-plugins`.

Do not run deployment commands or mutating fixture tests against external
projects. The initial `muellmann-app.de` fixture is read-only.
