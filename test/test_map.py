# Python JAM Codec Library
#
# Copyright 2024 JAMdot technologies.
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
from collections.abc import Mapping

from jamcodec.base import JamBytes
from jamcodec.types import U32, Map, H256, Bytes


class TestMap(unittest.TestCase):

    def test_map_dict_encode(self):

        obj = Map(H256, Bytes).new()

        value = {
            "0xbb30a42c1e62f0afda5f0a4e8a562f7a13a24cea00ee81917b86b89e801314aa": b'\x01\x02',
            "0x03170a2e7597b7b7e3d84c05391d139a62b157e78786d8c082f29dcf4c111314": b'test'
        }
        # Should be encoded sorted by key
        data = obj.encode(value)
        self.assertEqual(
            JamBytes("0x0203170a2e7597b7b7e3d84c05391d139a62b157e78786d8c082f29dcf4c1113140474657374bb30a42c1e62f0afda5f0a4e8a562f7a13a24cea00ee81917b86b89e801314aa020102"),
            data
        )

    def test_map_encode_list(self):
        obj = Map(H256, Bytes).new()

        value = [
            ("0xbb30a42c1e62f0afda5f0a4e8a562f7a13a24cea00ee81917b86b89e801314aa",  b'\x01\x02'),
            ("0x03170a2e7597b7b7e3d84c05391d139a62b157e78786d8c082f29dcf4c111314", b'test')
        ]

        # Should be encoded sorted by key
        data = obj.encode(value)
        self.assertEqual(
            JamBytes(
                "0x0203170a2e7597b7b7e3d84c05391d139a62b157e78786d8c082f29dcf4c1113140474657374bb30a42c1e62f0afda5f0a4e8a562f7a13a24cea00ee81917b86b89e801314aa020102"
                ),
            data
        )

    def test_map_encode_sort_key_values(self):
        obj = Map(U32, U32).new()
        value = [
            (2, 1),
            (2, 2),
            (1, 2),
            (1, 1)
        ]

        data = obj.encode(value)

        self.assertEqual(
            JamBytes(
                "0x040100000001000000010000000200000002000000010000000200000002000000"
            ),
            data
        )


    def test_map_decode(self):
        obj = Map(U32, Bytes).new()

        obj.decode(JamBytes('0x01020000000474657374'))

        self.assertEqual([(2, '0x74657374')], obj.serialize())
        self.assertEqual({2: b'test'}, obj.to_serializable_obj())




    def test_mapping_type(self):

        class StorageMap(Mapping):
            def __init__(self, initial_data: dict = None):
                if initial_data is None:
                    initial_data = {}
                self.cache = initial_data

            def __getitem__(self, *args):

                if len(args) == 1:
                    args = args[0]

                return self.cache.get(args)

            def __iter__(self):
                return iter(self.cache)

            def __len__(self):
                return len(self.cache)

        obj = Map(U32, Bytes).new()

        data = obj.encode(StorageMap({2: b'test'}))
        self.assertEqual(JamBytes('0x01020000000474657374'), data)

        obj = Map(U32, Bytes).new()

        obj.deserialize(StorageMap({2: b'test'}))

        self.assertEqual(obj.value_object[0][0], 2)



if __name__ == '__main__':
    unittest.main()
