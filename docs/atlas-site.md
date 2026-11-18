# Project homepage and public Trinsic atlas

The project's custom domain is **https://ultimaoffline7.com/**. GitHub Pages remains the host; the previous address is `https://vedit.github.io/ultima-offline-7/`.

GitHub Pages serves the root of the independent `gh-pages` branch. The game source stays on `main`. Pages deploys automatically when the site branch changes; `.nojekyll` tells GitHub to serve the already-built static site.

The site opens on the project homepage: actual gameplay captures, an introduction for U7/UO players, a switchable Fellowship interior comparison, current Trinsic scope and build guides. **Weapons and armour** is at `armory.html`, with the Weapon family selected. The **Full catalog** link opens `atlas.html` (7,141 source entries); homes, inn, public interiors and the other galleries remain available. Shields are included in the equipment page's **Family → Shield** filter (buckler, curved heater, kite, magic, spiked and wooden). There is no separate Shields navigation tab; the old two-shield comparison URL remains available for existing bookmarks. `armory.html` also opens the equipment page. The approved rake is linked from the full catalog. Existing candidate/approval labels remain visible; the site is a review catalog, not a promise that every candidate is installed in the game.

The Atlas chat uses the same game repository, not a second source repository. Its generated review outputs can be newer than the installed atlas. In particular, the installed `armory.html` was an early baseline even after later batches had been approved. The public equipment collection now reconciles those reviews into 109 entries, including frame-specific magical variants, accepted shimmer previews, the redesigned shields and the final serpentine guard.

## Export the homepage and reviewed atlas

Use the existing generated atlas directory you intend to publish. A newly generated baseline atlas and a newer local art review can differ; inspect the source date and pages first. Do not regenerate or overwrite parallel artwork as part of publishing.

```powershell
py -3.13 -B game/atlas/publish_site.py --atlas 'D:\path\to\reviewed-atlas' --reviews 'D:\path\to\Atlas-review-root' --guard-ground 'D:\path\to\public-interiors-revision5\guard-ground' --screenshots 'D:\path\to\selected-client-captures' --social-assets 'D:\path\to\current-pages\site\social' --out 'D:\empty\atlas-site'
py -3.13 -B -m unittest discover -s tests -p test_atlas_site.py -q
```

The exporter follows links from the input `index.html`, copies all images referenced by the catalog, fixes local atlas links (including their query and fragment), adds shared navigation and removes machine paths from input fingerprints. It writes that catalog to `atlas.html` and keeps the equipment page at `armory.html`; `index.html` is the project homepage. It rejects missing/escaping dependencies and refuses a nonempty output directory. It excludes unlinked old revisions, executable content and runtime `.gump`/`.alpha` assets. Existing PNG/WebP review pixels are copied or embedded unchanged. `publication.json` records source hashes, source date, review precedence, pages, sizes and exported page hashes.

`--reviews` selects the newer Atlas review collection; `--guard-ground` supplies its five accepted ground facings. `review_snapshot.py` records the specific November 2026 review precedence: eight-batch equipment page → accepted lore variants and shimmer → later shield and guard corrections. It retains ordinary boots separately from magic boots and both Ethereal Ring states. The lore page supplies its existing review controls, including female paperdolls. The current Inn, shield and public-interior pages come directly from that same review root. The Fellowship column-base change remains explicitly labeled a preview.

For a future art pass, update this explicit recipe and its sources after checking the Atlas chat's approvals; do not select files just by modification time or regenerate art during publication. The public CLI requires the reviewed collection, final guard art and selected screenshots. The lower-level `export()` function can still export minimal review fixtures for tests; those fixtures must not be presented as the published site. Public visitor feedback stays in that visitor's browser and never changes recorded approval or the source files.

The equipment, full-catalog and room-comparison pages (Homes, Inn and public interiors) show animated placeholders before their card data loads, then individual image spinners until each preview is ready. Loading also follows filter, page and frame changes. Failed images show an unavailable state; reduced-motion preferences disable the animation.

