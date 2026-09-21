"""Provider adapter. The only package that may import litellm.

Everything outside this package depends only on `Provider`, `Message`,
`TokenUsage` and `StructuredResult` — never on a vendor SDK. See
`tests/test_no_llm_import_leak.py`, which is the PB0 risk mitigation this
package exists to satisfy.
"""

from probative.llm.fake import FakeProvider
from probative.llm.litellm_provider import LiteLLMProvider
from probative.llm.provider import Provider
from probative.llm.types import Message, StructuredResult, TokenUsage

__all__ = [
    "FakeProvider",
    "LiteLLMProvider",
    "Message",
    "Provider",
    "StructuredResult",
    "TokenUsage",
]
