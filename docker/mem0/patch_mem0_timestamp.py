"""Patch mem0 OSS add() so timestamps reach the extraction prompt.

The upstream OSS API exposes ``timestamp`` but currently rejects or drops it
before the additive extraction prompt is built. The benchmark sends Unix epoch
seconds for LOCOMO session dates, so normalize those values to an ISO date.
This script runs during the image build and fails loudly if the upstream source
changes shape instead of silently producing an unpatched image.
"""

from pathlib import Path


TARGET = Path("/usr/local/lib/python3.12/site-packages/mem0/memory/main.py")

HELPER = '''\n\ndef _coerce_timestamp_for_prompt(timestamp: Optional[Any]) -> Optional[str]:\n    """Convert benchmark timestamps to the ISO date expected by prompts."""\n    if timestamp is None:\n        return None\n    if isinstance(timestamp, (int, float)):\n        return datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()\n    return str(timestamp)\n'''


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")

    temporal_guard = '''        if timestamp is not None:\n            raise ValueError(get_temporal_feature_error_message("sync", "add", "timestamp"))\n'''
    if temporal_guard in source:
        source = source.replace(
            temporal_guard,
            '''        # Timestamp is supported by the benchmark OSS path.\n''',
            1,
        )
    elif "# Timestamp is supported by the benchmark OSS path." not in source:
        raise RuntimeError("mem0 Memory.add() timestamp guard was not found")

    anchor = "\n\ndef _build_filters_and_metadata("
    if "def _coerce_timestamp_for_prompt(" not in source:
        if anchor not in source:
            raise RuntimeError("mem0 timestamp helper insertion point was not found")
        source = source.replace(anchor, HELPER + anchor, 1)

    old_signature = "    def _add_to_vector_store(self, messages, metadata, filters, infer, prompt=None):"
    new_signature = "    def _add_to_vector_store(self, messages, metadata, filters, infer, prompt=None, timestamp=None):"
    if old_signature in source:
        source = source.replace(old_signature, new_signature, 1)
    elif new_signature not in source:
        raise RuntimeError("mem0 _add_to_vector_store() signature was not found")

    old_call = (
        "        vector_store_result = self._add_to_vector_store("
        "messages, processed_metadata, effective_filters, infer, prompt=prompt)"
    )
    new_call = (
        "        vector_store_result = self._add_to_vector_store("
        "messages, processed_metadata, effective_filters, infer, prompt=prompt, "
        "timestamp=_coerce_timestamp_for_prompt(timestamp))"
    )
    if old_call in source:
        source = source.replace(old_call, new_call, 1)
    elif new_call not in source:
        raise RuntimeError("mem0 Memory.add() vector-store call was not found")

    old_prompt_call = (
        "        user_prompt = generate_additive_extraction_prompt(\n"
        "            existing_memories=existing_memories,\n"
        "            new_messages=parsed_messages,\n"
        "            last_k_messages=last_messages,\n"
        "            custom_instructions=custom_instr,\n"
        "        )"
    )
    new_prompt_call = (
        "        user_prompt = generate_additive_extraction_prompt(\n"
        "            existing_memories=existing_memories,\n"
        "            new_messages=parsed_messages,\n"
        "            last_k_messages=last_messages,\n"
        "            custom_instructions=custom_instr,\n"
        "            timestamp=timestamp,\n"
        "        )"
    )
    if old_prompt_call in source:
        source = source.replace(old_prompt_call, new_prompt_call, 1)
    elif new_prompt_call not in source:
        raise RuntimeError("mem0 extraction prompt call was not found")

    TARGET.write_text(source, encoding="utf-8")
    print(f"Patched {TARGET}: timestamp guard, normalization, and prompt forwarding")


if __name__ == "__main__":
    main()
