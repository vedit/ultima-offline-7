import hashlib
import struct
import unittest

from u7uo.shore import PROJECTION, art_key, compose


class ShoreTests(unittest.TestCase):
    def test_native_member_keys(self):
        self.assertEqual(art_key(0x79),4252316317249405192)
        self.assertEqual(art_key(0xa8),15002293201429739685)

    def test_source_axes_distinct_donors_and_opaque_black(self):
        palette = bytearray(768)
        palette[120*3:120*3+3] = bytes((62,0,0))
        # Northwest is water; northeast is mud; southwest is a red marker;
        # southeast is black stone. Target east corresponds to increasing source X.
        frame = bytes((80 if x<4 else 144) if y<4 else (120 if x<4 else 121)
                      for y in range(8) for x in range(8))
        raw,digest,radar = compose(frame,palette,[0x03e0]*1012,[0x001f]*1012)
        expected = bytearray(44*44*4)
        pixels = {}
        for i,(screen,_) in enumerate(PROJECTION):
            color, = struct.unpack_from("<H",raw,i*2)
            pixels[(screen%44,screen//44)] = color
            expected[screen*4:screen*4+4] = bytes([(color>>s&31)*255//31 for s in (10,5,0)]+[255])
        self.assertEqual(len(pixels),1012)
        self.assertEqual([pixels[p] for p in [(21,0),(43,22),(0,22),(22,43)]],
                         [0x001f,0x03e0,0x7c00,0])
        self.assertEqual(expected[0:4],bytes(4))
        self.assertEqual(digest,hashlib.sha256(expected).hexdigest())
        self.assertGreater(radar,0)
