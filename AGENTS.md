# Working on Ultima Offline 7

## Installation requests

Read `README.md`, `docs/agent-install.md`, `docs/build-local.md` and `game/dependencies.json` before installing or building.

- Inspect existing tools and game installations first. Ask only for missing information that cannot be discovered locally.
- Use a private `ULTIMA_OFFLINE_HOME` outside this checkout. Preserve the original games and existing saves.
- Pin upstream sources exactly, initialize ClassicUO submodules, then overlay this repository's files. Never substitute upstream HEAD silently.
- The native portable Black Gate engine is the gameplay authority. Do not replace it with Exult, ModernUO, `ultima7-modern`, or a fabricated starter save.
- Fetch tools and open-source dependencies from their official upstreams. Retail game data and optional music/ROMs must come from the player's own installations; do not search for mirrors of them.
- Complete verification before claiming success. Report exact commands, versions, input editions, generated outputs, run name and any checks not performed.
- Do not commit game data, generated retail art/audio, saves, binaries, credentials or machine paths. Do not force-add ignored outputs.

The user-authorized public website is a separate exception for the project homepage, selected gameplay screenshots, review HTML and PNG/WebP comparisons on the `gh-pages` branch. Use `game/atlas/publish_site.py` and [the publishing notes](docs/atlas-site.md). Reconcile the latest Atlas review outputs before publishing; the installed armory baseline can lag behind approved reviews. Runtime assets, source game archives, audio, saves and local paths remain excluded; do not add the atlas export to `main`.

## Development

Use a separate branch or worktree when another task is active. Preserve unrelated edits. Read the roadmap and relevant qualification scripts before changing a subsystem. Keep source changes and evidence focused; historical receipts may depend on private fixtures.

## Asset work

Read [the art direction rules](docs/art-direction.md) before creating, importing or revising game assets. Stock Ultima Online camera perspective, lighting, scale and view-specific angles are the reference for every asset. U7 supplies the object's identity and design. In the armory, leather, scale and plate chests own matching shoulders and arms; gauntlets remain at the wrists.
