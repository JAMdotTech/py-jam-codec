# Python SCALE Codec Library
#
# Copyright 2018-2020 Stichting Polkascan (Polkascan Foundation).
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
#  test_scalebytes.py
#

import unittest

from jamcodec.base import JamBytes
from jamcodec.exceptions import RemainingScaleBytesNotEmptyException
from jamcodec.types import CompactDef, U32, Array, U8, String


class TestScaleBytes(unittest.TestCase):

    def test_unknown_data_format(self):
        self.assertRaises(ValueError, JamBytes, 123)
        self.assertRaises(ValueError, JamBytes, 'test')

    def test_bytes_data_format(self):
        obj = CompactDef(U32).new()
        obj.decode(JamBytes(b"\x02\x09\x3d\x00"))
        self.assertEqual(obj.value, 1000000)

    def test_remaining_bytes(self):
        scale = JamBytes("0x01020304")
        scale.get_next_bytes(1)
        self.assertEqual(scale.get_remaining_bytes(), b'\x02\x03\x04')

    def test_reset(self):
        scale = JamBytes("0x01020304")
        scale.get_next_bytes(1)
        scale.reset()
        self.assertEqual(scale.get_remaining_bytes(), b'\x01\x02\x03\x04')

    def test_add_scalebytes(self):
        scale_total = JamBytes("0x0102") + "0x0304"

        self.assertEqual(scale_total.data, bytearray.fromhex("01020304"))

    def test_scale_bytes_compare(self):
        self.assertEqual(JamBytes('0x1234'), JamBytes('0x1234'))
        self.assertNotEqual(JamBytes('0x1234'), JamBytes('0x555555'))

    def test_no_more_bytes_available(self):
        obj = Array(U8, 4).new()
        with self.assertRaises(RemainingScaleBytesNotEmptyException):
            obj.decode(JamBytes("0x010203"), check_remaining=False)

