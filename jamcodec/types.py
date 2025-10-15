# Python SCALE Codec Library
#
# Copyright 2018-2023 Stichting Polkascan (Polkascan Foundation).
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
import dataclasses
import enum

import math
import struct
import typing
from collections.abc import Mapping
from typing import Union, Optional

from jamcodec.base import JamCodecType, JamBytes, JamCodecPrimitive, JamCodecTypeDef
from jamcodec.constants import TYPE_DECOMP_MAX_RECURSIVE
from jamcodec.exceptions import ScaleEncodeException, ScaleDecodeException, ScaleDeserializeException, \
    ScaleSerializeException

if typing.TYPE_CHECKING:
    from jamcodec.mixins import Serializable


class UnsignedInteger(JamCodecPrimitive):
    """
    Unsigned int type, encoded in little-endian (LE) format
    """

    def __init__(self, bits: int):
        super().__init__()
        self.bits = bits
        self.byte_count = int(self.bits / 8)

    def decode(self, data: JamBytes) -> int:
        return int.from_bytes(data.get_next_bytes(self.byte_count), byteorder='little')

    def encode(self, value) -> JamBytes:

        if 0 <= int(value) <= 2**(self.byte_count * 8) - 1:
            return JamBytes(bytearray(int(value).to_bytes(self.byte_count, 'little')))
        else:
            raise ScaleEncodeException(f'{value} out of range for u{self.bits}')

    def serialize(self, value: int) -> int:
        return value

    def deserialize(self, value: int) -> int:
        if type(value) is not int:
            raise ValueError('Value must be an integer')
        return value

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):
        return self.bits


class SignedInteger(JamCodecPrimitive):
    """
    Signed int type, encoded in little-endian (LE) format
    """

    def __init__(self, bits: int):
        super().__init__()
        self.bits = bits
        self.byte_count = int(self.bits / 8)

    def decode(self, data: JamBytes) -> int:
        return int.from_bytes(data.get_next_bytes(self.byte_count), byteorder='little', signed=True)

    def encode(self, value) -> JamBytes:

        if -2**self.bits <= int(value) <= 2**self.bits - 1:
            return JamBytes(bytearray(int(value).to_bytes(self.byte_count, 'little', signed=True)))
        else:
            raise ScaleEncodeException(f'{value} out of range for i{self.bits}')

    def serialize(self, value: int) -> int:
        return value

    def deserialize(self, value: int) -> int:
        if type(value) is not int:
            raise ValueError('Value must be an integer')
        return value

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):
        return -self.bits


class Float(JamCodecPrimitive):

    def __init__(self, bits: int):
        super().__init__()
        self.bits = bits
        self.byte_count = int(self.bits / 8)
        self.struct_format = 'f' if self.bits == 32 else 'd'

    def decode(self, data: JamBytes) -> int:
        return struct.unpack(self.struct_format, data.get_next_bytes(self.byte_count))[0]

    def encode(self, value: float) -> JamBytes:
        if type(value) is not float:
            raise ScaleEncodeException(f'{value} is not a float')

        return JamBytes(struct.pack(self.struct_format, value))

    def serialize(self, value: float) -> float:
        return value

    def deserialize(self, value: float) -> float:
        if type(value) is not float:
            raise ScaleDeserializeException('Value must be an float')
        return value

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):
        return float(self.bits)

class Bool(JamCodecPrimitive):

    def decode(self, data: JamBytes) -> bool:

        bool_data = data.get_next_bytes(1)
        if bool_data not in [b'\x00', b'\x01']:
            raise ScaleDecodeException('Invalid value for datatype "bool"')
        return bool_data == b'\x01'

    def encode(self, value: bool) -> JamBytes:
        if value is True:
            return JamBytes('0x01')
        elif value is False:
            return JamBytes('0x00')
        else:
            raise ScaleEncodeException("Value must be boolean")

    def serialize(self, value: bool) -> bool:
        return value

    def deserialize(self, value: bool) -> bool:
        return value

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):
        return True


class NullType(JamCodecTypeDef):

    def decode(self, data: JamBytes) -> any:
        return None

    def encode(self, value: any) -> JamBytes:
        return JamBytes(bytearray())

    def serialize(self, value: any) -> any:
        return None

    def deserialize(self, value: any) -> any:
        return None

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):
        return None

    def to_serializable_obj(self, value_object: any) -> 'Serializable':
        return Null