Before uploading, verify all pages, images and local links, search/filter behavior, the U7 original/upscaled toggle, pagination and a narrow viewport. This explicit website publication covers the project homepage, the selected gameplay captures and review comparisons. Never copy the entire private runtime or force-add ignored game files.

## Homepage inputs and maintenance

Edit `game/site/index.html`, `home.css` and `home.js` for the landing page. It is static, has no external font or JavaScript dependencies, and uses relative asset links that work at both the custom-domain root and a repository subpath. Keep the copy honest about the unfinished full campaign.

`--screenshots` must point to a local folder containing `barn-overview-u7.png` / `barn-overview-uo7.png`, `fellowship-interior-u7.png` / `fellowship-interior-uo7.png`, and `guardian-dream-u7.png` / `guardian-dream-uo7.png`, plus their `scene-captures.json` receipt. Review them for presentation and private information before publication. The exporter checks all three comparison pairs against their capture hashes. Do not substitute promotional renders or include save data, audio or other runtime files. Captures belong only to the published site branch, not source `main`.

Capture each scene pair from the same private checkpoint with `game/qualification/capture_scene_comparisons.py --source-run <saved-scene> --run-prefix <unused-prefix> --output <capture-folder> --town <approved-town-overlay>`. The source save must have the Avatar named Vedit. The script copies it into two new runs and refuses existing destinations. Original U7 images come from the portable original renderer and original game artwork; UO7 images come from the actual ClassicUO window. It encodes original PPM frames losslessly as PNG without cropping or retouching. Camera perspectives differ; the viewer does not warp the scenes to suggest pixel alignment. For the Guardian pair, retain the approved ClassicUO dream capture and capture the original DOS intro through the existing `tools/oracle/capture.cjs` video interface. Record both image hashes and their different sources in `scene-captures.json`; this pair is an adaptation comparison, not a shared saved scene. Never substitute an extracted head or a recreated background for an actual cutscene capture.

`game/atlas/homepage.py` copies those captures unchanged and extracts three equipment previews byte-for-byte from the reviewed HTML. It does not redraw or regenerate any art. `site/sources.json` records logical sources and SHA-256 hashes without private machine paths. The main `publication.json` also covers these files. Re-export after changing the template or inputs so those receipts stay accurate.

Check the homepage on desktop and a narrow viewport, including the barn and Fellowship pairs, the centered reveal slider, its endpoints and keyboard controls, loading/error states, Escape dismissal, the Fellowship switch and the Guardian dream slider and its adaptation caption. The comparison viewer resets to 50/50 when selecting a pair or reopening it. Galleries retain their shared Home/Weapons navigation and existing loading states; shields remain an equipment filter rather than a separate tab.

## Publish an update

### Social sharing artwork

The homepage uses static Open Graph and X/Twitter large-image tags. Crawlers do
not need JavaScript. The image URL is versioned so future revisions can use a
new filename without depending on old image caches. The image's absolute HTTPS
URL, JPEG MIME type, measured dimensions and descriptive alt text are explicit.

`share.html` provides the project link and landscape/portrait downloads for
messaging apps and social posts. These AI-assisted promotional composites are
separate from the unedited gameplay comparison captures; they must not replace
those captures or be described as screenshots. Their JPEGs live only on
`gh-pages` under `site/social/`. The source manifest is
`game/site/social-assets.json`; the export verifies each SHA-256 before copying.

Pass the previous publication's `site/social` folder as `--social-assets` when
exporting the full homepage, or place that folder under the selected screenshot
directory. Missing or altered assets stop the export. Source images and the
generation prompts are recorded in `game/site/social-prompts.md`.

For a metadata-only release, change only the homepage head, sharing page and
social assets in an isolated checkout of current `gh-pages`. Preserve the
entire `play/` tree and its exact bundle: this is not a browser game rebuild.
Verify the image byte sizes, MIME types, dimensions, metadata and public HTTPS
responses with crawler user agents. A 200 response verifies availability, not a
guarantee that each social app has refreshed its cached card. Actual platform
previews may crop differently or require the user to share the link again.

