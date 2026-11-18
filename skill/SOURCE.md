# Provenance of the simplification guide

- `code-simplifier.md`: unmodified copy of Anthropic's `code-simplifier` plugin agent,
  licensed under Apache License 2.0 (see `LICENSE-code-simplifier`).
  - Source: Claude Code official plugin marketplace (`claude-plugins-official`),
    `plugins/code-simplifier/agents/code-simplifier.md`
  - Plugin version 1.0.0, marketplace commit `3cd501878b8689c40e8ec7ec6059742739c7510a` (2026-11-16)
  - SHA-256 `2A51E8D210580D9F66AC2ED1226C41F9374565FC275DA30D7BB95F65C2CC87BB`
- `code-simplifier.body.md`: modified copy. The only change is that the YAML front matter was
  removed (`model: opus` is a Claude Code setting). External agents receive this file.
  The external model is chosen by the wrapper config (`setup`), not by this file.
- To refresh: copy the new upstream file over `code-simplifier.md`, regenerate the body by
  stripping the front matter, and update the commit and hash above.
