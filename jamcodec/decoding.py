"""Binary model decoding without intermediate serialized values."""

import enum

from jamcodec.base import JamBytes, JamCodecType, JamCodecTypeDef
from jamcodec import types
from jamcodec.exceptions import ScaleDecodeException


class _DecodedValue(JamCodecType):
    # Existing model converters (notably Option) recognize JamCodecType values.
    # Only these two fields are needed; models are built after the whole decode.
    __slots__ = ('type_def', 'value_object')

    def __init__(self, type_def, value):
        self.type_def = type_def
        self.value_object = value


_WRAPPERS = {
    types.UnsignedInteger: JamCodecType,
    types.SignedInteger: JamCodecType,
    types.Float: JamCodecType,
    types.Bool: JamCodecType,
    types.NullType: JamCodecType,
    types.CompactDef: JamCodecType,
    types.BitVec: JamCodecType,
    types.BitArray: JamCodecType,
    types.BytesDef: JamCodecType,
    types.StringDef: JamCodecType,
    types.VarInt64Def: JamCodecType,
    types.HashDef: types.HashDefObject,
    types.Struct: types.StructObject,
    types.Tuple: JamCodecType,
    types.Enum: JamCodecType,
    types.Option: JamCodecType,
    types.Vec: types.VecType,
    types.BoundedVec: types.VecType,
    types.Array: types.ArrayObject,
    types.Map: JamCodecType,
}
_CONTAINERS = frozenset((
    types.Struct, types.Tuple, types.Enum, types.Option,
    types.Vec, types.BoundedVec, types.Array, types.Map,
))

# A custom hook must still see a normal codec wrapper, including its serialized
# value and stream offsets. Do not cache plans: definitions remain mutable.
_HOOK_NAMES = frozenset(('new', 'decode', 'serialize', 'to_serializable_obj', '_check_count'))
_BUILTINS = {
    cls: (
        wrapper,
        (cls.new, cls.decode, cls.serialize, cls.to_serializable_obj),
        (wrapper.decode, wrapper.serialize, wrapper.to_serializable_obj),
    )
    for cls, wrapper in _WRAPPERS.items()
}


def _decode_value(codec, data):
    cls = type(codec)
    wrapper, type_methods, wrapper_methods = _BUILTINS.get(cls, (None, None, None))
    if (
        wrapper is None
        or codec.scale_type_cls is not wrapper
        or not _HOOK_NAMES.isdisjoint(codec.__dict__)
        or (cls.new, cls.decode, cls.serialize, cls.to_serializable_obj) != type_methods
        or (wrapper.decode, wrapper.serialize, wrapper.to_serializable_obj) != wrapper_methods
        # Python enums expose their codec tuple rather than constructing a model.
        or (cls is types.Enum and codec._deserialize_type is not None
            and issubclass(codec._deserialize_type, enum.Enum))
    ):
        value = codec.new()
        value.decode(data)
        return value

    if cls not in _CONTAINERS:
        # Primitive decoders already enforce their wire-format validation.
        value = codec.decode(data)
    elif cls is types.Struct:
        value = {name: _decode_value(child, data) for name, child in codec.arguments.items()}
    elif cls is types.Tuple:
        if len(codec.values) == 1:
            value = _decode_value(codec.values[0], data)
        else:
            value = tuple(_decode_value(child, data) for child in codec.values)
    elif cls is types.Enum:
        index = int.from_bytes(data.get_next_bytes(1), byteorder='little')
        for variant_index, (name, child) in enumerate(codec.variants.items()):
            if type(child) is dict:
                variant_index = child.get('id', variant_index)
                child = child.get('type', child)
            if index == variant_index:
                value = (name, _decode_value(child, data) if child is not None else None)
                break
        else:
            raise ScaleDecodeException(f"Index '{index}' not present in Enum type mapping")
    elif cls is types.Option:
        value = None if data.get_next_bytes(1) == b'\x00' else _decode_value(codec.some, data)
    elif cls in (types.Vec, types.BoundedVec):
        if codec.type_def is types.U8:
            # Byte vectors also delegate serialization hooks to the Bytes codec.
            value = codec.new()
            value.decode(data)
            return value
        start = data.offset
        count = types.VarInt64.decode(data)
        if cls is types.BoundedVec:
            if data.data[start:data.offset] != types.VarInt64.encode(count).data:
                raise ValueError('non-canonical sequence length')
            codec._check_count(count)
        value = [_decode_value(codec.type_def, data) for _ in range(count)]
    elif cls is types.Array:
        value = (codec.decode(data) if codec.type_def is types.U8 else
                 [_decode_value(codec.type_def, data) for _ in range(codec.length)])
    elif cls is types.Map:
        count = types.VarInt64.decode(data)
        value = [(_decode_value(codec.key_def, data), _decode_value(codec.value_def, data))
                 for _ in range(count)]
    return _DecodedValue(codec, value)


def decode_to_object(codec: JamCodecTypeDef, data: JamBytes):
    """Decode a model while preserving the normal wrapper path for custom codecs."""
    return _decode_value(codec, data).to_serializable_obj()
