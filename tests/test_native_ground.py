"""Presentation underlays must follow native footprints, never a donor map."""
from pathlib import Path
import runpy
import unittest

native_ground=runpy.run_path(str(Path(__file__).resolve().parents[1]/
                               'game/qualification/town_scale.py'))['native_ground']


class Ground:
    def __init__(self,cells=(),default=(24,0)):
        self.cells=dict(cells);self.default=default

    def tile(self,x,y):
        shape,frame=self.cells.get((x,y),self.default)
        return dict(shape=shape,frame=frame)


class NativeGroundTests(unittest.TestCase):
    def setUp(self):
        self.tfa=bytearray(3072)
        self.tfa[900]=32  # A one-lift scenery shape, 3 x 2 native cells.
        self.tfa[902]=2|8
        self.land={(24,0):1001,(18,16):999,(148,0):3}
        self.filler=lambda s,f:(s,f)==(18,16)

    def resolve(self,cells,floors=None,source=None,bounds=(0,0,12,12)):
        return native_ground(Ground(cells),self.tfa,self.land,floors or {},
                             source or {},self.filler,bounds)

    def test_hidden_filler_and_scenery_are_recovered_but_real_dark_ground_survives(self):
        ground,repairs=self.resolve({(3,2):(300,0),(1,1):(18,16),(8,8):(18,16)},
                                    floors={(1,1):888})
        self.assertEqual(ground[1,1],(1001,0))
        self.assertEqual(ground[3,2],(1001,0))
        self.assertEqual(ground[8,8],(999,0))
        self.assertEqual({(r[0],r[1],r[4]) for r in repairs},
                         {(1,1,'concealed filler'),(3,2,'scenery anchor')})

    def test_reflection_swaps_footprint_axes(self):
        ground,_=self.resolve({(3,3):(300,32),(2,1):(18,16),(1,2):(18,16)})
        self.assertEqual(ground[2,1],(1001,0))
        self.assertEqual(ground[1,2],(999,0))

    def test_anchor_beyond_output_boundary_still_covers_its_native_cells(self):
        ground,repairs=self.resolve({(13,11):(300,0),(11,10):(18,16)},bounds=(10,10,12,12))
        self.assertEqual(ground[11,10],(1001,0))
        self.assertEqual([(r[0],r[1]) for r in repairs],[(11,10)])

    def test_actual_surfaces_and_elevations_are_unchanged(self):
        cells={(3,2):(300,0),(1,1):(148,0),(5,5):(24,0),(7,7):(148,0)}
        source={(7,7):(6,4)};floors={(5,5):1234}
        before=dict(source)
        ground,_=self.resolve(cells,floors,source)
        self.assertEqual(ground[1,1],(3,0))  # Genuine grass under scenery.
        self.assertEqual(ground[5,5],(1234,0))
        self.assertEqual(ground[7,7],(6,4))
        self.assertEqual(source,before)
        self.assertEqual(self.resolve(cells,floors,source),self.resolve(dict(reversed(list(cells.items()))),floors,source))

    def test_missing_native_ground_is_reported_instead_of_invented(self):
        with self.assertRaisesRegex(AssertionError,'no surrounding ground'):
            native_ground(Ground(default=(300,0)),self.tfa,self.land,{}, {},self.filler,(0,0,4,4))


if __name__=='__main__':unittest.main()
