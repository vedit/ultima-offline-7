# Ultima Offline 7

Play Ultima VII: The Black Gate through a modified ClassicUO desktop client. The original native U7 engine owns dialogue, schedules, inventory, combat, spell rules and saves; ClassicUO presents the world and translates input.

**Current scope:** a Windows development build of the Trinsic investigation, with Avatar creation, the Guardian dream and a player-controlled portal arrival. This is a work in progress, not a finished conversion of all Britannia.

## Install and build

You need your own **English Ultima VII: The Black Gate + Forge of Virtue** installation and **Ultima Online Classic** client data. The tested editions are Steam U7 and UO Classic 7.0.118.46. Game files, extracted art, audio, ROMs and saves are not included.

- **[Build locally](docs/build-local.md)** — dependencies, pinned checkouts, data placement, compilation, asset generation and launch.
- **[Agent-assisted installation](docs/agent-install.md)** — discovery rules and a prompt you can give your coding agent.
- **[Controls and saves](game/README.md)** — playing, resuming and making independent test runs.
- **[Roadmap](docs/roadmap.md)** · **[Rendering audit](docs/rendering-audit.md)** · **[Credits and licensing boundaries](THIRD_PARTY_NOTICES.md)**

After setup, run **Play Ultima Offline 7.cmd**. It starts a new game or resumes the current run. There is no server account to create.

## Repository layout

| Path | Purpose |
| --- | --- |
| `game/client/src` | Source overlay for a pinned ClassicUO checkout; not a standalone client tree |
| `game/native/Black Gate` | Source overlay for the pinned portable native U7 engine |
| `game/dependencies.json` | Upstream URLs, exact source revisions and tested toolchain |
| `game/atlas` | Reviewed mappings and recipes that generate art from your local games |
| `game/intro` | Dream presentation, authored head poses, local extraction and checks |
| `game/qualification` | Build scripts, launcher and focused interaction/rendering checks |
| `u7uo`, `tests` | Source readers, conversion utilities and data-free unit tests |
| `docs` | Setup, architecture, roadmap and retained development evidence |

The older ModernUO conversion is retained for reference; it is **not required** to build or play this client. Its machine-specific workflow is in [archived notes](docs/archive/modernuo-notes.md). Historical receipts describe their recorded builds, not a guarantee that every check can run without the maintainer's private fixtures.

## Contributing

Read [AGENTS.md](AGENTS.md) and, for artwork, [art direction](docs/art-direction.md). Keep U7 gameplay authoritative. Fix general conversion rules where possible, and keep presentation changes separate from native game logic.

Keep installations, generated retail assets, saves and build output outside the repository. Do not force-add ignored files. This repository preserves upstream notices; it does not grant rights to distribute Ultima game data.
