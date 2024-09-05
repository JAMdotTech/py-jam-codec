import dataclasses
from dataclasses import is_dataclass
import enum
from typing import Type, TypeVar, Union
import typing
import json

from jamcodec.base import JamCodecTypeDef, JamCodecType, JamBytes
from jamcodec.types import Struct, Option, Vec, Enum

T = TypeVar('T')


class Serializable:
    @classmethod
    def to_codec_def(cls) -> JamCodecTypeDef:

        if getattr(cls, '_codec_type_def', None) is None:

            if is_dataclass(cls):

                if getattr(cls, '_codec_enum', False):
                    variants = {
                        field.name: cls.dataclass_field_to_scale_typ_def(field) for field in dataclasses.fields(cls)
                    }
                    cls._codec_type_def = Enum(**variants)
                else:
                    arguments = {}
                    for field in dataclasses.fields(cls):

                        arguments[field.name] = cls.dataclass_field_to_scale_typ_def(field)

                    cls._codec_type_def = Struct(**arguments)

            elif issubclass(cls, enum.Enum):
                variants = {status.name: None for status in cls}
                cls._codec_type_def = Enum(**variants)
            else:
                raise NotImplementedError

        # Set deserialize type
        cls._codec_type_def._deserialize_type = cls

        return cls._codec_type_def

    def serialize(self) -> Union[str, int, float, bool, dict, list]:
        scale_type = self.to_codec_type()
        return scale_type.value_serialized

    @classmethod
    def deserialize(cls: Type[T], data: Union[str, int, float, bool, dict, list]) -> T:
        scale_type = cls.to_codec_def().new()
        scale_type.deserialize(data)
        return cls.from_codec_type(scale_type)

    def to_codec_type(self) -> JamCodecType:

        if not is_dataclass(self) and not issubclass(self.__class__, enum.Enum):
            raise NotImplementedError("Type not supported.")

        scale_type = self.to_codec_def().new()
        scale_type.deserialize(self)

        return scale_type

    @classmethod
    def from_codec_type(cls: Type[T], scale_type: JamCodecType) -> T:
        return scale_type.to_serializable_obj()

    def to_jam_bytes(self) -> JamBytes:
        scale_obj = self.to_codec_type()
        return scale_obj.encode()

    @classmethod
    def from_jam_bytes(cls: Type[T], scale_bytes: JamBytes) -> T:
        scale_obj = cls.to_codec_def().new()
        scale_obj.decode(scale_bytes)
        return cls.from_codec_type(scale_obj)

    def to_json(self) -> any:
        # TODO rename?
        return self.serialize()

    @classmethod
    def from_json(cls: Type[T], json_data: dict) -> T:
        # TODO rename?
        return cls.deserialize(json_data)

    @classmethod
    def dataclass_field_to_scale_typ_def(cls, field) -> JamCodecTypeDef:

        if 'codec' not in field.metadata:
            raise ValueError(f'Field {field.name} has no codec metadata')

        return field.metadata['codec']

    def enum_value(self):
        for field in dataclasses.fields(self):
            if getattr(self, field.name, None) is not None:
                return field.name, getattr(self, field.name)
