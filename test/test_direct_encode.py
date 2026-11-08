from dataclasses import dataclass, field
from types import MethodType
from unittest.mock import patch

import pytest

from jamcodec.base import JamBytes, JamCodecType
from jamcodec.encoding import encode_from_object
from jamcodec.exceptions import ScaleDeserializeException
from jamcodec.mixins import Serializable
from jamcodec.types import (
    Array, BitArray, Bool, BoundedVec, Bytes, BytesDef, Enum, F32, F64, H256, I16, Map, Null,
    Option, Struct, StructObject, Tuple, U8, U16, U32, UnsignedInteger, VarInt64, Vec,
)


def legacy_encode(value):
    """The binary encoding path before direct normalization was introduced."""
    wrapper = value.to_codec_type()
    if type(wrapper) in (JamCodecType, StructObject):
        return wrapper.type_def.encode(wrapper.value_serialized)
    return wrapper.encode()


def assert_matches_legacy(value):
    assert_encoding_matches_legacy(value)
    # Exercise the collection path too when the original model is a mixed
    # record, which deliberately keeps the normal wrapper path at the root.
    assert_encoding_matches_legacy(model(Vec(value.to_codec_def()), [value]))


def assert_encoding_matches_legacy(value):
    try:
        expected = legacy_encode(value)
    except Exception as error:
        with pytest.raises(type(error)) as caught:
            value.to_jam_bytes()
        assert str(caught.value) == str(error)
    else:
        actual = value.to_jam_bytes()
        assert actual.to_bytes() == expected.to_bytes()
        assert actual.offset == 0
        assert actual.length == expected.length


@dataclass
class Item(Serializable):
    number: int = field(metadata={'codec': U16})
    payload: bytes = field(metadata={'codec': Bytes})


@dataclass
class Choice(Serializable):
    item: object = None
    empty: object = None
    _codec_type_def = Enum(item={'id': 17, 'type': Item.to_codec_def()}, empty={'id': 255, 'type': Null})


@dataclass
class Packet(Serializable):
    records: list = field(metadata={'codec': BoundedVec(Item.to_codec_def(), 3, minimum=1)})
    optional: object = field(metadata={'codec': Option(Item.to_codec_def())})
    lookup: dict = field(metadata={'codec': Map(Tuple(H256, U16), Option(Bytes))})
    pair: tuple = field(metadata={'codec': Tuple(U8, Array(U16, 2))})
    fixed: bytes = field(metadata={'codec': Array(U8, 2)})
    bits: list = field(metadata={'codec': BitArray(9)})
    choice: Choice = field(metadata={'codec': Choice.to_codec_def()})


@pytest.mark.parametrize('choice', [Choice(item=Item(7, b'item')), Choice(empty=Null)])
def test_standard_nested_models_use_direct_normalization(choice):
    value = Packet(
        [Item(1, b'first'), Item(258, b'')], Item(65535, b'optional'),
        {(bytes(32), 2): None, (b'\xff' * 32, 1): b'value'},
        (3, [1, 258]), bytearray(b'ab'), [True] * 9, choice,
    )
    collection = model(Vec(Packet.to_codec_def()), [value])
    assert encode_from_object(collection.to_codec_def(), collection) is not None
    assert_matches_legacy(value)


def model(codec, value):
    @dataclass
    class Value(Serializable):
        item: object = field(metadata={'codec': codec})

    return Value(value)


@pytest.mark.parametrize('codec,value', [
    (Array(U8, 2), [1, 255]),
    (Array(U8, 2), 'é'),
    (Array(U8, 2), '0x01ff'),
    (Array(U16, 2), [1, 258]),
    (Tuple(U16), 258),
    (Tuple(U8, U16), [1, 258, 999]),
    (Vec(U16), (1, 258)),
    (Vec(U8), 'é'),
    (BoundedVec(U8, 2, minimum=2, multiple=2), 'é'),
    (Option(Null), Null),
    (Option(Option(U16)), None),
    (Bytes, [0, 255]),
    (Bytes, '0x00ff'),
    (H256, bytearray(range(32))),
    (BitArray(9), [False] * 9),
])
def test_accepted_input_representations_match(codec, value):
    assert_matches_legacy(model(codec, value))


