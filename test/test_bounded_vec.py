import unittest
from dataclasses import dataclass, field

from jamcodec.base import JamBytes, JamCodecTypeDef
from jamcodec.exceptions import RemainingScaleBytesNotEmptyException
from jamcodec.mixins import Serializable
from jamcodec.types import BoundedVec, U8, U16, VarInt64, Vec


class NoElementAllocation(JamCodecTypeDef):
    def new(self, **kwargs):
        raise AssertionError('Invalid length must be rejected before creating elements')


@dataclass
class BoundedItem(Serializable):
    number: int = field(metadata={'codec': U16})


@dataclass
class BoundedPacket(Serializable):
    items: list = field(metadata={'codec': BoundedVec(BoundedItem.to_codec_def(), 2, minimum=1)})
    groups: list = field(metadata={'codec': BoundedVec(BoundedVec(U16, 2), 2)})
    payload: bytes = field(metadata={'codec': BoundedVec(U8, 4, minimum=2, multiple=2)})


class TestBoundedVec(unittest.TestCase):

    def test_invalid_constructor_constraints(self):
        invalid = (
            {'maximum': -1},
            {'maximum': 2, 'minimum': -1},
            {'maximum': 2, 'minimum': 3},
            {'maximum': 2, 'multiple': 0},
            {'maximum': 2, 'multiple': -1},
            {'maximum': 2.0},
            {'maximum': 2, 'minimum': '0'},
            {'maximum': 2, 'multiple': 1.0},
            {'maximum': True},
            {'maximum': 2, 'minimum': False},
            {'maximum': 2, 'multiple': True},
        )
        for constraints in invalid:
            with self.subTest(constraints=constraints):
                with self.assertRaises(ValueError):
                    BoundedVec(U16, **constraints)

    def test_inclusive_bounds_and_multiple_roundtrip(self):
        codec = BoundedVec(U16, maximum=6, minimum=2, multiple=2)
        for count in (2, 4, 6):
            with self.subTest(count=count):
                value = list(range(count))
                obj = codec.new()
                encoded = obj.encode(value)
                self.assertEqual(value, codec.new().decode(encoded))
                self.assertEqual(value, codec.new(value=value).serialize())

    def test_empty_vector_with_default_minimum(self):
        codec = BoundedVec(U16, maximum=0)
        self.assertEqual(JamBytes('0x00'), codec.encode([]))
        self.assertEqual([], codec.deserialize([]))
        self.assertEqual([], codec.decode(JamBytes('0x00')))

    def test_encode_rejects_invalid_counts(self):
        codec = BoundedVec(U16, maximum=4, minimum=2, multiple=2)
        for count in (0, 1, 3, 5, 6):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    codec.encode([0] * count)

    def test_deserialize_rejects_invalid_counts(self):
        codec = BoundedVec(U16, maximum=4, minimum=2, multiple=2)
        for count in (0, 1, 3, 5, 6):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    codec.new(value=[0] * count)

    def test_decode_checks_count_before_element_allocation(self):
        codec = BoundedVec(NoElementAllocation(), maximum=4, minimum=2, multiple=2)
        for count in (0, 1, 3, 5, 6):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    codec.decode(VarInt64.encode(count))

    def test_huge_count_is_rejected_before_element_allocation(self):
        codec = BoundedVec(NoElementAllocation(), maximum=4)
        data = VarInt64.encode(2 ** 64 - 1)
        with self.assertRaises(ValueError):
            codec.decode(data)
        self.assertEqual(data.length, data.offset)

    def test_noncanonical_prefix_at_nonzero_offset(self):
        codec = BoundedVec(NoElementAllocation(), maximum=128)
        for prefix in (b'\x80\x00', b'\x80\x01', b'\x80\x7f', b'\xc0\x80\x00', b'\xff' + bytes(8)):
            with self.subTest(prefix=prefix.hex()):
                data = JamBytes(b'\x99' + prefix + b'\x42')
                data.offset = 1
                with self.assertRaises(ValueError):
                    codec.decode(data)
                self.assertEqual(1 + len(prefix), data.offset)

    def test_truncated_prefix_at_nonzero_offset(self):
        codec = BoundedVec(NoElementAllocation(), maximum=128)
        prefixes = [b''] + [bytes([prefix]) + bytes(length - 1) for prefix, length in (
            (0x80, 1), (0xc0, 2), (0xe0, 3), (0xf0, 4),
            (0xf8, 5), (0xfc, 6), (0xfe, 7), (0xff, 8),
        )]
        for prefix in prefixes:
            with self.subTest(prefix=prefix.hex()):
                data = JamBytes(b'\x99' + prefix)
                data.offset = 1
                with self.assertRaises(RemainingScaleBytesNotEmptyException):
                    codec.decode(data)

    def test_wire_encoding_matches_vec_across_prefix_boundary(self):
        codec = BoundedVec(U16, maximum=128)
        for count in (0, 1, 127, 128):
            with self.subTest(count=count):
                value = list(range(count))
                encoded = codec.encode(value)
                self.assertEqual(Vec(U16).encode(value), encoded)
                self.assertEqual(value, codec.new().decode(encoded))

    def test_new_preserves_vec_wrapper_semantics(self):
        codec = BoundedVec(U16, maximum=2)
        self.assertIsInstance(codec, Vec)
        obj = codec.new(value=[1, 258])
        self.assertEqual(2, len(obj))
        self.assertEqual([1, 258], [item.value for item in obj.value_object])
        encoded = obj.encode()
        self.assertEqual(JamBytes('0x0201000201'), encoded)
        decoded = codec.new(scale=encoded)
        self.assertEqual([1, 258], decoded.value)
        self.assertEqual([1, 258], decoded.to_serializable_obj())

    def test_decode_consumes_only_vector_at_nonzero_offset(self):
        data = JamBytes('0x99020100020142')
        data.offset = 1
        self.assertEqual([1, 258], BoundedVec(U16, 2).new().decode(data))
        self.assertEqual(6, data.offset)
        self.assertEqual(bytearray(b'\x42'), data.get_remaining_bytes())

    def test_byte_inputs_use_normalized_cardinality(self):
        codec = BoundedVec(U8, maximum=2, minimum=2, multiple=2)
        for value in (b'\xc3\xa9', bytearray(b'\xc3\xa9'), [195, 169], '0xc3a9', 'é'):
            with self.subTest(value=value):
                self.assertEqual(JamBytes('0x02c3a9'), codec.encode(value))
                self.assertEqual(b'\xc3\xa9', codec.deserialize(value))

    def test_byte_bounds_reject_normalized_lengths(self):
        codec = BoundedVec(U8, maximum=2, minimum=2, multiple=2)
        for value in ('0x00', '0x000102', 'a', 'éa'):
            for operation in (codec.encode, codec.deserialize):
                with self.subTest(value=value, operation=operation.__name__):
                    with self.assertRaises(ValueError):
                        operation(value)

    def test_bytes_decode_and_wrapper_match_vec(self):
        codec = BoundedVec(U8, maximum=2)
        self.assertEqual(b'\xc3\xa9', codec.decode(JamBytes('0x02c3a9')))
        obj = codec.new(scale=JamBytes('0x02c3a9'))
        self.assertEqual(Vec(U8).new().decode(JamBytes('0x02c3a9')), obj.value)
        self.assertEqual('0xc3a9', obj.value)
        self.assertEqual(b'\xc3\xa9', obj.value_object)
        self.assertEqual(b'\xc3\xa9', obj.to_serializable_obj())
        self.assertEqual(JamBytes('0x02c3a9'), obj.encode())

    def test_truncated_element_payload(self):
        for element, payload in ((U16, b'\x02\x01\x00\x02'), (U8, b'\x02\x01')):
            with self.subTest(element=element):
                with self.assertRaises(RemainingScaleBytesNotEmptyException):
                    BoundedVec(element, maximum=2, minimum=1).new().decode(JamBytes(payload))

    def test_nested_serializable_dataclass_roundtrip(self):
        packet = BoundedPacket(
            items=[BoundedItem(1), BoundedItem(258)],
            groups=[[3, 4], []],
            payload=b'\xc3\xa9',
        )
        serialized = {
            'items': [{'number': 1}, {'number': 258}],
            'groups': [[3, 4], []],
            'payload': '0xc3a9',
        }
        self.assertEqual(serialized, packet.serialize())
        self.assertEqual(packet, BoundedPacket.deserialize(serialized))
        self.assertEqual(packet, BoundedPacket.from_jam_bytes(packet.to_jam_bytes()))


if __name__ == '__main__':
    unittest.main()
