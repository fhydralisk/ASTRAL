"""Preserve the spacing already provided in streamed reasoning fragments."""
from sr_harness.core import APICallSample


def test_reasoning_fragments_keep_provider_spacing():
    sample = APICallSample(None, message_extra={"reasoning_details": [
        {"text": "This"}, {"text": " looks"}, {"text": " like an oscillator.\nNext paragraph."},
    ]})
    assert sample.reasoning == "This looks like an oscillator.\nNext paragraph."