@pytest.mark.parametrize('codec,value', [
    (U8, True), (U8, '1'), (U8, 256), (H256, b'short'), (H256, 7),
    (Array(U8, 2), [256, 1]), (Array(U8, 2), [True, 1]),
    (Array(U8, 2), b'x'), (Array(U16, 2), b'ab'), (Tuple(U8, U16), [1]),
    (BoundedVec(U16, 4, minimum=2, multiple=2), [1, 2, 3]),
    (BoundedVec(U8, 2, minimum=2), 'éa'), (Bytes, '0xgg'),
    (BitArray(9), ['x']),
])
def test_validation_errors_match(codec, value):
    assert_matches_legacy(model(codec, value))


@pytest.mark.parametrize('first,second,first_codec,second_codec', [
    (256, 7, U8, H256),
    (256, '0xgg', U8, Bytes),
    (b'short', 'not an integer', H256, U8),
    ([256, 1], 'not an integer', Array(U8, 2), U8),
])
def test_all_normalization_finishes_before_binary_validation(first, second, first_codec, second_codec):
    @dataclass
    class Invalid(Serializable):
        first: object = field(metadata={'codec': first_codec})
        second: object = field(metadata={'codec': second_codec})

    assert_matches_legacy(Invalid(first, second))


@pytest.mark.parametrize('first,first_codec', [
    ([256, 1], Vec(U8)),
    ([256, 1], BoundedVec(U8, 1)),
    (1e100, F32),
    (-1, VarInt64),
    ([(1, None), (1, b'x')], Map(U8, Option(Bytes))),
])
def test_early_binary_errors_defer_to_later_normalization_errors(first, first_codec):
    @dataclass
    class Invalid(Serializable):
        first: object = field(metadata={'codec': first_codec})
        second: object = field(metadata={'codec': H256})

    assert_matches_legacy(Invalid(first, 7))


@pytest.mark.parametrize('codec,value', [
    (Vec(U8), b'abc'),
    (Array(U8, 2), [1, 255]),
    (Array(U16, 2), [1, 65535]),
    (Array(H256, 2), [bytes(32), b'\xff' * 32]),
    (BoundedVec(H256, 3), [bytes(32)]),
    (Vec(I16), [-32768, 32767]),
    (Vec(F32), [0.5, float('inf')]),
    (Vec(F64), [0.5, float('nan')]),
    (Tuple(Bool(), U32), (True, 2**32 - 1)),
    (Option(Option(Null)), Null),
])
def test_native_values_use_the_direct_path(codec, value):
    value = model(codec, value)
    value = model(Vec(value.to_codec_def()), [value])
    assert encode_from_object(value.to_codec_def(), value) == legacy_encode(value)


@pytest.mark.parametrize('codec,value', [
    (Map(Bytes, Bytes), [(b'key', b'z'), (b'key', b'a')]),
    (Map(Option(Bytes), U8), [(None, 1), (b'x', 2)]),
    (Map(U8, Option(H256)), [(1, None), (1, bytes(32))]),
    (Map(Array(U8, 2), U8), [(bytearray(b'ab'), 1), (b'aa', 2)]),
    (Map(U8, Enum(a=None, b=None)), [(1, 'b'), (1, 'a')]),
    (Map(U8, U8), [(1, 2, 3)]),
])
def test_map_sorting_uses_the_legacy_serialized_representations(codec, value):
    assert_matches_legacy(model(codec, value))


