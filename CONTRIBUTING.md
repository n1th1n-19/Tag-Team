# Contributing to Tag Team

Thanks for stepping into the ring. Bug reports, fixes, new moves and better pixel art are all welcome.

By taking part you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Found a security problem? Don't open an issue; follow [SECURITY.md](SECURITY.md).

## Before you start

- **Bugs:** open an issue with your OS, `tagteam --version`, `cswap --version`, what you ran and what happened. Leave out emails, org names, account UUIDs and tokens; `tagteam state` output contains them.
- **Features:** open an issue first so we can agree on the shape before you build it.
- **Small fixes** (typos, docs, an obvious bug): just send the PR.

## Set up

You need [uv](https://docs.astral.sh/uv/), [Claude Code](https://claude.com/claude-code), and Node.js 20 if you're building the editor extension.

```bash
git clone https://github.com/n1th1n-19/Tag-Team && cd Tag-Team
uv run --python 3.12 --with claude-swap python tests/test_tagteam.py   # Python tests
claude plugin validate plugin && claude plugin test plugin             # plugin checks
claude --plugin-dir plugin                                             # Claude Code with your working copy
uv run --python 3.12 --with claude-swap python -m tagteam ring        # the ring in your browser
python scripts/package.py                                              # zips + tag-team.vsix (needs Node)
```

To try the editor extension, install `dist/tag-team.vsix` with *Extensions: Install from VSIX…*.

## Where things live

| Change | Files |
|---|---|
| Token counting, ledger, history | `tagteam/tokens.py`, `tagteam/store.py` |
| Switching, roster, blind tag, corner man | `tagteam/accounts.py` (all calls to claude-swap go through here) |
| Terminal commands | `tagteam/cli.py` |
| The ring page | `tagteam/web/index.html`, served by `tagteam/server.py` |
| Claude Code plugin | `plugin/hooks/register.tsx`, `plugin/commands/`, `plugin/skills/` |
| Editor extension | `vscode/extension.js`, `vscode/package.json` |
| Installers | `install/` |
| Releases | `scripts/package.py`, `.github/workflows/release.yml` |

The snapshot from `tagteam state` is the contract between the Python side and both UIs. If you change its shape, update `plugin/types/index.d.ts` and the extension too.

## House rules

- **Stdlib only** in the `tagteam` package. claude-swap is the one dependency; adding another needs a very good reason.
- **Comments:** one line, and only where the code can't say it itself.
- **Wrestling words, not trademarks.** Use the generic tag-team vocabulary in `tagteam/rules.py` (tag in, apron, stamina, blind tag…). No promotion, show or wrestler names, and no lookalike logos.
- **Pixel art comes from Figma.** `tagteam/web/mascot.js` is an export; don't hand-edit the frames. See *Design* in the README.
- **No personal data** in tests, fixtures or screenshots: no real emails, org names, UUIDs or tokens.
- **Security:** tokens go to claude-swap on stdin, never in argv. Programs run by absolute path, never from the current folder. The ring server stays on 127.0.0.1 behind its token. Keep it that way, and add a test when you touch any of it.
- **Cross-platform:** anything touching paths, processes or services has to work on macOS, Linux and Windows. CI checks all three.

## Pull requests

1. Branch from `master` and keep the PR to one change.
2. Add or update a test for any behavior change (`tests/test_tagteam.py` or `plugin/tests/`).
3. Use [Conventional Commits](https://www.conventionalcommits.org) titles: `fix:`, `feat:`, `docs:`, `ci:`, `test:`, `chore:`.
4. Update the README if a command, setting or install step changes.

`master` is protected. A PR merges once all 7 checks pass: tests and a real install-and-uninstall on macOS, Linux and Windows, plus the build. PRs are squash-merged.

Releases are cut by the maintainer: the steps are under *Develop* in the README.
