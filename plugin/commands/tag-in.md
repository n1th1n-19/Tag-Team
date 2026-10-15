---
description: Tag a partner into the ring (switch Claude account). Number, ring name, email, or "best"
argument-hint: "[best|N|ring name]"
allowed-tools: Bash(tagteam tag-in:*)
---
The user wants to tag a partner into the ring. Requested partner: "$ARGUMENTS" (empty means "best").

Only if it is empty, `best`, a number, a ring name or an email (letters, digits and `@ . _ + -` only), run `tagteam tag-in <partner>` with the Bash tool, passing it as a single argument. Otherwise don't run anything; ask the user which partner they meant.

Then tell the user in one line who is in the ring now. Running Claude Code sessions use the new partner from their next request.
