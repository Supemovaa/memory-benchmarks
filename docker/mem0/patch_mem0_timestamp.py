"""Patch mem0 OSS add() so timestamps reach extraction and storage.

The upstream OSS API exposes ``timestamp`` but currently rejects or drops it
before the additive extraction prompt is built. The benchmark sends Unix epoch
seconds for LOCOMO session dates, so normalize those values to an ISO date for
the prompt and a full UTC ISO timestamp for memory metadata. This script runs
during the image build and fails loudly if the upstream source changes shape
instead of silently producing an unpatched image.
"""

from pathlib import Path


TARGET = Path("/usr/local/lib/python3.12/site-packages/mem0/memory/main.py")

PROMPT_HELPER = '''\n\ndef _coerce_timestamp_for_prompt(timestamp: Optional[Any]) -> Optional[str]:\n    """Convert benchmark timestamps to the ISO date expected by prompts."""\n    if timestamp is None:\n        return None\n    if isinstance(timestamp, (int, float)):\n        return datetime.fromtimestamp(timestamp, timezone.utc).date().isoformat()\n    return str(timestamp)\n'''

STORAGE_HELPER = '''\n\ndef _coerce_timestamp_for_storage(timestamp: Optional[Any]) -> Optional[str]:\n    """Convert benchmark timestamps to a full UTC ISO timestamp for storage."""\n    if timestamp is None:\n        return None\n    if isinstance(timestamp, (int, float)):\n        return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()\n    if isinstance(timestamp, datetime):\n        if timestamp.tzinfo is None:\n            timestamp = timestamp.replace(tzinfo=timezone.utc)\n        return timestamp.astimezone(timezone.utc).isoformat()\n\n    value = str(timestamp)\n    try:\n        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))\n    except ValueError:\n        return value\n    if parsed.tzinfo is None:\n        parsed = parsed.replace(tzinfo=timezone.utc)\n    return parsed.astimezone(timezone.utc).isoformat()\n'''


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

    async_temporal_guard = '''        if timestamp is not None:\n            raise ValueError(await get_temporal_feature_error_message_async("async", "add", "timestamp"))\n'''
    if async_temporal_guard in source:
        source = source.replace(
            async_temporal_guard,
            '''        # Timestamp is supported by the benchmark OSS path.\n''',
            1,
        )
    elif source.count("# Timestamp is supported by the benchmark OSS path.") < 2:
        raise RuntimeError("mem0 AsyncMemory.add() timestamp guard was not found")

    anchor = "\n\ndef _build_filters_and_metadata("
    if "def _coerce_timestamp_for_prompt(" not in source:
        if anchor not in source:
            raise RuntimeError("mem0 timestamp helper insertion point was not found")
        source = source.replace(anchor, PROMPT_HELPER + anchor, 1)
    if "def _coerce_timestamp_for_storage(" not in source:
        if anchor not in source:
            raise RuntimeError("mem0 storage timestamp helper insertion point was not found")
        source = source.replace(anchor, STORAGE_HELPER + anchor, 1)

    old_signature = "    def _add_to_vector_store(self, messages, metadata, filters, infer, prompt=None):"
    new_signature = "    def _add_to_vector_store(self, messages, metadata, filters, infer, prompt=None, timestamp=None):"
    if old_signature in source:
        source = source.replace(old_signature, new_signature, 1)
    elif new_signature not in source:
        raise RuntimeError("mem0 _add_to_vector_store() signature was not found")

    old_async_signature = '''    async def _add_to_vector_store(
        self,
        messages: list,
        metadata: dict,
        effective_filters: dict,
        infer: bool,
        prompt: Optional[str] = None,
    ):'''
    new_async_signature = '''    async def _add_to_vector_store(
        self,
        messages: list,
        metadata: dict,
        effective_filters: dict,
        infer: bool,
        prompt: Optional[str] = None,
        timestamp: Optional[str] = None,
    ):'''
    if old_async_signature in source:
        source = source.replace(old_async_signature, new_async_signature, 1)
    elif new_async_signature not in source:
        raise RuntimeError("mem0 async _add_to_vector_store() signature was not found")

    old_sync_metadata = '''            input_metadata=metadata,
        )
        if normalized_expiration_date is not None:'''
    new_sync_metadata = '''            input_metadata=metadata,
        )
        storage_timestamp = _coerce_timestamp_for_storage(timestamp)
        if storage_timestamp is not None:
            processed_metadata["created_at"] = storage_timestamp
            processed_metadata["updated_at"] = storage_timestamp
        if normalized_expiration_date is not None:'''
    if old_sync_metadata in source:
        source = source.replace(old_sync_metadata, new_sync_metadata, 1)
    elif new_sync_metadata not in source:
        raise RuntimeError("mem0 Memory.add() storage metadata insertion point was not found")

    old_async_metadata = '''        processed_metadata, effective_filters = _build_filters_and_metadata(
            user_id=user_id, agent_id=agent_id, run_id=run_id, input_metadata=metadata
        )
        if normalized_expiration_date is not None:'''
    new_async_metadata = '''        processed_metadata, effective_filters = _build_filters_and_metadata(
            user_id=user_id, agent_id=agent_id, run_id=run_id, input_metadata=metadata
        )
        storage_timestamp = _coerce_timestamp_for_storage(timestamp)
        if storage_timestamp is not None:
            processed_metadata["created_at"] = storage_timestamp
            processed_metadata["updated_at"] = storage_timestamp
        if normalized_expiration_date is not None:'''
    if old_async_metadata in source:
        source = source.replace(old_async_metadata, new_async_metadata, 1)
    elif new_async_metadata not in source:
        raise RuntimeError("mem0 AsyncMemory.add() storage metadata insertion point was not found")

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

    old_async_call = (
        "        vector_store_result = await self._add_to_vector_store("
        "messages, processed_metadata, effective_filters, infer, prompt=prompt)"
    )
    new_async_call = (
        "        vector_store_result = await self._add_to_vector_store("
        "messages, processed_metadata, effective_filters, infer, prompt=prompt, "
        "timestamp=_coerce_timestamp_for_prompt(timestamp))"
    )
    if old_async_call in source:
        source = source.replace(old_async_call, new_async_call, 1)
    elif new_async_call not in source:
        raise RuntimeError("mem0 AsyncMemory.add() vector-store call was not found")

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
        source = source.replace(old_prompt_call, new_prompt_call)
    if source.count(new_prompt_call) < 2:
        raise RuntimeError("mem0 sync/async extraction prompt calls were not found")

    old_history_timestamp = '''                "created_at": r[3].get("created_at"),
                "is_deleted": 0,'''
    new_history_timestamp = '''                "created_at": r[3].get("created_at"),
                "updated_at": r[3].get("updated_at"),
                "is_deleted": 0,'''
    if old_history_timestamp in source:
        source = source.replace(old_history_timestamp, new_history_timestamp)
    if source.count(new_history_timestamp) < 2:
        raise RuntimeError("mem0 sync/async batch history timestamps were not found")

    old_sync_history_fallback = (
        '                    self.db.add_history(hr["memory_id"], None, hr["new_memory"], "ADD", '
        'created_at=hr.get("created_at"))'
    )
    new_sync_history_fallback = '''                    self.db.add_history(
                        hr["memory_id"], None, hr["new_memory"], "ADD",
                        created_at=hr.get("created_at"),
                        updated_at=hr.get("updated_at"),
                    )'''
    if old_sync_history_fallback in source:
        source = source.replace(old_sync_history_fallback, new_sync_history_fallback, 1)
    elif new_sync_history_fallback not in source:
        raise RuntimeError("mem0 sync history fallback timestamps were not found")

    old_async_history_fallback = '''                        self.db.add_history, hr["memory_id"], None, hr["new_memory"], "ADD",
                        created_at=hr.get("created_at")
                    )'''
    new_async_history_fallback = '''                        self.db.add_history, hr["memory_id"], None, hr["new_memory"], "ADD",
                        created_at=hr.get("created_at"),
                        updated_at=hr.get("updated_at"),
                    )'''
    if old_async_history_fallback in source:
        source = source.replace(old_async_history_fallback, new_async_history_fallback, 1)
    elif new_async_history_fallback not in source:
        raise RuntimeError("mem0 async history fallback timestamps were not found")

    TARGET.write_text(source, encoding="utf-8")
    print(f"Patched {TARGET}: timestamp guards, prompt forwarding, and storage metadata")


if __name__ == "__main__":
    main()
