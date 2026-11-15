# Public Trinsic atlas

The atlas is hosted at **https://vedit.github.io/ultima-offline-7/**.

GitHub Pages serves the root of the independent `gh-pages` branch. The game source stays on `main`. Pages deploys automatically when the site branch changes; `.nojekyll` tells GitHub to serve the already-built static site.

The first public snapshot contains 7,141 catalog entries and nine linked pages: the main atlas, homes, inn, public interiors, armory, shields, gargoyles, revised matches and stock studies. The approved rake is linked from the atlas. Existing candidate/approval labels remain visible; the site is a review catalog, not a promise that every candidate is installed in the game.

## Export a reviewed atlas

Use the existing generated atlas directory you intend to publish. A newly generated baseline atlas and a newer local art review can differ; inspect the source date and pages first. Do not regenerate or overwrite parallel artwork as part of publishing.

```powershell
py -3.13 -B game/atlas/publish_site.py --atlas 'D:\path\to\reviewed-atlas' --out 'D:\empty\atlas-site'
py -3.13 -B -m unittest discover -s tests -p test_atlas_site.py -q
```

The exporter follows links from `index.html`, copies all images referenced by the catalog, fixes local atlas links, adds shared navigation and removes machine paths from input fingerprints. It rejects missing/escaping dependencies and refuses a nonempty output directory. It excludes unlinked old revisions, executable content and runtime `.gump`/`.alpha` assets. PNGs are copied unchanged. `publication.json` records the source catalog hash, source date, pages, sizes and exported page hashes.

Before uploading, verify all pages, images and local links, search/filter behavior, the U7 original/upscaled toggle, pagination and a narrow viewport. This explicit website publication covers review comparisons only. Never copy the entire private runtime or force-add ignored game files.

## Publish an update

Use an isolated checkout of `origin/gh-pages`. Review its current commit, then replace its site files with the verified export, keeping its Git metadata. Inspect the staged diff and commit normally. Push only `HEAD:gh-pages`; do not force-push, mirror refs or change the source branch. Do not publish directly from an active art-development folder.

Pages settings should remain **Deploy from a branch → gh-pages → /(root)**. Follow the Pages deployment result and verify the live URL before reporting success. See [GitHub's publishing-source documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

The original U7/UO artwork remains credited to its rights holders. This atlas is a project review presentation, not a game-data download or a new license for those assets.
