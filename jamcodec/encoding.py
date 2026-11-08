"""Prepare standard model values for binary encoding without codec wrappers."""

import dataclasses
import struct
from types import GetSetDescriptorType

from jamcodec import types
from jamcodec.base import JamBytes, JamCodecType


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
_TYPE_METHODS = {
    cls: (cls.new, cls.deserialize, cls.serialize, cls.encode,
          getattr(cls, '_check_count', None))
    for cls in _WRAPPERS
}
_WRAPPER_METHODS = {
    cls: (cls.__init__, cls.deserialize, cls.serialize, cls.encode,
          cls.__getattribute__, cls.__setattr__, cls.value)
    for cls in set(_WRAPPERS.values())
}
_HOOK_NAMES = frozenset(('new', 'deserialize', 'serialize', 'encode', '_check_count'))
_PRIMITIVES = frozenset(_WRAPPERS) - {
    types.Struct, types.Tuple, types.Enum, types.Option,
    types.Vec, types.BoundedVec, types.Array, types.Map,
}
_INTEGERS = frozenset((types.UnsignedInteger, types.SignedInteger, types.CompactDef, types.VarInt64Def))
_MODEL_HOOKS = frozenset(('__getattr__', '__bool__', '__len__'))


class _UseWrappers(Exception):
    pass


