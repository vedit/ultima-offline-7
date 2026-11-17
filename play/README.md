# Play Trinsic in the browser

Open https://vedit.github.io/ultima-offline-7/play/ in Chrome or Edge, select your
Ultima VII Black Gate + Forge of Virtue folder, and choose **Play now**.
The existing ClassicUO and Black Gate WebAssembly build runs locally.

GitHub Pages serves the client and our artwork. Automatic UO data downloads use
the existing HTTPS asset service at
https://ultima-offline-trinsic.firatarig.chatgpt.site/api/uo/manifest.
That service must remain online; GitHub Pages cannot run its server code.
The initial UO download is approximately 143 MB, retained in browser storage.
Ultima VII files remain local. No Python, UO installation or shard account is needed.

Optionally select an Exult installation with the Roland MT-32 OGG recordings
in data/music. These files stay local and are remembered in browser storage.
The original game controls track changes. Audio starts after a user interaction.

Press F5 to save. Optionally choose a save folder in supported browsers; saves
use ultima-offline-trinsic.u7 and also keep a browser backup. Returning to a
folder with an existing save resumes it. If folder permission is unavailable,
the browser backup is used; use Folders to reconnect. Folders opens setup again.

Game and music imports use the standard directory file input so protected
Steam/Exult locations do not require File System Access permissions. Imported
files are cached locally for refresh/resume. Optional music, save folders and
Steam path help are collapsed under optional settings. For writable folder
saves, choose a folder in Documents if the browser rejects a protected path.

Saves are local to this browser and origin unless a save folder is selected.
Existing saves on the chatgpt.site address do not automatically appear on
github.io. Refreshing resumes the saved tile. Clearing site storage deletes
browser data and saves; files in a chosen save folder remain.

The service worker enables cross-origin isolation required by WebAssembly
threads because GitHub Pages does not configure our custom isolation headers.
The first navigation may reload once. Full upstream notices are in licenses.txt.