def test_custom_codec_hooks_run_once_and_in_the_original_order():
    events = []

    class CustomByte(UnsignedInteger):
        def deserialize(self, value):
            events.append('deserialize')
            return super().deserialize(value) + 1

        def serialize(self, value):
            events.append('serialize')
            return value + 10

        def encode(self, value):
            events.append('encode')
            return super().encode(value)

    @dataclass
    class Value(Serializable):
        first: bytes = field(metadata={'codec': Bytes})
        custom: int = field(metadata={'codec': CustomByte(8)})

    value = Value(b'first', 2)
    expected = legacy_encode(value)
    events.clear()
    assert value.to_jam_bytes() == expected
    assert events == ['deserialize', 'serialize', 'encode']


def test_custom_root_wrapper_keeps_post_encode_validation():
    events = []

    class Wrapper(StructObject):
        def deserialize(self, value):
            events.append(('deserialize', self._data is not None))
            return super().deserialize(value)

        def encode(self, value=None):
            events.append(('encode',))
            return JamBytes(b'\xaa' + super().encode(value).to_bytes())

    @dataclass
    class Value(Serializable):
        number: int
        _codec_type_def = Struct(number=U8).impl(Wrapper)

    expected = legacy_encode(Value(7))
    events.clear()
    assert Value(7).to_jam_bytes() == expected
    assert events == [('deserialize', False), ('encode',), ('deserialize', True)]


def test_custom_to_codec_type_is_called_once():
    calls = []

    @dataclass
    class Value(Serializable):
        number: int = field(metadata={'codec': U8})

        def to_codec_type(self):
            calls.append('to_codec_type')
            return super().to_codec_type()

    assert Value(7).to_jam_bytes().to_bytes() == b'\x07'
    assert calls == ['to_codec_type']


def test_replaced_base_to_codec_type_is_called_once():
    original = Serializable.to_codec_type
    calls = []

    def custom(self):
        calls.append('to_codec_type')
        return original(self)

    with patch.object(Serializable, 'to_codec_type', custom):
        assert model(Vec(U16), [1, 258]).to_jam_bytes() == JamBytes(b'\x02\x01\x00\x02\x01')
    assert calls == ['to_codec_type']


def test_mutable_definitions_and_wrapper_changes_are_not_cached_between_calls():
    @dataclass
    class Value(Serializable):
        number: int
        _codec_type_def = Struct(number=U8)

    assert Value(7).to_jam_bytes().to_bytes() == b'\x07'
    Value.to_codec_def().arguments['number'] = U16
    assert Value(258).to_jam_bytes().to_bytes() == b'\x02\x01'

    class Prefix(StructObject):
        def encode(self, value=None):
            return JamBytes(b'\xaa' + super().encode(value).to_bytes())

    Value.to_codec_def().impl(Prefix)
    assert Value(258).to_jam_bytes().to_bytes() == b'\xaa\x02\x01'


@pytest.mark.parametrize('hook', ['deserialize', 'serialize', 'encode'])
def test_builtin_instance_hooks_are_preserved(hook):
    codec = UnsignedInteger(8)
    value = model(codec, 2)
    assert value.to_jam_bytes().to_bytes() == b'\x02'
    calls = []
    original = getattr(codec, hook)

    def custom(self, item):
        calls.append(hook)
        return original(item)

    setattr(codec, hook, MethodType(custom, codec))
    expected = legacy_encode(value)
    calls.clear()
    assert value.to_jam_bytes() == expected
    assert calls == [hook]


def test_class_serialization_hooks_preserve_validation():
    original = UnsignedInteger.serialize

    def checked(self, value):
        if value == 255:
            raise ScaleDeserializeException('class validation')
        return original(self, value)

    with patch.object(UnsignedInteger, 'serialize', checked):
        assert_matches_legacy(model(Vec(U16), [1, 255]))