Null = NullType()


class StructObject(JamCodecType):
    def encode(self, value: Optional[Union[dict, tuple]] = None) -> JamBytes:
        if type(value) is tuple:
            # Convert tuple to dict
            try:
                value = {key: value[idx] for idx, key in enumerate(self.type_def.arguments.keys())}
            except IndexError:
                raise ScaleEncodeException("Not enough items in tuple to convert to dict")
        return super().encode(value)


class Struct(JamCodecTypeDef):

    arguments = None
    scale_type_cls = StructObject

    def __init__(self, **kwargs):
        if len(kwargs) > 0:
            self.arguments = {key: value for key, value in kwargs.items()}
        super().__init__()

    def encode(self, value: dict) -> JamBytes:

        data = JamBytes(bytearray())
        for name, scale_obj in self.arguments.items():

            if name not in value:
                raise ScaleEncodeException(f'Argument "{name}" of Struct is missing in given value')

            data += scale_obj.encode(value[name])

            if value[name] and issubclass(value[name].__class__, JamCodecType):
                value[name] = value[name].serialize()

        return data

    def decode(self, data) -> dict:
        value = {}

        for key, scale_def in self.arguments.items():

            scale_obj = scale_def.new()
            scale_obj.decode(data)

            value[key] = scale_obj

        return value

    def serialize(self, value: dict) -> dict:
        if value is None:
            raise ScaleSerializeException('Value cannot be None')
        return {k: obj.value for k, obj in value.items()}

    def deserialize(self, value: Union[dict, 'Serializable']) -> dict:

        value_object = {}

        if dataclasses.is_dataclass(value):
            value = {f.name: getattr(value, f.name) for f in dataclasses.fields(value)}

        for key, scale_def in self.arguments.items():
            if key in value:
                scale_obj = scale_def.new()

                scale_obj.value_serialized = value[key]
                scale_obj.deserialize(value[key])

                value_object[key] = scale_obj
            else:
                raise ScaleDeserializeException(f'Argument "{key}" of Struct is missing in given value')

        return value_object

    def to_serializable_obj(self, value_object: dict):
        fields = {}
        for name, value in value_object.items():
            fields[name] = value.to_serializable_obj()

        return self._deserialize_type(**fields)

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):

        if _recursion_level > max_recursion:
            return f'<{self.__class__.__name__}>'

        return {
            k: scale_def.example_value(_recursion_level + 1, max_recursion) for k, scale_def in self.arguments.items()
        }


class Tuple(JamCodecTypeDef):

    values = None

    def __init__(self, *args, **kwargs):
        if len(args) > 0:
            self.values = args
        super().__init__()

    def encode(self, value: tuple) -> JamBytes:
        if type(value) is not tuple:
            value = (value,)

        data = JamBytes(bytearray())
        for idx, scale_obj in enumerate(self.values):

            data += scale_obj.encode(value[idx])
        return data

    def decode(self, data: JamBytes) -> tuple:
        value = ()

        for scale_def in self.values:
            scale_obj = scale_def.new()

            scale_obj.decode(data)

            if len(self.values) == 1:
                return scale_obj

            value += (scale_obj,)

        return value

    def serialize(self, value: Union[tuple, JamCodecType]) -> tuple:
        if issubclass(value.__class__, JamCodecType):
            return value.value

        return tuple((i.value for i in value))

    def deserialize(self, value: Union[tuple, list]) -> tuple:

        if type(value) not in (tuple, list):
            value = (value,)

        value_object = ()

        for idx, scale_def in enumerate(self.values):
            scale_obj = scale_def.new()

            scale_obj.value_serialized = value
            scale_obj.deserialize(value[idx])
            value_object += (scale_obj,)

        return value_object

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):
        return tuple([i.example_value() for i in self.values])

    def to_serializable_obj(self, value_object: tuple) -> tuple:
        return tuple([item.to_serializable_obj() for item in value_object])

class EnumType(JamCodecType):

    @property
    def index(self):
        if self.value_object is not None:
            for index, name in enumerate(self.type_def.variants.keys()):
                if name == self.value_object[0]:
                    return index


