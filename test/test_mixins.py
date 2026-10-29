import enum
import json
import os
import unittest
from dataclasses import dataclass, field
from os import path
from typing import Optional, Type, Union, List

from jamcodec.base import JamBytes, JamCodecType
from jamcodec.exceptions import ScaleDeserializeException, ScaleEncodeException
from jamcodec.mixins import Serializable, T
from jamcodec.types import H256, U8, U16, Array, Enum, Option, Null, Bytes, Map, Struct, StructObject, Vec


# Test definitions


@dataclass
class ValidatorData(Serializable):
    bandersnatch: bytes = field(metadata={'codec': H256})
    ed25519: bytes = field(metadata={'codec': H256})
    bls: bytes = field(metadata={'codec': Array(U8, 144)})
    metadata: bytes = field(metadata={'codec': Array(U8, 128)})


@dataclass
class EpochMark(Serializable):
    entropy: bytes = field(metadata={'codec': H256})
    validators: List[bytes] = field(metadata={'codec': Array(H256, 6)})

@dataclass
class OutputMarks(Serializable):
    epoch_mark: Optional[EpochMark] = field(metadata={'codec': Option(EpochMark.to_codec_def())})


class CustomErrorCode(Serializable, enum.Enum):
    bad_slot = 0  # Timeslot value must be strictly monotonic.
    unexpected_ticket = 1  # Received a ticket while in epoch's tail.
    bad_ticket_order = 2  # Tickets must be sorted.
    bad_ticket_proof = 3  # Invalid ticket ring proof.
    bad_ticket_attempt = 4  # Invalid ticket attempt value.
    reserved = 5  # Reserved
    duplicate_ticket = 6  # Found a ticket duplicate.
    too_many_tickets = 7  # Found amount of tickets > K


@dataclass
class Output(Serializable):
    ok: Optional[OutputMarks] = None  # Markers
    err: Optional[CustomErrorCode] = None

    _codec_type_def = Enum(
            ok=OutputMarks.to_codec_def(),
            err=CustomErrorCode.to_codec_def()
        )

    def to_codec_type(self) -> JamCodecType:
        scale_type = self.to_codec_def().new()
        scale_type.deserialize(self.serialize())
        return scale_type

    @classmethod
    def deserialize(cls: Type[T], data: Union[str, int, float, bool, dict, list]) -> T:

        return super().deserialize(data)

    def serialize(self) -> Union[str, int, float, bool, dict, list]:
        if self.err is not None:
            return {'err': self.err.serialize()}
        else:
            return {'ok': self.ok.serialize()}


@dataclass
class WorkExecResult(Serializable):

    ok: bytes = field(default=None, metadata={'codec': Bytes})
    out_of_gas: None = field(default=None, metadata={'codec': Null})
    panic: None = field(default=None, metadata={'codec': Null})
    bad_code: None = field(default=None, metadata={'codec': Null})
    code_oversize: None = field(default=None, metadata={'codec': Null})

    _codec_enum = True


