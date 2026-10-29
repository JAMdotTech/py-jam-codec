import pytest

from jamcodec.base import JamBytes
from jamcodec.types import Array, Map, Struct, Tuple, U16, Vec


@pytest.mark.parametrize("codec,value,expected", [
    (Struct(first=U16, second=U16), {"first": 1, "second": 2}, b"\x01\x00\x02\x00"),
    (Tuple(U16, U16), (1, 2), b"\x01\x00\x02\x00"),
    (Array(U16, 2), [1, 2], b"\x01\x00\x02\x00"),
    (Vec(U16), [1, 2], b"\x02\x01\x00\x02\x00"),
    (Map(U16, U16), {2: 1, 1: 2}, b"\x02\x01\x00\x02\x00\x02\x00\x01\x00"),
])
def test_collection_encoding_has_complete_readable_buffer(codec, value, expected):
    encoded = codec.encode(value)

    assert encoded.to_bytes() == expected
    assert encoded.offset == 0
    assert encoded.length == len(expected)
    codec.new().decode(encoded, check_remaining=True)
    assert encoded.get_remaining_length() == 0


def test_vec_does_not_mutate_or_share_preencoded_item_buffer():
    item = JamBytes(b"\x01\x00")
    item.get_next_bytes(1)
    encoded = Vec(U16).encode([item, item])

    assert item.to_bytes() == b"\x01\x00"
    assert item.offset == 1
    assert encoded.to_bytes() == b"\x02\x01\x00\x01\x00"
    item.data[0] = 9
    assert encoded.to_bytes() == b"\x02\x01\x00\x01\x00"
    encoded.data[1] = 7
    assert item.to_bytes() == b"\x09\x00"
