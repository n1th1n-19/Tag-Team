# Security

Tag Team handles Claude Code login tokens (through claude-swap), runs a local web server, and ships installers people pipe into a shell, so security reports are welcome.

## Reporting a vulnerability

Please **don't open a public issue**. Report it privately through [GitHub's private vulnerability reporting](https://github.com/n1th1n-19/Tag-Team/security/advisories/new). Include what you found, how to reproduce it, and what an attacker could do with it.

You'll get a reply within a week. Fixes ship as a new release, and the advisory is published once people can update.

## Supported versions

Only the latest release gets fixes. Update with the one-line installer from the [README](README.md#download-and-install).

## In scope

- the `tagteam` CLI and the local ring server (`tagteam ring`)
- the Claude Code plugin and the VS Code / VSCodium extension
- the installers (`install.sh`, `install.ps1`, `get.sh`, `get.ps1`) and the release pipeline

Bugs in claude-swap itself belong upstream at [realiti4/claude-swap](https://github.com/realiti4/claude-swap).
