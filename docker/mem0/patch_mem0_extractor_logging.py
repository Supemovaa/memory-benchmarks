"""Patch Mem0 extraction to log raw responses and classify malformed items.

The extractor contract is ``{"memory": [{"id": "0", "text": "..."}]}``,
but some responses mix memory dictionaries and string IDs. Upstream calls
``.get`` on every item, turning that malformed-but-parseable response into a
500. This patch logs the original response and removes malformed items before
the rest of the memory pipeline accesses them. Unrecoverable JSON parse
failures are logged and re-raised so the API returns HTTP 500 and callers can
use their existing retry policy instead of silently losing a chunk.
"""

from pathlib import Path


TARGET = Path("/usr/local/lib/python3.12/site-packages/mem0/memory/main.py")
RAW_MARKER = "raw_response = response"
SCHEMA_MARKER = "Invalid extractor memory schema"
NORMALIZE_MARKER = "Error normalizing extracted memories"
SYNC_PARSE_RERAISE = '            raise LLMError(f"Error parsing extraction response: {e}") from e\n'
ASYNC_PARSE_RERAISE = '            raise LLMError(f"Error parsing extraction response (async): {e}") from e\n'


def _require_count(source: str, needle: str, expected: int, label: str) -> None:
    actual = source.count(needle)
    if actual != expected:
        raise RuntimeError(f"{label}: expected {expected} matches, found {actual}")


def patch_source(source: str) -> str:
    """Return source with raw-response logging and schema filtering injected."""
    marker_counts = (
        source.count(RAW_MARKER),
        source.count(SCHEMA_MARKER),
        source.count(NORMALIZE_MARKER),
    )
    if marker_counts == (2, 4, 2):
        # The first version of this patch logged parse failures but converted
        # them into an empty extraction.  Upgrade that already-patched source
        # in place so unrecoverable JSON errors propagate to FastAPI (HTTP 500)
        # and the existing client retry loop can handle them.
        old_sync_parse = (
            '            logger.error(\n'
            '                "Error parsing extraction response: %s; raw_response=%r",\n'
            '                e,\n'
            '                raw_response,\n'
            '                exc_info=True,\n'
            '            )\n'
            '            extracted_memories = []\n'
        )
        old_async_parse = (
            '            logger.error(\n'
            '                "Error parsing extraction response (async): %s; raw_response=%r",\n'
            '                e,\n'
            '                raw_response,\n'
            '                exc_info=True,\n'
            '            )\n'
            '            extracted_memories = []\n'
        )
        source = source.replace(old_sync_parse, (
            old_sync_parse.rsplit("            extracted_memories = []\n", 1)[0]
            + SYNC_PARSE_RERAISE
        ), 1)
        source = source.replace(old_async_parse, (
            old_async_parse.rsplit("            extracted_memories = []\n", 1)[0]
            + ASYNC_PARSE_RERAISE
        ), 1)
        if source.count("exc_info=True") < 4:
            raise RuntimeError("extractor logging patch is only partially applied")
        if source.count(SYNC_PARSE_RERAISE) != 1 or source.count(ASYNC_PARSE_RERAISE) != 1:
            raise RuntimeError("extractor logging patch is only partially applied")
        return source
    if any(marker_counts):
        raise RuntimeError("extractor logging patch is only partially applied")

    parse_anchor = "        # Parse response\n        try:"
    parse_sync_old = (
        '        except Exception as e:\n'
        '            logger.error(f"Error parsing extraction response: {e}")\n'
        '            extracted_memories = []\n'
    )
    parse_async_old = (
        '        except Exception as e:\n'
        '            logger.error(f"Error parsing extraction response (async): {e}")\n'
        '            extracted_memories = []\n'
    )
    normalize_anchor = (
        '        mem_texts = [m.get("text", "") for m in extracted_memories if m.get("text")]\n'
    )
    schema_anchor = "            extracted_memories = []\n\n        if not extracted_memories:"

    _require_count(source, parse_anchor, 2, "parse anchors")
    _require_count(source, parse_sync_old, 1, "sync parse block")
    _require_count(source, parse_async_old, 1, "async parse block")
    _require_count(source, normalize_anchor, 2, "mem_texts anchors")
    _require_count(source, schema_anchor, 2, "schema anchors")

    # Install schema filtering before replacing the parse exception blocks:
    # those blocks contain the ``extracted_memories = []`` text used as the
    # schema insertion anchor.
    schema_block = """            extracted_memories = []

        if not isinstance(extracted_memories, list):
            logger.error(
                "Invalid extractor memory schema; raw_response=%r; extracted_memories=%r",
                raw_response,
                extracted_memories,
            )
            extracted_memories = []
        else:
            invalid_items = []
            normalized_memories = []
            existing_memory_ids = set(uuid_mapping) | set(uuid_mapping.values())
            for item in extracted_memories:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        normalized_memories.append(item)
                    else:
                        invalid_items.append(item)
                elif isinstance(item, str) and item.strip():
                    text = item.strip()
                    if text.isdigit() or text in existing_memory_ids:
                        invalid_items.append(item)
                    else:
                        normalized_memories.append({
                            "id": str(len(normalized_memories)),
                            "text": text,
                        })
                else:
                    invalid_items.append(item)

            if invalid_items:
                logger.error(
                    "Invalid extractor memory schema; raw_response=%r; invalid_items=%r",
                    raw_response,
                    invalid_items,
                )
            extracted_memories = normalized_memories

        if not extracted_memories:"""
    source = source.replace(schema_anchor, schema_block, 2)

    source = source.replace(
        parse_anchor,
        "        # Parse response\n        raw_response = response\n        try:",
        2,
    )
    source = source.replace(
        parse_sync_old,
        """        except Exception as e:
            logger.error(
                "Error parsing extraction response: %s; raw_response=%r",
                e,
                raw_response,
                exc_info=True,
            )
            raise LLMError(f"Error parsing extraction response: {e}") from e
""",
        1,
    )
    source = source.replace(
        parse_async_old,
        """        except Exception as e:
            logger.error(
                "Error parsing extraction response (async): %s; raw_response=%r",
                e,
                raw_response,
                exc_info=True,
            )
            raise LLMError(f"Error parsing extraction response (async): {e}") from e
""",
        1,
    )

    normalize_block = """        try:
            mem_texts = [m.get("text", "") for m in extracted_memories if m.get("text")]
        except Exception:
            logger.error(
                "Error normalizing extracted memories; raw_response=%r; extracted_memories=%r",
                raw_response,
                extracted_memories,
                exc_info=True,
            )
            raise
"""
    source = source.replace(normalize_anchor, normalize_block, 2)

    _require_count(source, RAW_MARKER, 2, "raw response assignments")
    _require_count(source, SCHEMA_MARKER, 4, "schema log branches")
    _require_count(source, NORMALIZE_MARKER, 2, "normalization log blocks")
    if source.count("exc_info=True") != 4:
        raise RuntimeError("extractor logging patch produced an unexpected log count")
    return source


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")
    TARGET.write_text(patch_source(source), encoding="utf-8")
    print(f"Patched {TARGET}: raw extractor logging and schema filtering")


if __name__ == "__main__":
    main()
