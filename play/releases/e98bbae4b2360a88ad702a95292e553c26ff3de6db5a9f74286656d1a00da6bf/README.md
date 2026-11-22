# Play Trinsic in the browser

Install your own copy of Ultima VII: The Black Gate with Forge of Virtue.
The Complete Edition is available on [GOG](https://www.gog.com/en/game/ultima_7_complete) and [Steam](https://store.steampowered.com/app/3067540/Ultima_VII_The_Complete_Edition/).
Open https://ultimaoffline7.com/play/ in Chrome or Edge, select your Black Gate
folder or its `STATIC` folder, and choose **Play now**.
The existing ClassicUO and Black Gate WebAssembly build runs locally.

GitHub Pages serves the client and our artwork. Automatic UO data downloads use
the existing HTTPS asset service at
https://ultima-offline-trinsic.firatarig.chatgpt.site/api/uo/manifest.
That service must remain online; GitHub Pages cannot run its server code.
The UO demo subset is retained in browser storage; later launches reuse it.
Ultima VII files remain local. No Python, UO installation or shard account is needed.

Optionally select an Exult installation with the Roland MT-32 OGG recordings
in data/music. These files stay local and are remembered in browser storage.
The original game controls track changes. Audio starts after a user interaction.

Progress autosaves after a 1.5-second pause following movement or completed actions.
Held movement input suppresses checkpoints, and storage writes run asynchronously.
Pause until Autosaved before closing or refreshing; unload saving is best-effort. F5 still saves manually. Optionally choose a save folder; saves
use ultima-offline-trinsic.u7 and also keep a browser backup. Returning to a
folder with an existing save resumes it. If folder permission is unavailable,
the browser backup is used; use Folders to reconnect. Folders opens setup again.

Game and music imports use the standard directory file input so protected
Steam/Exult locations do not require File System Access permissions. Imported
files are cached locally for refresh/resume. The game folder picker has help
for finding GOG and Steam installations. Optional settings cover music and save folders. For writable folder
saves, choose a folder in Documents if the browser rejects a protected path.

Saves are local to this browser and origin unless a save folder is selected.
Existing saves on the chatgpt.site address do not automatically appear on
github.io. Refreshing resumes the saved tile. Clearing site storage deletes
browser data and saves; files in a chosen save folder remain.

The service worker enables cross-origin isolation required by WebAssembly
threads because GitHub Pages does not configure our custom isolation headers.
The first navigation may reload once. The launch screen shows an animated
loader, estimated overall percentage, and the current startup stage.
Hide bar removes the header; the floating Show bar button restores it. The
preference survives refresh. Build provenance is in build-info.json. The current
desktop Trinsic code and approved artwork include the bloody footprint trail.
New journey starts the shared character creation and voiced dream intro while
preserving existing saves in their numbered slots. Play now resumes saved progress.
The party control and creature animations follow the desktop's shared mappings.
parity-receipt.json records the exact tested source bundle and release checks.
Full upstream notices are in licenses.txt.

Anonymous playtest reporting measures rendered playtime, loading results and
native investigation milestones. Use Folders to turn off "Share anonymous
playtime and progress". DNT/GPC also disable it. Names, saves, files and game
text are never included. The collector is telemetry.ultimaoffline7.com;
reporting is optional and never blocks game execution or saving. See
analytics/privacy.html for timing definitions, retention and limitations.

Browser storage and permissions belong to each origin. A domain change does not
automatically move browser-only saves; an external save folder remains portable.
