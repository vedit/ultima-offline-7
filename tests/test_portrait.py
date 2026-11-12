import struct
import unittest

from u7uo.portrait import compile_gump, face_frame


def shape(spans):
    # Origin (1, 1) in a 4x2 frame. Frame zero starts at byte eight.
    data = struct.pack("<hhhh", 2, 1, 1, 0) + spans + bytes(2)
    return struct.pack("<II", len(data) + 8, 8) + data


class PortraitTest(unittest.TestCase):
    def test_source_spans_target_alpha_and_scanline_pointers(self):
        raw = struct.pack("<Hhh", 4, -1, -1) + bytes([0, 1])
        encoded = struct.pack("<Hhh", 9, -1, 0) + bytes([5, 1, 4, 0, 2])
        width, height, pixels, offset, origin = face_frame(shape(raw + encoded), 0)
        self.assertEqual((width, height, offset, origin), (4, 2, 8, (1, 1)))
        self.assertEqual(pixels, [0, 1, None, None, 1, 1, 0, 2])
        palette = bytes([0, 0, 0, 63, 0, 0, 0, 0, 63]) + bytes(759)
        data, rgba = compile_gump(width, height, pixels, palette)
        self.assertEqual(struct.unpack_from("<II", data), (2, 5))
        self.assertEqual(list(struct.iter_unpack("<HH", data[8:])),
                         [(0x8000, 1), (0xFC00, 1), (0, 2), (0xFC00, 2), (0x8000, 1), (0x801F, 1)])
        self.assertEqual(rgba[:16], bytes([0, 0, 0, 255, 255, 0, 0, 255, 0, 0, 0, 0, 0, 0, 0, 0]))
        self.assertEqual(rgba[-4:], bytes([0, 0, 255, 255]))

    def test_truncated_invalid_or_overlapping_spans_fail(self):
        head = struct.pack("<Hhh", 5, -1, 0)
        raw = struct.pack("<Hhh", 4, -1, -1) + bytes([1, 2])
        cases = [shape(head + b"\0"), shape(head + b"\x07\x01"), shape(head + b"\x05"),
                 shape(raw + raw), shape(struct.pack("<Hhh", 4, 2, -1) + bytes(2)), shape(raw)[:-2]]
        for frame in cases:
            with self.subTest(frame=frame), self.assertRaises(ValueError):
                face_frame(frame, 0)
