# Public Trinsic atlas

The atlas is hosted at **https://vedit.github.io/ultima-offline-7/**.

GitHub Pages serves the root of the independent `gh-pages` branch. The game source stays on `main`. Pages deploys automatically when the site branch changes; `.nojekyll` tells GitHub to serve the already-built static site.

The site opens on **Weapons and armour**, with the Weapon family selected. The **Full catalog** link opens `atlas.html` (7,141 source entries); homes, inn, public interiors and the other galleries remain available. Shields are included in the equipment page's **Family → Shield** filter (buckler, curved heater, kite, magic, spiked and wooden). There is no separate Shields navigation tab; the old two-shield comparison URL remains available for existing bookmarks. `armory.html` also opens the equipment page. The approved rake is linked from the full catalog. Existing candidate/approval labels remain visible; the site is a review catalog, not a promise that every candidate is installed in the game.

The Atlas chat uses the same game repository, not a second source repository. Its generated review outputs can be newer than the installed atlas. In particular, the installed `armory.html` was an early baseline even after later batches had been approved. The public equipment collection now reconciles those reviews into 109 entries, including frame-specific magical variants, accepted shimmer previews, the redesigned shields and the final serpentine guard.

## Export a reviewed atlas

Use the existing generated atlas directory you intend to publish. A newly generated baseline atlas and a newer local art review can differ; inspect the source date and pages first. Do not regenerate or overwrite parallel artwork as part of publishing.

```powershell
py -3.13 -B game/atlas/publish_site.py --atlas 'D:\path\to\reviewed-atlas' --reviews 'D:\path\to\Atlas-review-root' --guard-ground 'D:\path\to\public-interiors-revision5\guard-ground' --out 'D:\empty\atlas-site'
py -3.13 -B -m unittest discover -s tests -p test_atlas_site.py -q
```

The exporter follows links from the input `index.html`, copies all images referenced by the catalog, fixes local atlas links (including their query and fragment), adds shared navigation and removes machine paths from input fingerprints. It writes that catalog to `atlas.html` and serves the equipment page at the root. It rejects missing/escaping dependencies and refuses a nonempty output directory. It excludes unlinked old revisions, executable content and runtime `.gump`/`.alpha` assets. Existing PNG/WebP review pixels are copied or embedded unchanged. `publication.json` records source hashes, source date, review precedence, pages, sizes and exported page hashes.

`--reviews` selects the newer Atlas review collection; `--guard-ground` supplies its five accepted ground facings. `review_snapshot.py` records the specific November 2026 review precedence: eight-batch equipment page → accepted lore variants and shimmer → later shield and guard corrections. It retains ordinary boots separately from magic boots and both Ethereal Ring states. The lore page supplies its existing review controls, including female paperdolls. The current Inn, shield and public-interior pages come directly from that same review root. The Fellowship column-base change remains explicitly labeled a preview.

For a future art pass, update this explicit recipe and its sources after checking the Atlas chat's approvals; do not select files just by modification time or regenerate art during publication. Omitting `--reviews` exports the installed baseline only and must not be presented as the latest reviewed equipment. Public visitor feedback stays in that visitor's browser and never changes recorded approval or the source files.

The equipment, full-catalog and room-comparison pages (Homes, Inn and public interiors) show animated placeholders before their card data loads, then individual image spinners until each preview is ready. Loading also follows filter, page and frame changes. Failed images show an unavailable state; reduced-motion preferences disable the animation.

Before uploading, verify all pages, images and local links, search/filter behavior, the U7 original/upscaled toggle, pagination and a narrow viewport. This explicit website publication covers review comparisons only. Never copy the entire private runtime or force-add ignored game files.

## Publish an update

Use an isolated checkout of `origin/gh-pages`. Review its current commit, then replace its site files with the verified export, keeping its Git metadata. Inspect the staged diff and commit normally. Push only `HEAD:gh-pages`; do not force-push, mirror refs or change the source branch. Do not publish directly from an active art-development folder.

Pages settings should remain **Deploy from a branch → gh-pages → /(root)**. Follow the Pages deployment result and verify the live URL before reporting success. See [GitHub's publishing-source documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

The original U7/UO artwork remains credited to its rights holders. This atlas is a project review presentation, not a game-data download or a new license for those assets.
