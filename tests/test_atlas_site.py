import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


script = Path(__file__).resolve().parents[1] / 'game/atlas/publish_site.py'
spec = importlib.util.spec_from_file_location('atlas_site', script)
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)


class AtlasSiteTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.atlas, self.out = self.root / 'atlas', self.root / 'site'
        (self.atlas / 'images').mkdir(parents=True)
        (self.atlas / 'images/ab12.png').write_bytes(b'fixture image')
        (self.atlas / 'images/unused.png').write_bytes(b'old unused export')
        (self.atlas / 'runtime.gump').write_bytes(b'private runtime data')
        (self.atlas / 'old-review.html').write_text('<main>Unlinked old review</main>')
        (self.atlas / 'catalog.js').write_text('const CATALOG=[{"source_image":"ab12"}];')
        (self.atlas / 'index.html').write_text('<main><a href="sources.json">Sources</a></main>')
        (self.atlas / 'sources.json').write_text(json.dumps({'input_sha256': {'C:/Users/Test/Assets/UO/art.mul':'abc'}, 'output_sha256':{'index.html':'old'}}))

    def run_export(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return site.export(self.atlas, self.out)

    def test_only_linked_web_files_and_catalog_images_are_exported(self):
        result = self.run_export()
        self.assertEqual(result['rows'], 1)
        self.assertTrue((self.out / 'images/ab12.png').exists())
        for name in ('runtime.gump', 'old-review.html', 'images/unused.png'):
            self.assertFalse((self.out / name).exists())
        receipt = (self.out / 'sources.json').read_text()
        self.assertNotIn('C:/Users', receipt)
        self.assertIn('local-assets/UO/art.mul', receipt)
        self.assertNotIn('output_sha256', receipt)
        with self.assertRaises(ValueError):
            self.run_export()

    def test_relative_escape_and_runtime_links_are_rejected(self):
        for url in ('../outside.txt', 'runtime.gump'):
            (self.atlas / 'index.html').write_text(f'<main><a href="{url}">link</a></main>')
            with self.assertRaises(ValueError):
                self.run_export()
            self.assertFalse(self.out.exists())

    def test_missing_catalog_image_does_not_publish_incomplete_atlas(self):
        (self.atlas / 'catalog.js').write_text('const CATALOG=[{"target_image":"deadbeef"}];')
        with self.assertRaises(ValueError):
            self.run_export()
        self.assertFalse(self.out.exists())

    def test_public_urls_are_not_treated_as_drive_paths(self):
        self.assertIsNone(site.PATH_PATTERN.search('https://github.com/vedit/ultima-offline-7'))
        self.assertIsNotNone(site.PATH_PATTERN.search('C:/Users/Test/atlas'))

    def test_weapons_land_at_root_and_catalog_links_keep_their_location(self):
        (self.atlas / 'index.html').write_text('<main>Catalog <a href="armory.html">Weapons</a></main>')
        (self.atlas / 'armory.html').write_text('<main>Weapon review <a href="index.html?scope=all#637/0">Original</a></main>')
        result = self.run_export()
        self.assertEqual(result['landing_page'], 'armory.html')
        self.assertEqual((self.out / 'index.html').read_bytes(), (self.out / 'armory.html').read_bytes())
        self.assertIn('atlas.html?scope=all#637/0', (self.out / 'index.html').read_text())
        self.assertIn('Catalog', (self.out / 'atlas.html').read_text())
        self.assertIn('atlas.html', result['output_sha256'])

    def test_review_overlay_preserves_ordinary_items_and_replaces_superseded_variants(self):
        spec = importlib.util.spec_from_file_location('review_snapshot', script.with_name('review_snapshot.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        base = [dict(shape=s, ground='old') for s in (561, 564, 759, 587, 545, 663, 637, 702)]
        lore = [dict(shape=s, ground='accepted') for s in ('561/0', '564/0', '759/0', '759/1', '587/1', '587-approved')]
        cards = module.reconcile_cards(base, lore, {'ground':'final contour'}, {545:{'ground':'silver'}, 663:{'ground':'blue rim'}})
        by_shape = {c['shape']:c for c in cards}
        self.assertNotIn(561, by_shape)
        self.assertNotIn('587-approved', by_shape)
        self.assertEqual(by_shape[587]['ground'], 'old')
        self.assertEqual(by_shape['587/1']['ground'], 'accepted')
        self.assertEqual(by_shape[663]['ground'], 'blue rim')
        self.assertEqual(by_shape[637]['ground'], 'final contour')
        self.assertTrue(by_shape['759/1']['approved'])

    def test_local_atlas_link_is_rewritten_but_outside_file_is_rejected(self):
        if self.root.drive:  # Windows file:/// drive syntax used by the review pages.
            url = (self.atlas / 'index.html').as_uri()
            self.assertEqual(site.local_link(url, 'homes.html', self.atlas), 'index.html')
            with self.assertRaises(ValueError):
                site.local_link((self.root / 'private.txt').as_uri(), 'homes.html', self.atlas)


if __name__ == '__main__':
    unittest.main()