class Enum(JamCodecTypeDef):

    variants = None

    def __init__(self, **kwargs):
        super().__init__()

        if len(kwargs) > 0:
            self.variants = {key.rstrip('_'): value for key, value in kwargs.items()}

        if self.scale_type_cls is None:
            self.scale_type_cls = EnumType

    def encode(self, value: Union[str, dict]) -> JamBytes:

        # if issubclass(value.__class__, ScaleType) and value.type_def.__class__ is self.__class__:
        #     value = value.value

        if type(value) is dict:
            value = value.copy()

        if type(value) is str:
            # Convert simple enum values
            value = {value: None}

        if type(value) is not dict:
            raise ScaleEncodeException(f"Value must be a dict or str when encoding enums, not '{value}'")

        if len(value) != 1:
            raise ScaleEncodeException("Only one variant can be specified for enums")

        enum_key, enum_value = list(value.items())[0]

        for idx, (variant_name, variant_obj) in enumerate(self.variants.items()):

            if type(variant_obj) is dict:
                idx = variant_obj.get('id', idx)
                variant_obj = variant_obj.get('type', variant_obj)

            if enum_key == variant_name:
                data = JamBytes(bytearray([idx]))

                if variant_obj is not None:

                    data += variant_obj.encode(enum_value)

                return data

        raise ScaleEncodeException(f"Variant '{enum_key}' not defined for this enum")

    def decode(self, data: JamBytes) -> tuple:

        index = int.from_bytes(data.get_next_bytes(1), byteorder='little')

        enum_key = None
        enum_variant = None

        for idx, (variant_key, variant_obj) in enumerate(self.variants.items()):
            if type(variant_obj) is dict:
                idx = variant_obj.get('id', idx)
                variant_obj = variant_obj.get('type', variant_obj)
            if index == idx:
                enum_key = variant_key
                enum_variant = variant_obj
                break

        if enum_key is None:
            raise ScaleDecodeException(f"Index '{index}' not present in Enum type mapping")

        if enum_variant is None:
            return (enum_key, None)
        else:
            scale_obj = enum_variant.new()
            scale_obj.decode(data)
            return (enum_key, scale_obj)

    def serialize(self, value: tuple) -> Union[str, dict]:

        if isinstance(value, enum.Enum):
            return value.name

        if value[1] is None:
            return value[0]
        else:
            return {value[0]: value[1].value}

    def deserialize(self, value: Union[str, dict, tuple]) -> tuple:

        if self._deserialize_type:
            if isinstance(value, self._deserialize_type):
                if dataclasses.is_dataclass(value):
                    value = {f.name: getattr(value, f.name) for f in dataclasses.fields(value) if getattr(value, f.name) is not None}
                else:
                    return value
            elif issubclass(self._deserialize_type, enum.Enum):
                return self._deserialize_type[value]
                # pass

        if type(value) is str:
            value = {value: None}

        if isinstance(value, enum.Enum):
            value = {value.name: None}

        if len(list(value.items())) != 1:
            raise ScaleDeserializeException("Only one variant can be specified for enums")

        enum_key, enum_value = list(value.items())[0]

        for idx, (variant_name, variant_obj) in enumerate(self.variants.items()):

            if type(variant_obj) is dict:
                variant_obj = variant_obj.get('type', variant_obj)

            if enum_key == variant_name:

                if variant_obj is not None:
                    enum_value_obj = variant_obj.new()
                    enum_value_obj.value_serialized = enum_value
                    enum_value_obj.deserialize(enum_value)
                else:
                    enum_value_obj = None

                return enum_key, enum_value_obj

        raise ValueError(f"Error while deserializing Enum; variant '{enum_key}' not found")

    def to_serializable_obj(self, value_object: any) -> 'Serializable':
        if self._deserialize_type and issubclass(self._deserialize_type, enum.Enum):
            return value_object

        fields = {value_object[0]: value_object[1].to_serializable_obj()}
        return self._deserialize_type(**fields)

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):

        if _recursion_level > max_recursion:
            return f'<{self.__class__.__name__}>'

        example = {}
        for idx, (variant_name, variant_obj) in enumerate(self.variants.items()):
            if not variant_name.startswith('__'):
                if variant_obj is None:
                    example[variant_name] = None
                else:
                    example[variant_name] = variant_obj.example_value(_recursion_level + 1, max_recursion)
        return example


