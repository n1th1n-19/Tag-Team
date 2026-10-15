---
name: wrestling-tag-team
description: Tag Team Wrestling for Claude accounts, using the `tagteam` CLI. Check token use (tonight, this month, career, per partner, per model, purse = API-price estimate), see which partner (saved Claude account) is worn down near its 5-hour stamina or weekly endurance limit, tag partners in and out (switch accounts), manage the roster (sign, ring name, bench, release), and control blind tags (automatic switching). Use when the user asks about token usage or cost, limits, which account to use, or to switch, add, remove accounts, or turn auto-switching on or off, or says tag in, tag out, hot tag, roster or blind tag.
---

# Tag Team Wrestling

The user's Claude accounts are a tag team. One partner is **in the ring** (the account Claude Code is using); the others wait **on the apron**. When the one inside is **worn down** (past the tag-out point, default 90% of a limit) they **tag out** to a fresh partner. `tagteam rules` prints the full glossary. Every command takes `--json`.

## Read
- `NO_COLOR=1 tagteam ring-card`: mascot, score (career tokens), roster with stamina/endurance life bars, match history heatmap, alerts.
- `tagteam state --json`: everything. Keys: `accounts[].{number,label,peakPct,nearLimit,usage}`, `tokens.totals.all.{today,month,lifetime}.{total,output,cost}`, `tokens.models`, `tokens.projects`, `alerts` (`near-limit` = TAG ME), `best`.
- `tagteam export --csv -o usage.csv`.

Token totals count input + output + cache writes + cache reads. The purse is an API-price estimate, not a bill: Pro and Max plans aren't charged per token.

## Tag
- `tagteam tag-out` hands off to the partner with the most stamina left (the hot tag); `tagteam tag-in 2` (or a ring name or email) picks one.
- A tag changes the login for every Claude Code session on this machine. Say so first if `state.sessions` shows other matches in progress.

## Roster
- Sign the current login: `tagteam sign --ring-name work`. Another account: the user runs `/login`, logs in, then `tagteam sign` again.
- Contracts (setup-tokens): the user runs `tagteam sign --contract` themselves. Never pass a token on a command line or echo it.
- `tagteam ring-name N NAME`, `bench N`, `unbench N`, `release N --yes` (confirm a release with the user first).

## Blind tag (automatic)
- `tagteam blind-tag on|off|status|preview`; `tagteam corner-man install` keeps it going with Claude Code closed.
- `tagteam blind-tag set threshold 85`, `set strategy consume-first`, `set cooldownSeconds 600`.
- `tagteam tag-out-point 85` sets when TAG ME appears.
- `tagteam update` installs the newest release (`--check` only looks); `tagteam auto-update on|off|status` checks weekly. Ask before turning auto-update on.
