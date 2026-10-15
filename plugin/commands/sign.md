---
description: Sign partners to the roster (save the current login), give ring names, bench or release partners
argument-hint: "[sign [ring name]|ring-name N NAME|bench N|unbench N|release N]"
allowed-tools: Bash(tagteam sign:*), Bash(tagteam ring-name:*), Bash(tagteam bench:*), Bash(tagteam unbench:*), Bash(tagteam release:*), Bash(tagteam ring-card:*)
---
The user wants to manage their tag-team roster (their saved Claude accounts). Arguments: "$ARGUMENTS".

- No arguments: run `NO_COLOR=1 tagteam ring-card` and walk them through the pre-match checklist: sign the current login with `tagteam sign --ring-name NAME`; for another account they run `/login`, log in, and sign again.
- `sign [name]`: run `tagteam sign` (with `--ring-name` if given).
- `ring-name N NAME`, `bench N`, `unbench N`: run the matching `tagteam` command.
- `release N`: confirm with the user first, then `tagteam release N --yes`.
- Contracts (tokens): never put one on a command line. Tell the user to run `tagteam sign --contract` in their own terminal, where it's read hidden.