class Option(JamCodecTypeDef):
    def __init__(self, some):
        self.some = some
        super().__init__()

    def encode(self, value: any) -> JamBytes:
        if value is None:
            return JamBytes('0x00')
        else:
            return JamBytes('0x01') + self.some.encode(value)

    def decode(self, data: JamBytes) -> Optional[JamCodecType]:
        if data.get_next_bytes(1) == b'\x00':
            return None
        else:
            scale_obj = self.some.new()
            scale_obj.decode(data)
            return scale_obj

    def serialize(self, value: Optional[JamCodecType]) -> any:
        if value is not None:
            return value.value

    def deserialize(self, value: any) -> Optional[JamCodecType]:
        if value is not None:
            some_obj = self.some.new()
            some_obj.deserialize(value)
            return some_obj

    def to_serializable_obj(self, value_object: any):
        if issubclass(value_object.__class__, JamCodecType):
            return value_object.to_serializable_obj()
        else:
            return value_object

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):
        return None, self.some.example_value()


class CompactDef(JamCodecTypeDef):
    def __init__(self, type_: JamCodecTypeDef = None):
        self.type = type_
        self.compact_length = 0
        self.compact_bytes = None
        super().__init__()

    def process_compact_bytes(self, data):
        compact_byte = data.get_next_bytes(1)
        try:
            byte_mod = compact_byte[0] % 4
        except IndexError:
            raise ScaleDecodeException("Invalid byte for Compact")

        if byte_mod == 0:
            self.compact_length = 1
        elif byte_mod == 1:
            self.compact_length = 2
        elif byte_mod == 2:
            self.compact_length = 4
        else:
            self.compact_length = int(5 + (compact_byte[0] - 3) / 4)

        if self.compact_length == 1:
            self.compact_bytes = compact_byte
        elif self.compact_length in [2, 4]:
            self.compact_bytes = compact_byte + data.get_next_bytes(self.compact_length - 1)
        else:
            self.compact_bytes = data.get_next_bytes(self.compact_length - 1)

        return self.compact_bytes

    def decode(self, data: JamBytes) -> any:
        self.process_compact_bytes(data)

        if self.compact_length <= 4:
            return int(int.from_bytes(self.compact_bytes, byteorder='little') / 4)
        else:
            return int.from_bytes(self.compact_bytes, byteorder='little')

    def encode(self, value: int) -> JamBytes:

        value = int(value)

        if value <= 0b00111111:
            return JamBytes(bytearray(int(value << 2).to_bytes(1, 'little')))

        elif value <= 0b0011111111111111:
            return JamBytes(bytearray(int((value << 2) | 0b01).to_bytes(2, 'little')))

        elif value <= 0b00111111111111111111111111111111:
            return JamBytes(bytearray(int((value << 2) | 0b10).to_bytes(4, 'little')))

        else:
            for bytes_length in range(4, 68):
                if 2 ** (8 * (bytes_length - 1)) <= value < 2 ** (8 * bytes_length):
                    return JamBytes(bytearray(
                        ((bytes_length - 4) << 2 | 0b11).to_bytes(1, 'little') + value.to_bytes(bytes_length,
                                                                                                'little')))
            else:
                raise ScaleEncodeException('{} out of range'.format(value))

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):
        return 1

    def serialize(self, value: int) -> int:
        return value

    def deserialize(self, value: int) -> int:
        if type(value) is not int:
            raise ValueError('Value must be an integer')
        return value


class VecType(JamCodecType):

    def __len__(self):
        return len(self.value_object)