Use an isolated checkout of `origin/gh-pages`. Review its current commit, then replace its site files with the verified export, keeping its Git metadata. Inspect the staged diff and commit normally. Push only `HEAD:gh-pages`; do not force-push, mirror refs or change the source branch. Do not publish directly from an active art-development folder.

Pages settings should remain **Deploy from a branch → gh-pages → /(root)**. Follow the Pages deployment result and verify the live URL before reporting success. See [GitHub's publishing-source documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

## Custom domain and DNS

The root `CNAME` on `gh-pages` must contain only `ultimaoffline7.com`. The atlas exporter copies the tracked `game/site/CNAME` into every export so future publications retain the domain. When publishing a partial update, preserve the existing browser build under `play/` and other independently updated site files.

The domain uses Cloudflare DNS. Configure these records with **DNS only** (proxy off) and TTL **Auto**:

| Type | Name | Target |
| --- | --- | --- |
| A | @ | 185.199.108.153 |
| A | @ | 185.199.109.153 |
| A | @ | 185.199.110.153 |
| A | @ | 185.199.111.153 |
| CNAME | www | vedit.github.io |

GitHub Pages must have `ultimaoffline7.com` set as its custom domain before adding these DNS records. Preserve unrelated mail or verification records. Once GitHub's DNS check succeeds and its certificate is issued, enable **Enforce HTTPS** and verify the homepage, `/homes.html`, `/play/`, and the `www` redirect. The `www` CNAME targets the account hostname, without the repository path. See [GitHub's custom-domain instructions](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site).

The browser demo's storage and folder permissions belong to each origin. Existing browser-local saves at `vedit.github.io` are not automatically transferred to `ultimaoffline7.com`; retain an exported save or the configured external save folder before switching origins.

## Website visits

Cloudflare Web Analytics uses **manual JS snippet installation** for
`ultimaoffline7.com`. DNS-only hosting does not support automatic injection.
The exporter adds `game/site/web-analytics.html` to the homepage, sharing page
and atlas galleries; redirect aliases are excluded to count their destinations
once. The token in that snippet is a public site identifier, not an API secret.
Keep automatic injection off even if proxying is enabled later.

For a website-only update, run `python game/atlas/web_analytics.py <pages-worktree>`.
It is idempotent and touches only top-level HTML, preserving the exact `play/`
bundle. Publish the isolated diff through the normal Pages workflow. Verify that
the live HTML includes exactly one beacon and that a browser loads it. Web
Analytics can take a few minutes to show new traffic, and content blockers can
prevent reporting. Historical unmeasured visits cannot be recovered.

View site visits in the account's
[Web Analytics dashboard](https://dash.cloudflare.com/9ba409024b123e5c7470039a1785b53b/web-analytics/overview?siteTag=0183f0fc3d944f16a66cf2783129d26b).
This works with DNS-only records. Zone HTTP traffic/security charts require the
Cloudflare proxy and are separate from browser-based Web Analytics. See
[Cloudflare's manual setup](https://developers.cloudflare.com/web-analytics/get-started/#sites-not-proxied-through-cloudflare).

## Browser playtest analytics

After preparing a browser export, run `python game/analytics/install.py <pages-worktree>/play`
to retain the optional playtime reporting and launcher privacy toggle. This is a
separate Cloudflare Worker at `telemetry.ultimaoffline7.com`; the site and game
stay on GitHub Pages. Preserve that Worker custom-domain record when changing
site DNS. See [collection, deployment, tests and private reporting](../game/analytics/README.md).
Do not add analytics credentials, raw query exports or player data to the public site.

The original U7/UO artwork remains credited to its rights holders. This atlas is a project review presentation, not a game-data download or a new license for those assets.
