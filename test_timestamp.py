#!/usr/bin/env python3
"""Test if timestamp is correctly propagated to created_at/updated_at in mem0."""

import asyncio
import os
from datetime import datetime, timezone

# Set up minimal environment
os.environ.setdefault("OPENAI_API_KEY", "dummy-key-for-test")

from benchmarks.common.mem0_client import Mem0Client


async def main():
    # Connect to local mem0 OSS server
    client = Mem0Client(mode="oss", host="http://localhost:8888")

    # Test timestamp: 2021-01-01 00:00:00 UTC
    test_timestamp = 1609459200
    expected_iso = "2021-01-01T00:00:00+00:00"

    test_user = "timestamp_test_user"

    print(f"Testing timestamp propagation to created_at/updated_at")
    print(f"Test timestamp (epoch): {test_timestamp}")
    print(f"Expected ISO format: {expected_iso}")
    print()

    # Add a memory with timestamp
    messages = [
        {"role": "user", "content": "I love Python programming and machine learning"}
    ]

    print("Adding memory with timestamp...")
    add_result = await client.add(messages, test_user, timestamp=test_timestamp)

    if add_result:
        print(f"✓ Add successful, extracted {len(add_result.get('results', []))} memories")
        for mem in add_result.get('results', []):
            print(f"  - {mem.get('event')}: {mem.get('memory', '')[:80]}")
    else:
        print("✗ Add failed")
        return

    print()

    # Search and check timestamps
    print("Searching for memories...")
    search_results = await client.search("Python", test_user, top_k=10)

    if not search_results:
        print("✗ No search results")
        return

    print(f"✓ Found {len(search_results)} memories\n")

    # Check first result
    print("Checking first memory timestamps:")
    first = search_results[0]
    print(f"  Memory: {first.get('memory', '')[:80]}")
    print(f"  created_at: {first.get('created_at', 'MISSING')}")
    print(f"  updated_at: {first.get('updated_at', 'MISSING')}")
    print()

    # Verify
    created_at = first.get('created_at', '')
    updated_at = first.get('updated_at', '')

    print("Verification:")
    if expected_iso in str(created_at):
        print(f"  ✓ created_at matches expected timestamp")
    else:
        print(f"  ✗ created_at DOES NOT match!")
        print(f"    Expected: {expected_iso}")
        print(f"    Got: {created_at}")

    if expected_iso in str(updated_at):
        print(f"  ✓ updated_at matches expected timestamp")
    else:
        print(f"  ✗ updated_at DOES NOT match!")
        print(f"    Expected: {expected_iso}")
        print(f"    Got: {updated_at}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