class Vec(JamCodecTypeDef):
    def __init__(self, type_def: JamCodecTypeDef):
        super().__init__()
        self.scale_type_cls = VecType
        self.type_def = type_def

    def encode(self, value: list) -> JamBytes:
        if self.type_def is U8:
            return Bytes.encode(value)

        # Encode length of Vec
        data = VarInt64.encode(len(value))

        for idx, item in enumerate(value):
            if type(item) is JamBytes:
                data += item
            else:
                data += self.type_def.encode(item)
                if item and issubclass(item.__class__, JamCodecType):
                    value[idx] = item.serialize()

        return data

    def decode(self, data: JamBytes) -> Union[list, bytes]:

        if self.type_def is U8:
            return Bytes.decode(data)

        # Decode length of Vec
        length = VarInt64.decode(data)

        value = []

        for _ in range(0, length):
            obj = self.type_def.new()
            obj.decode(data)

            value.append(obj)

        return value

    def serialize(self, value: Union[list, bytes]) -> Union[list, str]:
        if self.type_def is U8:
            return Bytes.serialize(value)
        return [i.value_serialized for i in value]

    def deserialize(self, value: Union[list, bytes]) -> Union[list, bytes]:
        if self.type_def is U8:
            return Bytes.deserialize(value)


        value_object = []

        for item in value:
            obj = self.type_def.new()
            obj.value_serialized = item
            obj.deserialize(item)

            value_object.append(obj)

        return value_object

    def to_serializable_obj(self, value_object: dict):
        return [item.to_serializable_obj() for item in value_object]

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):
        if self.type_def is U8:
            return b'Bytes'
        return [self.type_def.example_value()]


class BitVec(JamCodecTypeDef):
    """
    A BitVec that represents an array of bits. The bits are however stored encoded. The difference between this
    and a normal Bytes would be that the length prefix indicates the number of bits encoded, not the bytes
    """

    def encode(self, value: Union[list, str, int, bytes]) -> JamBytes:

        if type(value) is str and value[0:2] == '0x':
            value = bytes.fromhex(value[2:])

        if type(value) is bytes:
            return JamBytes(value)

        if type(value) is list:
            value = sum(v << i for i, v in enumerate(reversed(value)))

        if type(value) is str and value[0:2] == '0b':
            value = int(value[2:], 2)

        if type(value) is not int:
            raise ScaleEncodeException("Provided value is not an int, binary str or a list of booleans")

        if value == 0:
            return JamBytes(b'\x00')

        # encode the length in a varint64
        data = VarInt64.encode(value.bit_length())

        byte_length = math.ceil(value.bit_length() / 8)

        return data + value.to_bytes(length=byte_length, byteorder='little')

    def decode(self, data: JamBytes) -> str:
        # Decode length of Vec
        length = VarInt64.decode(data)

        total = math.ceil(length / 8)

        value_int = int.from_bytes(data.get_next_bytes(total), byteorder='little')

        return '0b' + bin(value_int)[2:].zfill(length)

    def serialize(self, value: str) -> str:
        return value

    def deserialize(self, value: str) -> str:
        return value


class ArrayObject(JamCodecType):

    def to_bytes(self) -> bytes:
        if self.type_def.type_def is not U8:
            raise ScaleDeserializeException('Only an Array of U8 can be represented as bytes')
        return self.value_object


class Array(JamCodecTypeDef):

    scale_type_cls = ArrayObject

    def __init__(self, type_def: JamCodecTypeDef, length: int):
        self.type_def = type_def
        self.length = length
        super().__init__()

    def encode(self, value: Union[list, str, bytes]) -> JamBytes:

        if self.type_def is U8:

            if type(value) is list:
                value = bytes(value)
            elif type(value) is str:
                if value[0:2] == '0x':
                    value = bytes.fromhex(value[2:])
                else:
                    value = value.encode('utf-8')

            if type(value) is not bytes:
                raise ScaleEncodeException('value should be of type list, str or bytes')

            if len(value) != self.length:
                raise ScaleEncodeException(f'Value should be {self.length} bytes long')

            return JamBytes(value)
        else:
            data = JamBytes(bytearray())

            if type(value) is not list:
                raise ScaleEncodeException("Value must be of type list")

            if len(value) != self.length:
                raise ScaleEncodeException("Length of list does not match size of array")

            for item in value:
                data += self.type_def.encode(item)

            return data

    def decode(self, data: JamBytes) -> Union[list, bytes]:
        if self.type_def is U8:
            return data.get_next_bytes(self.length)
        else:
            value = []

            for _ in range(0, self.length):
                obj = self.type_def.new()
                obj.decode(data)

                value.append(obj)

            return value

    def serialize(self, value: Union[list, bytes]) -> Union[list, str]:
        if type(value) is list:
            return [i.value_serialized for i in value]
        else:
            return f'0x{value.hex()}'

    def deserialize(self, value: Union[list, str, bytes, bytearray]) -> Union[list, bytes]:

        if type(value) not in [list, str, bytes, bytearray]:
            raise ScaleDeserializeException('value should be of type list, str or bytes')

        if type(value) is str:
            if value[0:2] == '0x':
                value = bytes.fromhex(value[2:])
            else:
                value = value.encode()

        if len(value) != self.length:
            raise ScaleDeserializeException('Length of array does not match size of value')

        if type(value) is bytearray:
            value = bytes(value)

        if type(value) is bytes:
            if self.type_def is not U8:
                raise ScaleDeserializeException('Only an Array of U8 can be represented as (hex)bytes')

            return value

        if type(value) is list:

            value_object = []

            for item in value:
                obj = self.type_def.new()
                obj.value_serialized = item
                obj.deserialize(item)

                value_object.append(obj)

            return value_object

    def to_serializable_obj(self, value_object: dict):
        if type(value_object) is list:
            return [item.to_serializable_obj() for item in value_object]
        else:
            return value_object

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):
        if self.type_def is U8:
            return f'0x{str(self.length).zfill(2) * self.length}'
        else:
            return [self.type_def.example_value()] * self.length


