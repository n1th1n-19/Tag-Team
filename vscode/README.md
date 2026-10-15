# Tag Team Wrestling for VS Code and VSCodium

If you have more than one Claude account (say, work and personal), they're a tag team. One partner is **in the ring** (the account Claude Code is using); the rest wait **on the apron**. See each one's stamina at a glance and **tag** the right one in with one click.

- **Status bar**: `[IN] work ▮▮▮▯▯ 41%`, the partner in the ring and their 5-hour stamina. Hover for the whole roster.
- **TAG ME**: when the partner in the ring reaches the tag-out point (90% by default) the status bar turns into a red **TAG ME** button (one click hands off to the freshest partner) and a notification offers *TAG ME > partner*, *Hot tag: best* and *Open the ring*. It asks again at 100% (*down for the count*).
- **The ring** (click the status bar, or *Tag Team: Open the ring*): a retro pixel-art dashboard with every partner's stamina and endurance life bars, an arcade score of your career tokens, a year of match history, the roster and blind tags.
- **Tag in**: *Tag Team: Tag a partner in…* (`Ctrl+Alt+T`, `Cmd+Alt+T` on macOS).
- **Blind tag**: switches automatically to the partner with the most stamina left (off unless you turn it on), set up from the ring.

Needs the `tagteam` command, which the Tag Team installer sets up: https://github.com/n1th1n-19/tag-team

Tag Team uses generic wrestling words; it isn't affiliated with any wrestling company or with Anthropic.
