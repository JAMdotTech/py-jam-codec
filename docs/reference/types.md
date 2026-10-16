`BoundedVec(type_def, maximum, minimum=0, multiple=1)` uses the same wire
encoding as `Vec`, with an inclusive range for the element count and an optional
divisibility requirement. Invalid counts and non-canonical `VarInt64` length
prefixes raise `ValueError` before any elements are constructed or decoded.
Encoding and deserialization enforce the same count constraints.

```python
from jamcodec.base import JamBytes
from jamcodec.types import BoundedVec, U16

codec = BoundedVec(U16, maximum=6, minimum=2, multiple=2)
encoded = codec.encode([1, 2])  # JamBytes('0x0201000200')
assert codec.new().decode(encoded) == [1, 2]
```

`BoundedVec(U8, ...)` follows `Vec(U8)` byte semantics: decoding produces bytes
(a hex string through `.new().decode()`), and bounds count bytes even for hex
or UTF-8 string inputs. Constructor bounds must be integers satisfying
`0 <= minimum <= maximum`, with a positive integer `multiple`.

::: jamcodec.types