class BitArray(JamCodecTypeDef):

    def __init__(self, length: int, strict_decoding: bool = True):
        self.length = length
        self.strict_decoding = strict_decoding
        super().__init__()

    def encode(self, value: Union[list, str, bytes]) -> JamBytes:

        byte_length = (self.length + 7) // 8

        if type(value) is list:
            value = sum(v << i for i, v in enumerate(value))

        if type(value) is str and value[0:2] == '0x':
            value = bytes.fromhex(value[2:])

        if type(value) is str and value[0:2] == '0b':
            # value = int(value[2:], 2)
            raise NotImplementedError

        if type(value) is bytes:
            value = int.from_bytes(value, byteorder='little')

        if type(value) is not int:
            raise ScaleEncodeException("Provided value is not an int, binary str or a list of booleans")

        return JamBytes(value.to_bytes(length=byte_length, byteorder='little'))

    def decode(self, data: JamBytes) -> list:
        byte_length = (self.length + 7) // 8
        octets = data.get_next_bytes(byte_length)

        total_bits = len(octets) * 8
        bits = [False] * total_bits

        bit_index = 0
        for byte in octets:
            # Unpack the bits from the current byte (octet)
            for i in range(8):
                bits[bit_index] = (byte >> i) & 1 == 1
                bit_index += 1

        if self.strict_decoding and any(bits[self.length:]):
            raise ScaleDecodeException('Remaining bits not all 0')

        return bits[:self.length]

    def serialize(self, value: Union[list, bytes]) -> Union[list, str]:
        if type(value) is list:
            # Convert back to bytes
            value = sum(v << i for i, v in enumerate(value))
            byte_length = math.ceil(value.bit_length() / 8)
            value = value.to_bytes(length=byte_length, byteorder='little')

        return f'0x{value.hex()}'

    def deserialize(self, value: Union[list, str, bytes, bytearray], convert_to_list=True) -> Union[list, bytes]:

        if type(value) not in [list, str, bytes, bytearray]:
            raise ScaleDeserializeException('value should be of type list, str or bytes')

        if type(value) is list:
            return value

        if type(value) is str:
            if value[0:2] == '0x':
                value = bytes.fromhex(value[2:])
            else:
                value = value.encode()

        if type(value) is bytearray:
            value = bytes(value)

        if not convert_to_list:
            return value
        else:
            total_bits = len(value) * 8
            bits = [False] * total_bits

            bit_index = 0
            for byte in value:
                # Unpack the bits from the current byte (octet)
                for i in range(8):
                    bits[bit_index] = (byte >> i) & 1 == 1
                    bit_index += 1

            if self.strict_decoding and any(bits[self.length:]):
                raise ScaleDecodeException('Remaining bits not all 0')

            return bits[:self.length]

    def to_serializable_obj(self, value_object: dict):
        return value_object

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):
        return [True] * self.length


class DataType(EnumType):

    def decode(self, data: JamBytes, check_remaining=False) -> any:
        value = super().decode(data)

        if type(value) is dict:
            items = list(value.items())[0]
            if items[0].startswith('Raw'):
                self.value_serialized = {'Raw': items[1]}
                self.value_object = ('Raw', self.value_object[1])

        return self.value_serialized

    def encode(self, value: dict) -> JamBytes:
        items = list(value.items())[0]
        if items[0] == 'Raw':
            value = {f'Raw{len(items[1])}': items[1]}

        return super().encode(value)