class _Encoder:
    def __init__(self):
        self.checked = set()
        self.checked_types = set()
        self.checked_wrappers = set()
        self.model_fields = {}
        self.active = set()
        self.data = bytearray()

    def check(self, codec):
        cls = type(codec)
        if id(codec) in self.checked:
            return cls
        wrapper = _WRAPPERS.get(cls)
        if (wrapper is None or codec.scale_type_cls is not wrapper
                or not _HOOK_NAMES.isdisjoint(codec.__dict__)):
            raise _UseWrappers
        if cls not in self.checked_types:
            if (cls.new, cls.deserialize, cls.serialize, cls.encode,
                    getattr(cls, '_check_count', None)) != _TYPE_METHODS[cls]:
                raise _UseWrappers
            self.checked_types.add(cls)
        if wrapper not in self.checked_wrappers:
            if (wrapper.__init__, wrapper.deserialize, wrapper.serialize, wrapper.encode,
                    wrapper.__getattribute__, wrapper.__setattr__, wrapper.value) != _WRAPPER_METHODS[wrapper]:
                raise _UseWrappers
            self.checked_wrappers.add(wrapper)

        if cls is types.Struct:
            if type(codec.arguments) is not dict or any(type(name) is not str for name in codec.arguments):
                raise _UseWrappers
        elif cls is types.Enum:
            if (type(codec.variants) is not dict or
                    (codec._deserialize_type is not None and type(codec._deserialize_type) is not type)):
                raise _UseWrappers
            if any(type(name) is not str for name in codec.variants):
                raise _UseWrappers
        elif cls is types.Tuple:
            if type(codec.values) not in (list, tuple):
                raise _UseWrappers
        elif cls in (types.Vec, types.BoundedVec, types.Array):
            if cls is types.Array and type(codec.length) is not int:
                raise _UseWrappers
            if cls is types.BoundedVec and any(type(bound) is not int for bound in (
                codec.minimum, codec.maximum, codec.multiple,
            )):
                raise _UseWrappers
            if cls in (types.Vec, types.BoundedVec):
                self.check(types.VarInt64)
                if codec.type_def is types.U8:
                    self.check(types.Bytes)
        elif cls is types.Map:
            self.check(types.VarInt64)
        elif cls in (types.BytesDef, types.StringDef, types.BitVec):
            self.check(types.VarInt64)
        elif cls in (types.UnsignedInteger, types.SignedInteger, types.HashDef):
            if (type(codec.byte_count) is not int
                    or type(codec.bits) is not int):
                raise _UseWrappers
        elif cls is types.Float:
            if type(codec.struct_format) is not str:
                raise _UseWrappers
        elif cls is types.BitArray:
            if type(codec.length) is not int or type(codec.strict_decoding) is not bool:
                raise _UseWrappers
        self.checked.add(id(codec))
        return cls

    def fields(self, value):
        """Read plain dataclass fields without invoking user-defined accessors."""
        cls = type(value)
        if type(cls) is not type or not dataclasses.is_dataclass(cls):
            raise _UseWrappers
        if cls not in self.model_fields:
            if (cls.__getattribute__ is not object.__getattribute__ or
                    issubclass(cls, JamCodecType)):
                raise _UseWrappers
            names = tuple(field.name for field in dataclasses.fields(cls))
            remaining = set(names)
            dictionary = None
            for base in cls.__mro__:
                attributes = vars(base)
                if not _MODEL_HOOKS.isdisjoint(attributes):
                    raise _UseWrappers
                if dictionary is None and '__dict__' in attributes:
                    dictionary = attributes['__dict__']
                for name in remaining.intersection(attributes):
                    if hasattr(type(attributes[name]), '__get__'):
                        raise _UseWrappers
                    remaining.remove(name)
            if type(dictionary) is not GetSetDescriptorType:
                raise _UseWrappers
            self.model_fields[cls] = names
        values = object.__getattribute__(value, '__dict__')
        names = self.model_fields[cls]
        if any(name not in values for name in names):
            raise _UseWrappers
        return values if len(values) == len(names) else {name: values[name] for name in names}

    def plain_leaf(self, value):
        cls = type(value)
        if cls in (bytes, bytearray, int, float, bool, str, type(None)):
            return
        if value is types.Null and not any(
            name in base.__dict__ for base in cls.__mro__ for name in ('__bool__', '__len__')
        ):
            return
        if id(value) in self.active:
            raise _UseWrappers
        self.active.add(id(value))
        try:
            if cls in (list, tuple):
                for item in value:
                    self.plain_leaf(item)
            elif cls is dict:
                for key, item in value.items():
                    self.plain_leaf(key)
                    self.plain_leaf(item)
            else:
                raise _UseWrappers
        finally:
            self.active.remove(id(value))

    def primitive(self, codec, cls, value, native_bytes):
        value_type = type(value)
        if cls in _INTEGERS:
            if value_type is not int:
                raise _UseWrappers
            return value
        if cls is types.Float:
            if value_type is not float:
                raise _UseWrappers
            return value
        if cls is types.Bool:
            if value_type is not bool:
                raise _UseWrappers
            return value
        if cls in (types.BytesDef, types.HashDef):
            if value_type is bytearray:
                value = bytes(value)
                value_type = bytes
            if value_type is not bytes:
                raise _UseWrappers
            if cls is types.HashDef and len(value) != codec.byte_count:
                raise _UseWrappers
            return value if native_bytes else codec.serialize(value)
        if cls is types.StringDef:
            if value_type is not str:
                raise _UseWrappers
            return value
        # Less common leaves retain their existing normalization and validation.
        self.plain_leaf(value)
        return codec.serialize(codec.deserialize(value))

    def length(self, count):
        if count < 128:
            self.data.append(count)
        else:
            self.data.extend(types.VarInt64.encode(count).data)

    def prepare(self, codec, value, emit=True, native_bytes=True):
        """Write plain inputs, or return serialized values for map sorting.

        When emitting a container, only its None/non-None result matters to
        Option; its bytes have already been appended to the output buffer.
        """
        cls = self.check(codec)
        if cls in _PRIMITIVES:
            result = self.primitive(codec, cls, value, native_bytes)
            if emit:
                if cls is types.HashDef:
                    self.data.extend(result)
                elif cls is types.UnsignedInteger:
                    self.data.extend(result.to_bytes(codec.byte_count, 'little'))
                elif cls is types.BytesDef:
                    self.length(len(result))
                    self.data.extend(result)
                elif cls is types.Bool:
                    self.data.append(result)
                elif cls is types.VarInt64Def and 0 <= result < 128:
                    self.data.append(result)
                elif cls is not types.NullType:
                    self.data.extend(codec.encode(result).data)
            return result
        if cls is types.Struct:
            if type(value) is not dict:
                value = self.fields(value)
            elif any(type(name) is not str for name in value):
                raise _UseWrappers
            result = {} if not emit else True
            for name, child in codec.arguments.items():
                if name not in value:
                    raise _UseWrappers
                item = self.prepare(child, value[name], emit, native_bytes)
                if not emit:
                    result[name] = item
            return result
        if cls is types.Tuple:
            if type(value) not in (tuple, list) or len(value) < len(codec.values):
                raise _UseWrappers
            result = [self.prepare(child, value[index], emit, native_bytes)
                      for index, child in enumerate(codec.values)]
            return True if emit else tuple(result)
        if cls is types.Option:
            start = len(self.data)
            if emit:
                self.data.append(0)
            result = None if value is None else self.prepare(codec.some, value, emit, native_bytes)
            if emit and result is not None:
                self.data[start] = 1
            elif emit:
                # Option(Null) and nested Options normalize to None too.
                del self.data[start + 1:]
            return result
        if cls is types.Enum:
            if type(value) not in (dict, str):
                fields = self.fields(value)
                if codec._deserialize_type and isinstance(value, codec._deserialize_type):
                    value = {name: item for name, item in fields.items() if item is not None}
                else:
                    raise _UseWrappers
            if type(value) is str:
                value = {value: None}
            if len(value) != 1:
                raise _UseWrappers
            name, item = next(iter(value.items()))
            if type(name) is not str:
                raise _UseWrappers
            for index, (variant, child) in enumerate(codec.variants.items()):
                if type(child) is dict:
                    index, child = child.get('id', index), child.get('type', child)
                if variant == name:
                    if type(index) is not int or not 0 <= index <= 255:
                        raise _UseWrappers
                    if emit:
                        self.data.append(index)
                    if child is None:
                        return name
                    item = self.prepare(child, item, emit, native_bytes)
                    return True if emit else {name: item}
            raise _UseWrappers
        if cls in (types.Vec, types.BoundedVec, types.Array):
            array = cls is types.Array
            if type(value) is bytearray:
                value = bytes(value)
            if type(value) not in (list, tuple, bytes):
                raise _UseWrappers
            if array and (type(value) is tuple or len(value) != codec.length):
                raise _UseWrappers
            if type(value) is list and not value:
                if cls is types.BoundedVec:
                    codec._check_count(0)
                if emit and not array:
                    self.data.append(0)
                return True if emit else []
            if not array and codec.type_def is types.U8 and type(value) is not bytes:
                raise _UseWrappers
            if cls is types.BoundedVec:
                codec._check_count(len(value))
            if codec.type_def is types.U8 and type(value) is bytes:
                result = value if native_bytes else codec.serialize(value)
                if emit:
                    if not array:
                        self.length(len(value))
                    self.data.extend(value)
                return result
            if type(value) not in (list, tuple) or (array and type(value) is not list):
                raise _UseWrappers
            child_class = self.check(codec.type_def)
            if (emit and child_class is types.HashDef
                    and all(type(item) is bytes and len(item) == codec.type_def.byte_count for item in value)):
                if not array:
                    self.length(len(value))
                self.data.extend(b''.join(value))
                return True
            if emit and child_class in _INTEGERS and all(type(item) is int for item in value):
                if child_class is types.UnsignedInteger:
                    if not array:
                        self.length(len(value))
                    for item in value:
                        self.data.extend(item.to_bytes(codec.type_def.byte_count, 'little'))
                else:
                    self.data.extend(codec.encode(list(value) if type(value) is tuple else value).data)
                return True
            if emit and not array:
                self.length(len(value))
            result = [self.prepare(codec.type_def, item, emit, native_bytes) for item in value]
            return True if emit else result
        if type(value) not in (dict, list, tuple):
            raise _UseWrappers
        if not value:
            if emit:
                self.data.append(0)
            return []
        # Maps sort serialized representations, including values for duplicate
        # keys. Keep that representation and let the existing encoder sort it.
        items = value.items() if type(value) is dict else value
        result = []
        for pair in items:
            if type(pair) not in (tuple, list) or len(pair) != 2:
                raise _UseWrappers
            key, item = pair
            result.append((self.prepare(codec.key_def, key, False, False),
                           self.prepare(codec.value_def, item, False, False)))
        if emit:
            self.data.extend(codec.encode(result).data)
        return result


def encode_from_object(codec, value):
    """Return binary data for standard inputs, or None to use normal wrappers."""
    # Bypassing wrappers pays off for collection models. Small mixed records
    # are cheaper through the existing normalization path.
    if (type(codec) is not types.Struct or type(codec.arguments) is not dict
            or not codec.arguments or not all(type(child) in (
                types.Array, types.Vec, types.BoundedVec, types.Map,
            ) for child in codec.arguments.values())):
        return None
    encoder = _Encoder()
    try:
        encoder.prepare(codec, value)
    except (_UseWrappers, ValueError, TypeError, ArithmeticError, IndexError,
            KeyError, AttributeError, RecursionError, struct.error):
        # Probing uses only built-in hooks and plain inputs. On invalid or
        # unsupported data, repeat the original path so normalization errors
        # still take precedence over encode-time errors in earlier fields.
        return None
    return JamBytes(encoder.data)
