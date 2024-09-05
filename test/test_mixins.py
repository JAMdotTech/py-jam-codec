import enum
import json
import os
import unittest
from dataclasses import dataclass, field
from os import path
from typing import Optional, Type, Union, List

from jamcodec.base import JamBytes, JamCodecType
from jamcodec.mixins import Serializable, T
from jamcodec.types import H256, U8, Array, Enum, Option, Null, Bytes


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


if __name__ == '__main__':
    unittest.main()
