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

Saves are local to this browser and origin. Existing saves on the chatgpt.site
address do not automatically appear on github.io. Refreshing this Pages build
resumes its own saved tile. Clearing site storage deletes its data and saves.

The service worker enables cross-origin isolation required by WebAssembly
threads because GitHub Pages does not configure our custom isolation headers.
The first navigation may reload once. Full upstream notices are in licenses.txt.
