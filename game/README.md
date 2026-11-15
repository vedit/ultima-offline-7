# Playing and developing Ultima Offline 7

For a first installation, follow [Build locally](../docs/build-local.md). This directory contains source overlays, not complete upstream checkouts. The default private installation is `%LOCALAPPDATA%\UltimaOffline7`; set `ULTIMA_OFFLINE_HOME` to choose another location.

## Play

Run **Play Ultima Offline 7.cmd** at the repository root. A new run asks for your name and Avatar, plays the Guardian dream, then lets you walk into the red portal to arrive outside the Trinsic stables. A saved run skips setup and resumes its world.

| Input | Action |
| --- | --- |
| Right mouse button / arrow keys | Move |
| Single-click | Name or quantity |
| Double-click | Use an item or talk to someone; companions also expose their paperdoll |
| Drag | Move items between world, containers, backpack and equipment |
| F2 / F3 / F4 | Paperdoll / backpack / map |
| F5 | Save the current native world |
| Tab | War / peace |
| Space / Escape during the dream | Pause / wake; you still walk to the portal |

The backpack contains a [Developer's Wand](developer-wand.md). Pass `--no-debug` to disable it. Ordinary U7 spell and inventory rules still apply.

## Saves and independent runs

In PowerShell from the repository root:

```powershell
& '.\Play Ultima Offline 7.cmd' --run my-playtest
& '.\Play Ultima Offline 7.cmd' --run my-playtest --test-copy spell-testing
& '.\Play Ultima Offline 7.cmd' --run spell-testing
```

Save with F5 before making a test copy. The copy operation refuses an existing destination. It copies the selected saved checkpoint, not unsaved live progress.

The default run is `player-trinsic-opening`. Runs live under:

```text
<ULTIMA_OFFLINE_HOME>/PoCs/ClassicUO-U7-Local/runs/<run-name>/
```

`GAME00.U7` through `GAME09.U7` are native save slots; `active-slot.txt` selects the current slot. Back up the whole run folder after closing its game. Do not start two clients against one run. Use another `--run` for experiments instead of deleting or resetting your playthrough.

**Play Ultima Offline 7 Intro.cmd** is an alias with its own `player-dream-intro` run. **Play Trinsic Playtest.cmd** is a maintainer-only launcher for an old frozen local package; that package is not distributed here.

## Verification

The [build guide](../docs/build-local.md#verify-the-installation) separates data-free unit tests from local-data checks. Many older qualification scripts require private DOS reference saves; those are neither installation prerequisites nor included downloads.

The atlas generates the reviewed Trinsic mapping and stock-derived rake locally. Parallel art candidates and private comparison builds are not part of the published source baseline.
