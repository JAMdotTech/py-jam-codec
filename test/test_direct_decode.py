import enum
import unittest
from dataclasses import dataclass, field
from types import MethodType
from unittest.mock import patch

from jamcodec.base import JamBytes, JamCodecType, JamCodecTypeDef
from jamcodec.decoding import decode_to_object
from jamcodec.exceptions import RemainingScaleBytesNotEmptyException, ScaleSerializeException
from jamcodec.mixins import Serializable
from jamcodec.types import (
    Array, Bool, BoundedVec, Bytes, Enum, H256, Map, Null, Option,
    String, Struct, StructObject, Tuple, U8, U16, UnsignedInteger, Vec,
)


def decode_with_wrappers(codec, data):
    """The original binary-to-model route, independent of the optimized mixin."""
    wrapper = codec.new()
    wrapper.decode(data)
    return wrapper.to_serializable_obj()


@dataclass
class Item(Serializable):
    number: int = field(metadata={'codec': U16})
    payload: bytes = field(metadata={'codec': Bytes})


@dataclass
class Packet(Serializable):
    items: list = field(metadata={'codec': BoundedVec(Item.to_codec_def(), 3)})
    optional: object = field(metadata={'codec': Option(Item.to_codec_def())})
    lookup: dict = field(metadata={'codec': Map(U8, Option(Item.to_codec_def()))})
    pair: tuple = field(metadata={'codec': Tuple(U8, Bytes)})
    numbers: list = field(metadata={'codec': Array(U16, 2)})
    fixed: bytes = field(metadata={'codec': Array(U8, 2)})
    digest: bytes = field(metadata={'codec': H256})


@dataclass
class Choice(Serializable):
    item: object = None
    empty: object = None
    _codec_type_def = Enum(item={'id': 19, 'type': Item.to_codec_def()}, empty={'id': 255, 'type': Null})


class Status(Serializable, enum.Enum):
    ready = 10
    finished = 20