class Map(JamCodecTypeDef):

    def __init__(self, key_def: JamCodecTypeDef, value_def: JamCodecTypeDef):
        super().__init__()
        self.key_def = key_def
        self.value_def = value_def

    def encode(self, value: Union[typing.Mapping, list]) -> JamBytes:

        if isinstance(value, Mapping):
            # Convert to list
            value = value.items()

        # Sort Map by keys and then values
        value = sorted(value)

        # Encode length of Vec
        data = VarInt64.encode(len(value))

        for item_key, item_value in value:
            data += self.key_def.encode(item_key)
            data += self.value_def.encode(item_value)

        return data

    def decode(self, data: JamBytes) -> list:
        # Decode length of Map
        length = VarInt64.decode(data)

        value = []

        for _ in range(0, length):
            key_obj = self.key_def.new()
            key_obj.decode(data)
            value_obj = self.value_def.new()
            value_obj.decode(data)
            value.append((key_obj, value_obj))

        return value

    def serialize(self, value: list) -> typing.List[typing.Tuple]:
        return [(k.value_serialized, v.value_serialized) for k, v in value]

    def deserialize(self, value: Union[typing.Mapping, list]) -> list:
        if isinstance(value, Mapping):
            value = value.items()

        result = []
        for k, v in value:
            key_obj = self.key_def.new()
            key_obj.deserialize(k)
            value_obj = self.value_def.new()
            value_obj.deserialize(v)
            result.append((key_obj, value_obj))

        return result

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):
        return {self.key_def.example_value(): self.value_def.example_value()}

    def to_serializable_obj(self, value_object: list):
        return {key.to_serializable_obj(): value.to_serializable_obj() for key, value in value_object}


class BytesDef(JamCodecTypeDef):
    """
    A variable collection of bytes, stored as an `Vec<u8>`
    """

    def encode(self, value: Union[str, bytes, bytearray, list]) -> JamBytes:

        if type(value) is str:
            if value[0:2] == '0x':
                # TODO implicit HexBytes conversion can have unexpected result if string is actually starting with '0x'
                value = bytes.fromhex(value[2:])
            else:
                value = value.encode('utf-8')

        elif type(value) in (bytearray, list):
            value = bytes(value)

        if type(value) is not bytes:
            raise ScaleEncodeException(f'Cannot encode type "{type(value)}"')

        # Encode length of Vec
        data = VarInt64.encode(len(value))

        return data + value

    def decode(self, data: JamBytes) -> bytes:
        # Decode length of Vec
        length = VarInt64.decode(data)

        return bytes(data.get_next_bytes(length))

    def serialize(self, value: bytes) -> str:
        return f'0x{value.hex()}'

    def deserialize(self, value: Union[bytes, str, list]) -> bytes:

        if type(value) in (list, bytearray):
            value = bytes(value)

        elif type(value) is str:
            if value[0:2] == '0x':
                value = bytes.fromhex(value[2:])
            else:
                value = value.encode('utf-8')

        if type(value) is not bytes:
            raise ScaleDeserializeException(f'Cannot deserialize type "{type(value)}"')

        return value

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):
        return b'Bytes'


class StringDef(BytesDef):
    def decode(self, data: JamBytes) -> str:
        value = super().decode(data)

        try:
            return value.decode()
        except UnicodeDecodeError:
            return '0x{}'.format(value.hex())

    def serialize(self, value: str) -> str:
        return value

    def deserialize(self, value: str) -> str:
        return value

    def create_example(self, _recursion_level: int = 0):
        return 'String'


class HashDefObject(JamCodecType):
    def to_bytes(self) -> bytes:
        return self.value_object