def test_byte_vectors_preserve_indirect_bytes_hooks():
    def reject(self, value):
        raise ScaleDeserializeException('indirect byte validation')

    with patch.object(Bytes, 'serialize', MethodType(reject, Bytes)):
        assert_matches_legacy(model(BoundedVec(U8, 4), b'ab'))


def test_custom_iterable_is_consumed_once():
    for use_generator in (False, True):
        calls = []

        class Values(list):
            def __iter__(self):
                calls.append('iterate')
                return super().__iter__()

        def generate():
            calls.append('iterate')
            yield 1
            yield 258

        value = model(Vec(U16), generate() if use_generator else Values([1, 258]))
        assert value.to_jam_bytes().to_bytes() == b'\x02\x01\x00\x02\x01'
        assert calls == ['iterate']


def test_fallback_precedes_custom_attribute_access_and_schema_mutation():
    def make():
        calls = []
        payload_codec = BytesDef()
        encode = payload_codec.encode

        @dataclass
        class Nested(Serializable):
            number: int = field(metadata={'codec': U8})

        def read_number(self):
            calls.append('get_number')

            def require_hex(self, value):
                assert type(value) is str
                return encode(value)

            payload_codec.encode = MethodType(require_hex, payload_codec)
            return self.__dict__['number']

        value = Nested(7)
        Nested.number = property(read_number)

        @dataclass
        class Outer(Serializable):
            payload: bytes = field(metadata={'codec': payload_codec})
            nested: Nested = field(metadata={'codec': Nested.to_codec_def()})

        return Outer(b'abc', value), calls

    old, old_calls = make()
    expected = legacy_encode(old)
    new, new_calls = make()
    assert new.to_jam_bytes() == expected
    assert old_calls == new_calls == ['get_number']


def test_custom_truthiness_is_not_invoked_during_fast_path_probing():
    calls = []

    class Integer(int):
        def __bool__(self):
            calls.append('bool')
            return True

    value = model(U8, Integer(7))
    with pytest.raises(ValueError, match='Value must be an integer'):
        value.to_jam_bytes()
    assert calls == ['bool']


def test_custom_truthiness_in_a_collection_is_invoked_once():
    calls = []

    class Integer(int):
        def __bool__(self):
            calls.append('bool')
            return True

    value = model(Vec(U16), [Integer(7)])
    with pytest.raises(ValueError, match='Value must be an integer'):
        value.to_jam_bytes()
    assert calls == ['bool']


def test_direct_encoding_does_not_mutate_input_collections_or_buffers():
    @dataclass
    class Collection(Serializable):
        numbers: list = field(metadata={'codec': Array(U16, 2)})
        hashes: list = field(metadata={'codec': Vec(H256)})
        lookup: dict = field(metadata={'codec': Map(Bytes, Bytes)})

    numbers = [1, 258]
    digest = bytearray(range(32))
    hashes = [digest]
    lookup = {b'z': b'last', b'a': b'first'}
    value = Collection(numbers, hashes, lookup)
    first = value.to_jam_bytes()
    assert first == legacy_encode(value)
    assert value.numbers is numbers and numbers == [1, 258]
    assert value.hashes is hashes and hashes[0] is digest and digest == bytearray(range(32))
    assert value.lookup is lookup and list(lookup) == [b'z', b'a']
    numbers[0] = 2
    digest[0] = 255
    assert first != value.to_jam_bytes()


@pytest.mark.parametrize('kind', ['array', 'vec', 'bounded', 'map'])
def test_empty_collections_do_not_construct_elements(kind):
    class NoElement(UnsignedInteger):
        def new(self, **kwargs):
            raise AssertionError('An empty collection must not construct elements')

    child = NoElement(8)
    codec = {
        'array': Array(child, 0),
        'vec': Vec(child),
        'bounded': BoundedVec(child, 0),
        'map': Map(child, child),
    }[kind]
    value = model(codec, {} if kind == 'map' else [])
    assert encode_from_object(value.to_codec_def(), value) == legacy_encode(value)
