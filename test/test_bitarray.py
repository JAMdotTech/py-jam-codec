# Python JAM Codec Library
#
# Copyright 2024 JAMdot Technologies
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import unittest

from jamcodec.base import JamBytes
from jamcodec.types import BitArray


class TestBitArray(unittest.TestCase):

    def test_bitarray_decode(self):
        obj = BitArray(3).new()
        obj.decode(JamBytes('0x07'))
        self.assertEqual(obj.value, [True, True, True])

    def test_bitvec_decode_size_2bytes(self):
        obj = BitArray(10).new()
        obj.decode(JamBytes('0xfd02'))
        self.assertEqual(obj.value, [True, False, True, True, True, True, True, True, False, True])

    def test_bitvec_encode_list(self):
        obj = BitArray(3).new()
        data = obj.encode([True, True, True])
        self.assertEqual('0x07', data.to_hex())

    def test_bitvec_encode_list2(self):
        obj = BitArray(2).new()
        data = obj.encode([True, False])
        self.assertEqual(data.to_hex(), '0x01')

    def test_bitvec_encode_list3(self):
        obj = BitArray(2).new()
        data = obj.encode([False, True])
        self.assertEqual(data.to_hex(), '0x02')

    def test_bitvec_encode_list4(self):
        obj = BitArray(10).new()
        data = obj.encode([True, False, True, True, True, True, True, True, False, True])
        self.assertEqual(data.to_hex(), '0xfd02')

    # def test_bitvec_encode_bin_str(self):
    #     obj = BitArray(10).new()
    #     data = obj.encode('0b11100000')
    #     self.assertEqual(data.to_hex(), '0x07')
    #
    # def test_bitvec_encode_bin_str2(self):
    #     obj = BitArray(8).new()
    #     data = obj.encode('0b01000000')
    #     self.assertEqual(data.to_hex(), '0x02')
    #
    # def test_bitvec_encode_bin_str3(self):
    #     obj = BitArray(8).new()
    #     data = obj.encode('0b00000001')
    #     self.assertEqual(data.to_hex(), '0x01')
    #
    # def test_bitvec_encode_bin_str4(self):
    #     obj = BitArray(16).new()
    #     data = obj.encode('0b00000010_01111101')
    #     self.assertEqual(data.to_hex(), '0x7d02')
    #
    # def test_bitvec_encode_int(self):
    #     obj = BitVec().new()
    #     data = obj.encode(0b00000111)
    #     self.assertEqual(data.to_hex(), '0x0307')
    #
    # def test_bitvec_encode_int2(self):
    #     obj = BitVec().new()
    #     data = obj.encode(0b00000010)
    #     self.assertEqual(data.to_hex(), '0x0202')
    #
    # def test_bitvec_encode_int3(self):
    #     obj = BitVec().new()
    #     data = obj.encode(0b00000001)
    #     self.assertEqual(data.to_hex(), '0x0101')
    #
    # def test_bitvec_encode_int4(self):
    #     obj = BitVec().new()
    #     data = obj.encode(0b00000010_01111101)
    #     self.assertEqual(data.to_hex(), '0x0a7d02')

    def test_bitvec_encode_empty_list(self):
        obj = BitArray(0).new()
        data = obj.encode([])
        self.assertEqual(data.to_hex(), '0x')

    def test_bitvec_encode_bytes(self):
        obj = BitArray(1).new()
        data = obj.encode(b'\x01')
        self.assertEqual(data.to_hex(), '0x01')

        value = obj.decode(data)
        self.assertEqual([True], value)



if __name__ == '__main__':
    unittest.main()