class TestSerializableMixin(unittest.TestCase):

    def setUp(self):
        data = {
            'bandersnatch': '0x5e465beb01dbafe160ce8216047f2155dd0569f058afd52dcea601025a8d161d',
            'ed25519': '0x3b6a27bcceb6a42d62a3a8d02a6f0d73653215771de243a63ac048a18b59da29',
            'bls': '0x000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000',
            'metadata': '0x0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
        }

        self.test_obj = ValidatorData.deserialize(data)

    def test_dataclass_serialization(self):
        output = Output(ok=OutputMarks(epoch_mark=None))
        value = output.serialize()
        self.assertEqual({'ok': {'epoch_mark': None}}, value)

        output = Output(err=CustomErrorCode.duplicate_ticket)
        value = output.serialize()

        self.assertEqual({'err': 'duplicate_ticket'}, value)

    def test_dataclass_enum_serialization(self):
        work_exec_result = WorkExecResult(ok=bytes(4))
        value = work_exec_result.serialize()
        self.assertEqual({'ok': '0x00000000'}, value)

        work_exec_result = WorkExecResult(out_of_gas=Null)
        value = work_exec_result.serialize()
        self.assertEqual({'out_of_gas': None}, value)
        work_exec_result2 = WorkExecResult.from_json(value)

        self.assertEqual(work_exec_result, work_exec_result2)

    def test_dataclass_to_scale_type(self):
        output = Output(
            ok=OutputMarks(
                epoch_mark=EpochMark(
                    entropy=bytes(32),
                    validators=[bytes(32), bytes(32), bytes(32), bytes(32), bytes(32), bytes(32)]
                )
            )
        )
        scale_type = output.to_codec_type()
        output2 = Output.from_codec_type(scale_type)
        self.assertEqual(output, output2)

    def test_deserialize(self):

        data = {
            'bandersnatch': '0x5e465beb01dbafe160ce8216047f2155dd0569f058afd52dcea601025a8d161d',
            'ed25519': '0x3b6a27bcceb6a42d62a3a8d02a6f0d73653215771de243a63ac048a18b59da29',
            'bls': '0x000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000',
            'metadata': '0x0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
        }

        validator_obj = ValidatorData.deserialize(data)

        self.assertEqual(self.test_obj, validator_obj)
        self.assertEqual(data, validator_obj.serialize())

    def test_from_to_scale_bytes(self):

        scale_data = self.test_obj.to_jam_bytes()

        validator_obj = ValidatorData.from_jam_bytes(scale_data)

        self.assertEqual(self.test_obj, validator_obj)

    def test_binary_enum_encodings(self):
        cases = (
            (CustomErrorCode.bad_slot, b'\x00'),
            (CustomErrorCode.duplicate_ticket, b'\x06'),
            (Output(ok=OutputMarks(epoch_mark=None)), b'\x00\x00'),
            (Output(err=CustomErrorCode.duplicate_ticket), b'\x01\x06'),
            (WorkExecResult(ok=b''), b'\x00\x00'),
            (WorkExecResult(ok=b'abc'), b'\x00\x03abc'),
            (WorkExecResult(out_of_gas=Null), b'\x01'),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                serialized = value.serialize()
                encoded = value.to_jam_bytes()
                self.assertEqual(expected, encoded.to_bytes())
                self.assertEqual(0, encoded.offset)
                self.assertEqual(serialized, value.serialize())

    def test_binary_nested_collections_roundtrip(self):
        @dataclass
        class Packet(Serializable):
            payload: bytes = field(metadata={'codec': Bytes})
            numbers: list = field(metadata={'codec': Vec(Option(U16))})
            labels: dict = field(metadata={'codec': Map(U8, Bytes)})

        packet = Packet(b'abc', [None, 258], {2: b'b', 1: b'a'})
        encoded = packet.to_jam_bytes()
        self.assertEqual(b'\x03abc\x02\x00\x01\x02\x01\x02\x01\x01a\x02\x01b', encoded.to_bytes())
        self.assertEqual(packet, Packet.from_jam_bytes(encoded))
        self.assertEqual(encoded.length, encoded.offset)

    def test_binary_encoding_returns_independent_buffers(self):
        value = Output(ok=OutputMarks(epoch_mark=None))
        first = value.to_jam_bytes()
        first.get_next_bytes(1)
        second = value.to_jam_bytes()

        self.assertEqual(1, first.offset)
        self.assertEqual(0, second.offset)
        second.data[0] = 99
        self.assertEqual(b'\x00\x00', first.to_bytes())
        self.assertEqual(b'\x00\x00', value.to_jam_bytes().to_bytes())

        value.ok.epoch_mark = EpochMark(bytes(32), [bytes(32)] * 6)
        self.assertEqual(b'\x00\x01' + bytes(32 * 7), value.to_jam_bytes().to_bytes())
        self.assertEqual(b'\x00\x00', first.to_bytes())

    def test_binary_encoding_preserves_validation(self):
        @dataclass
        class Packet(Serializable):
            number: int = field(metadata={'codec': U8})
            digest: bytes = field(metadata={'codec': H256})

        for value in (Packet(256, bytes(32)), Packet(1, b'short')):
            with self.subTest(value=value):
                with self.assertRaises(ScaleEncodeException):
                    value.to_jam_bytes()

    def test_binary_encoding_preserves_custom_encoder(self):
        class PrefixedCodec(StructObject):
            def encode(self, value=None):
                return JamBytes(b'\xaa' + super().encode(value).to_bytes())

        @dataclass
        class Packet(Serializable):
            number: int
            _codec_type_def = Struct(number=U8).impl(PrefixedCodec)

        self.assertEqual(b'\xaa\x07', Packet(7).to_jam_bytes().to_bytes())

    def test_binary_encoding_preserves_custom_validation_hook(self):
        class ValidatedCodec(StructObject):
            def deserialize(self, value):
                if self._data is not None:
                    raise ScaleDeserializeException('custom post-encode validation')
                return super().deserialize(value)

        @dataclass
        class Packet(Serializable):
            number: int
            _codec_type_def = Struct(number=U8).impl(ValidatedCodec)

        with self.assertRaisesRegex(ScaleDeserializeException, 'custom post-encode validation'):
            Packet(7).to_jam_bytes()


if __name__ == '__main__':
    unittest.main()