class HashDef(JamCodecTypeDef):

    scale_type_cls = HashDefObject

    def __init__(self, bits: int):
        super().__init__()
        self.bits = bits
        self.byte_count = int(self.bits / 8)

    def decode(self, data: JamBytes) -> bytes:
        return bytes(data.get_next_bytes(self.byte_count))

    def encode(self, value: Union[str, bytes]) -> JamBytes:

        if type(value) is str:
            if value[0:2] != '0x' or len(value) != (self.byte_count*2)+2:
                raise ScaleEncodeException(f'Value should start with "0x" and should be {self.byte_count} bytes long')

            value = bytes.fromhex(value[2:])

        if type(value) is not bytes:
            raise ScaleEncodeException('value should be of type str or bytes')

        if len(value) != self.byte_count:
            raise ScaleEncodeException(f'Value should be {self.byte_count} bytes long')

        return JamBytes(value)

    def serialize(self, value: bytes) -> str:
        return f'0x{value.hex()}'

    def deserialize(self, value: Union[str, bytes, bytearray]) -> bytes:
        if type(value) is str:
            value = bytes.fromhex(value[2:])

        if type(value) is bytearray:
            value = bytes(value)

        if type(value) is not bytes:
            raise ScaleDeserializeException('value should be of type str or bytes')

        return value

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):
        return f'0x{str(self.byte_count).zfill(2) * self.byte_count}'


class VarInt64Def(JamCodecTypeDef):

    def encode(self, value: int) -> JamBytes:
        if value < 0:
            raise ScaleEncodeException("Cannot encode negative value")

        if value < 2 ** 7:
            return JamBytes(bytes([value]))

        length = math.ceil(value.bit_length() / 7) - 1

        if 2 ** 7 <= value < 2 ** 56:
            prefix = (2 ** 8 - 2 ** (8 - length)) + (value // 2 ** (8 * length))
            remainder = (value % 2 ** (8 * length)).to_bytes(length, byteorder='little')

        elif 2 ** 56 <= value < 2 ** 64:
            prefix = 2 ** 8 - 1
            remainder = value.to_bytes(8, byteorder='little')

        else:
            raise ScaleEncodeException("Number too large for 64-bit variable-length encoding")

        return JamBytes(bytes([prefix]) + remainder)

    def decode(self, data: JamBytes) -> int:
        prefix = int.from_bytes(data.get_next_bytes(1), byteorder='little')

        if prefix < 128:
            return prefix

        if 0x80 <= prefix < 0xc0:
            length = 1
        elif 0xc0 <= prefix < 0xe0:
            length = 2
        elif 0xe0 <= prefix < 0xf0:
            length = 3
        elif 0xf0 <= prefix < 0xf8:
            length = 4
        elif 0xf8 <= prefix < 0xfc:
            length = 5
        elif 0xfc <= prefix < 0xfe:
            length = 6
        elif 0xfe <= prefix < 0xff:
            length = 7
        else:
            length = 8

        if 1 <= length < 8:  # Handles case for `2**7 <= value < 2**21`
            value_part = prefix - (2 ** 8 - 2 ** (8 - length))
            value = (value_part * 2 ** (8 * length)) + int.from_bytes(data.get_next_bytes(length), byteorder='little')
        elif length == 8:  # Handles case for `2**21 <= value < 2**64`
            # value_part = prefix - (2 ** 8 - 1)
            value = int.from_bytes(data.get_next_bytes(8), byteorder='little')
        else:
            raise ScaleDecodeException("Unsupported length")

        return value

    def serialize(self, value: int) -> int:
        return value

    def deserialize(self, value: int) -> int:
        if type(value) is not int:
            raise ValueError('Value must be an integer')
        return value

    def example_value(self, _recursion_level: int = 0, max_recursion: int = TYPE_DECOMP_MAX_RECURSIVE):
        return 64


U8 = UnsignedInteger(8)
U16 = UnsignedInteger(16)
U32 = UnsignedInteger(32)
U64 = UnsignedInteger(64)
U128 = UnsignedInteger(128)
U256 = UnsignedInteger(256)

I8 = SignedInteger(8)
I16 = SignedInteger(16)
I32 = SignedInteger(32)
I64 = SignedInteger(64)
I128 = SignedInteger(128)
I256 = SignedInteger(256)

F32 = Float(32)
F64 = Float(64)

String = StringDef()
Bytes = BytesDef()
Type = String
Text = String
H256 = HashDef(256)
H512 = HashDef(512)
Hash = H256
HashMap = Map
BTreeMap = Map
VarInt64 = VarInt64Def()
Compact = CompactDef()