class TestDirectDecode(unittest.TestCase):
    def assertEquivalent(self, codec, payload):
        """Compare values, exact Python types, errors, and stream consumption."""
        expected_data = JamBytes(b'\x99' + payload + b'\x42')
        actual_data = JamBytes(expected_data.to_bytes())
        expected_data.offset = actual_data.offset = 1
        try:
            expected = decode_with_wrappers(codec, expected_data)
        except Exception as error:
            with self.assertRaises(type(error)) as caught:
                decode_to_object(codec, actual_data)
            self.assertEqual(str(error), str(caught.exception))
        else:
            actual = decode_to_object(codec, actual_data)
            self.assertEqual(expected, actual)
            self.assertSameTypes(expected, actual)
        self.assertEqual(expected_data.offset, actual_data.offset)

    def assertSameTypes(self, expected, actual):
        self.assertIs(type(expected), type(actual))
        if isinstance(expected, dict):
            for key in expected:
                self.assertSameTypes(expected[key], actual[key])
        elif isinstance(expected, (list, tuple)):
            for left, right in zip(expected, actual):
                self.assertSameTypes(left, right)

    def test_nested_model_and_collection_parity(self):
        value = Packet(
            items=[Item(1, b'first'), Item(258, b'')],
            optional=Item(65535, b'optional'),
            lookup={2: None, 1: Item(7, b'value')},
            pair=(3, b'pair'), numbers=[1, 258], fixed=b'ab', digest=bytes(range(32)),
        )
        payload = value.to_jam_bytes().to_bytes()
        self.assertEquivalent(Packet.to_codec_def(), payload)
        stream = JamBytes(b'\x99' + payload + b'\x42')
        stream.offset = 1
        decoded = Packet.from_jam_bytes(stream)
        self.assertEqual(value, decoded)
        self.assertIs(type(decoded.fixed), bytearray)
        self.assertEqual(bytearray(b'\x42'), stream.get_remaining_bytes())

    def test_leaf_values_and_byte_collection_types(self):
        cases = (
            (Null, b''), (Bool(), b'\x01'), (Bytes, b'\x02ab'),
            (String, b'\x02ab'), (String, b'\x01\xff'), (H256, bytes(32)),
            (Array(U8, 2), b'ab'), (Array(U16, 2), b'\x01\x00\x02\x00'),
            (Vec(U16), b'\x02\x01\x00\x02\x00'),
            (BoundedVec(U8, 2), b'\x02ab'),
            (Option(Null), b'\x01'), (Option(U16), b'\x00'),
            # Existing Option accepts every nonzero tag as Some.
            (Option(U16), b'\x02\x01\x00'),
        )
        for codec, payload in cases:
            with self.subTest(codec=type(codec).__name__, payload=payload):
                self.assertEquivalent(codec, payload)
        self.assertIs(Null, decode_to_object(Null, JamBytes(b'')))

    def test_enum_model_and_explicit_discriminants(self):
        for value in (Choice(item=Item(258, b'x')), Choice(empty=Null)):
            with self.subTest(value=value):
                self.assertEquivalent(Choice.to_codec_def(), value.to_jam_bytes().to_bytes())
                self.assertEqual(value, Choice.from_jam_bytes(value.to_jam_bytes()))
        self.assertEqual(('finished', None), Status.from_jam_bytes(JamBytes(b'\x01')))
        self.assertEquivalent(Status.to_codec_def(), b'\x00')
        self.assertEquivalent(Choice.to_codec_def(), b'\xfe')

    def test_preserves_existing_single_tuple_and_byte_vec_behavior(self):
        # These routes have unusual legacy behavior; optimizing decode must
        # preserve it rather than silently change their model representation.
        for codec, payload in ((Tuple(U8), b'\x03'), (Vec(U8), b'\x02ab')):
            with self.subTest(codec=type(codec).__name__):
                self.assertEquivalent(codec, payload)

    def test_map_duplicate_keys_keep_last_value(self):
        codec = Map(U8, U16)
        payload = b'\x02\x03\x01\x00\x03\x02\x00'
        self.assertEquivalent(codec, payload)
        self.assertEqual({3: 2}, decode_to_object(codec, JamBytes(payload)))

    def test_truncated_or_invalid_data_preserves_errors_and_cursor(self):
        cases = (
            (Bool(), b'\x02'), (U16, b''), (Bytes, b'\x05a'),
            (Array(U8, 3), b'a'), (Vec(U16), b'\x02\x01\x00'),
            (Map(U8, U16), b'\x01\x01'),
            (Item.to_codec_def(), b'\x01\x00\x03a'),
            (Choice.to_codec_def(), b'\x13\x01'),
            (BoundedVec(U16, 3), b'\x80'),
        )
        for codec, payload in cases:
            with self.subTest(codec=type(codec).__name__, payload=payload):
                self.assertEquivalent(codec, payload)

    def test_bounded_vec_checks_length_before_creating_elements(self):
        class NoElementAllocation(JamCodecTypeDef):
            def new(self, **kwargs):
                raise AssertionError('Invalid count must be rejected first')

        codec = BoundedVec(NoElementAllocation(), maximum=4, minimum=2, multiple=2)
        for payload in (b'\x00', b'\x01', b'\x03', b'\x05', b'\x80\x02', b'\xff' + b'\xff' * 8):
            with self.subTest(payload=payload):
                self.assertEquivalent(codec, payload)
                with self.assertRaises(ValueError):
                    decode_to_object(codec, JamBytes(payload))

    def test_bounded_vec_inclusive_limits_and_nested_bytes(self):
        codec = BoundedVec(U16, maximum=4, minimum=2, multiple=2)
        for count in (2, 4):
            self.assertEquivalent(codec, codec.encode(list(range(count))).to_bytes())
        nested = BoundedVec(BoundedVec(U8, maximum=4, minimum=2, multiple=2), maximum=2)
        payload = nested.encode([b'ab', b'cdef']).to_bytes()
        self.assertEquivalent(nested, payload)
        self.assertEqual([b'ab', b'cdef'], decode_to_object(nested, JamBytes(payload)))

    def test_custom_type_definition_hooks_are_preserved(self):
        events = []

        class CustomByte(UnsignedInteger):
            def decode(self, data):
                events.append('decode')
                return super().decode(data) + 1

            def serialize(self, value):
                events.append('serialize')
                if value == 256:
                    raise ScaleSerializeException('custom serialization validation')
                return super().serialize(value)

            def to_serializable_obj(self, value):
                events.append('to_object')
                return value + 100

        codec = CustomByte(8)
        self.assertEquivalent(Vec(codec), b'\x01\x02')
        events.clear()
        self.assertEqual(103, decode_to_object(codec, JamBytes(b'\x02')))
        self.assertEqual(['decode', 'serialize', 'to_object'], events)
        self.assertEquivalent(codec, b'\xff')

    def test_custom_wrapper_hooks_and_impl_updates_are_preserved(self):
        events = []

        class CustomWrapper(StructObject):
            def decode(self, data, check_remaining=False):
                events.append('decode')
                return super().decode(data, check_remaining)

            def serialize(self):
                events.append('serialize')
                return super().serialize()

            def to_serializable_obj(self):
                events.append('to_object')
                value = super().to_serializable_obj()
                value.number += 100
                return value

        @dataclass
        class CustomPacket(Serializable):
            number: int
            _codec_type_def = Struct(number=U8)

        self.assertEqual(CustomPacket(2), CustomPacket.from_jam_bytes(JamBytes(b'\x02')))
        CustomPacket.to_codec_def().impl(CustomWrapper)
        events.clear()
        self.assertEqual(CustomPacket(102), CustomPacket.from_jam_bytes(JamBytes(b'\x02')))
        self.assertEqual(['decode', 'serialize', 'to_object'], events)
        self.assertEquivalent(CustomPacket.to_codec_def(), b'\x02')
        nested = Vec(CustomPacket.to_codec_def())
        self.assertEqual([CustomPacket(102)], decode_to_object(nested, JamBytes(b'\x01\x02')))

    def test_custom_from_codec_type_runs_only_at_root(self):
        @dataclass
        class Adjusted(Serializable):
            number: int = field(metadata={'codec': U8})

            @classmethod
            def from_codec_type(cls, wrapper):
                value = super().from_codec_type(wrapper)
                value.number += 100
                return value

        @dataclass
        class Container(Serializable):
            value: Adjusted = field(metadata={'codec': Adjusted.to_codec_def()})

        self.assertEqual(Adjusted(102), Adjusted.from_jam_bytes(JamBytes(b'\x02')))
        self.assertEqual(Container(Adjusted(2)), Container.from_jam_bytes(JamBytes(b'\x02')))

    def test_nested_model_validation_runs_after_decoding_the_root(self):
        @dataclass
        class ValidatedItem(Serializable):
            number: int = field(metadata={'codec': U8})

            def __post_init__(self):
                if self.number == 0:
                    raise ValueError('number must be positive')

        @dataclass
        class Envelope(Serializable):
            item: ValidatedItem = field(metadata={'codec': ValidatedItem.to_codec_def()})
            tail: int = field(metadata={'codec': U16})

        # The original route consumes the tail before model construction fails.
        self.assertEquivalent(Envelope.to_codec_def(), b'\x00\x02\x01')

    def test_nested_custom_conversion_runs_after_decoding_the_root(self):
        class RejectedByte(UnsignedInteger):
            def to_serializable_obj(self, value):
                raise ValueError('custom conversion rejection')

        @dataclass
        class Envelope(Serializable):
            item: int = field(metadata={'codec': RejectedByte(8)})
            tail: int = field(metadata={'codec': U16})

        self.assertEquivalent(Envelope.to_codec_def(), b'\x01\x02\x01')

    def test_decoded_results_and_input_buffers_remain_independent(self):
        codec = BoundedVec(Array(U8, 2), maximum=2)
        first_data = JamBytes(b'\x02abcd')
        first = decode_to_object(codec, first_data)
        second = decode_to_object(codec, JamBytes(b'\x02abcd'))
        first[0][0] = ord('z')
        first.append(bytearray(b'ef'))
        first_data.data[1] = ord('y')
        self.assertEqual([bytearray(b'ab'), bytearray(b'cd')], second)
        self.assertEqual(bytearray(b'zb'), first[0])

    def test_mutable_codec_definitions_are_not_frozen_by_first_decode(self):
        @dataclass
        class MutablePacket(Serializable):
            number: int
            _codec_type_def = Struct(number=U8)

        self.assertEqual(MutablePacket(1), MutablePacket.from_jam_bytes(JamBytes(b'\x01')))
        codec = MutablePacket.to_codec_def()
        codec.arguments['number'] = U16
        self.assertEqual(MutablePacket(258), MutablePacket.from_jam_bytes(JamBytes(b'\x02\x01')))
        self.assertEquivalent(codec, b'\x02\x01')

    def test_builtin_instance_hooks_are_preserved(self):
        for hook in ('decode', 'serialize', 'to_serializable_obj'):
            with self.subTest(hook=hook):
                codec = UnsignedInteger(8)
                original = getattr(codec, hook)
                calls = []

                def custom(self, value):
                    calls.append(hook)
                    return original(value) + 10

                setattr(codec, hook, MethodType(custom, codec))
                self.assertEquivalent(codec, b'\x02')
                calls.clear()
                decoded = decode_to_object(codec, JamBytes(b'\x02'))
                # Serialization is a validation hook; the model value still
                # comes from decode and to_serializable_obj.
                self.assertEqual(2 if hook == 'serialize' else 12, decoded)
                self.assertEqual([hook], calls)

    def test_builtin_factory_updates_after_first_decode_are_preserved(self):
        class AdjustedWrapper(JamCodecType):
            def to_serializable_obj(self):
                return super().to_serializable_obj() + 100

        codec = UnsignedInteger(8)
        self.assertEqual(2, decode_to_object(codec, JamBytes(b'\x02')))
        calls = []

        def custom_factory(self, **kwargs):
            calls.append('new')
            return AdjustedWrapper(type_def=self, **kwargs)

        codec.new = MethodType(custom_factory, codec)
        self.assertEqual(102, decode_to_object(codec, JamBytes(b'\x02')))
        self.assertEqual(['new'], calls)
        self.assertEquivalent(codec, b'\x02')

    def test_builtin_class_serialization_validation_is_preserved(self):
        original = UnsignedInteger.serialize

        def checked(self, value):
            if value == 255:
                raise ScaleSerializeException('class serialization validation')
            return original(self, value)

        with patch.object(UnsignedInteger, 'serialize', checked):
            self.assertEquivalent(Vec(U16), b'\x01\xff\x00')
            with self.assertRaisesRegex(ScaleSerializeException, 'class serialization validation'):
                decode_to_object(U8, JamBytes(b'\xff'))

    def test_byte_vectors_preserve_bytes_serialization_validation(self):
        def rejected(value):
            raise ScaleSerializeException('byte vector serialization validation')

        with patch.object(Bytes, 'serialize', rejected):
            for codec in (Vec(U8), BoundedVec(U8, maximum=2)):
                with self.subTest(codec=type(codec).__name__):
                    self.assertEquivalent(codec, b'\x02ab')
                    with self.assertRaisesRegex(ScaleSerializeException, 'byte vector serialization validation'):
                        decode_to_object(codec, JamBytes(b'\x02ab'))

    def test_truncated_trailing_field_prevents_nested_model_construction(self):
        constructed = []

        @dataclass
        class ObservedItem(Serializable):
            number: int = field(metadata={'codec': U8})

            def __post_init__(self):
                constructed.append(self.number)

        @dataclass
        class Envelope(Serializable):
            item: ObservedItem = field(metadata={'codec': ObservedItem.to_codec_def()})
            tail: int = field(metadata={'codec': U16})

        codec = Envelope.to_codec_def()
        # Even though the item is complete, construction must wait until the
        # entire root has decoded successfully.
        for decode in (decode_with_wrappers, decode_to_object):
            with self.subTest(decode=decode.__name__):
                stream = JamBytes(b'\x01\x02')
                with self.assertRaises(RemainingScaleBytesNotEmptyException):
                    decode(codec, stream)
                self.assertEqual(1, stream.offset)
                self.assertEqual([], constructed)


if __name__ == '__main__':
    unittest.main()
