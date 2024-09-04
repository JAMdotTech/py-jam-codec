import unittest

from jamcodec.base import JamBytes
from jamcodec.exceptions import ScaleEncodeException
from jamcodec.types import VarInt64


class TestVarInt64(unittest.TestCase):
    def test_scale_encode(self):

        self.assertEqual('0x01', VarInt64.encode(1).to_hex())
        self.assertEqual('0x7f', VarInt64.encode(127).to_hex())
        self.assertEqual('0x8080', VarInt64.encode(128).to_hex())
        self.assertEqual('0xc00040', VarInt64.encode(2**14).to_hex())
        self.assertEqual('0xe0000020', VarInt64.encode(2**21).to_hex())
        self.assertEqual('0xf000000010', VarInt64.encode(2**28).to_hex())
        self.assertEqual('0xf80000000008', VarInt64.encode(2**35).to_hex())
        self.assertEqual('0xfc000000000004', VarInt64.encode(2**42).to_hex())
        self.assertEqual('0xfe00000000000002', VarInt64.encode(2**49).to_hex())
        self.assertEqual('0xff0000000000000001', VarInt64.encode(2**56).to_hex())
        self.assertEqual('0x83e8', VarInt64.encode(1000).to_hex())
        self.assertEqual('0xc4e093', VarInt64.encode(300000).to_hex())
        self.assertEqual('0xdfffff', VarInt64.encode(2 ** 21 - 1).to_hex())
        self.assertEqual('0xf0ffffff1f', VarInt64.encode(2**29-1).to_hex())
        self.assertEqual('0xffffffffffffffffff', VarInt64.encode(2**64 - 1).to_hex())

    def test_encode_overflow(self):
        with self.assertRaises(ScaleEncodeException) as context:
            VarInt64.encode(2**64)

        with self.assertRaises(ScaleEncodeException) as context:
            VarInt64.encode(-1)

    def test_scale_decode(self):

        self.assertEqual(1, VarInt64.decode(JamBytes('0x01')))
        self.assertEqual(128, VarInt64.decode(JamBytes('0x8080')))
        self.assertEqual(1000, VarInt64.decode(JamBytes('0x83e8')))
        self.assertEqual(300000, VarInt64.decode(JamBytes('0xc4e093')))
        self.assertEqual(2 ** 14, VarInt64.decode(JamBytes('0xc00040')))
        self.assertEqual(2 ** 21, VarInt64.decode(JamBytes('0xe0000020')))
        self.assertEqual(2 ** 28, VarInt64.decode(JamBytes('0xf000000010')))
        self.assertEqual(2 ** 35, VarInt64.decode(JamBytes('0xf80000000008')))
        self.assertEqual(2 ** 42, VarInt64.decode(JamBytes('0xfc000000000004')))
        self.assertEqual(2 ** 49, VarInt64.decode(JamBytes('0xfe00000000000002')))
        self.assertEqual(2 ** 56, VarInt64.decode(JamBytes('0xff0000000000000001')))
        self.assertEqual(2**21-1, VarInt64.decode(JamBytes('0xdfffff')))
        self.assertEqual(2**29-1, VarInt64.decode(JamBytes('0xf0ffffff1f')))
        self.assertEqual(2 ** 64 - 1, VarInt64.decode(JamBytes('0xffffffffffffffffff')))


if __name__ == '__main__':
    unittest.main()
