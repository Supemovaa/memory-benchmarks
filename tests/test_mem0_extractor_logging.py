from __future__ import annotations

import asyncio
import importlib.util
import json
import textwrap
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
PATCH_PATH = ROOT / "docker/mem0/patch_mem0_extractor_logging.py"


_FIXTURE_BODY = '''
def sync_extract(self):
    uuid_mapping = {"0": "uuid-0", "1": "uuid-1"}
    response = self.llm.generate_response(messages=[], response_format={"type": "json_object"})
    # Parse response
    try:
        response = remove_code_blocks(response)
        if not response or not response.strip():
            extracted_memories = []
        else:
            try:
                extracted_memories = json.loads(response, strict=False).get("memory", [])
            except json.JSONDecodeError:
                extracted_json = extract_json(response)
                extracted_memories = json.loads(extracted_json, strict=False).get("memory", [])
    except Exception as e:
        logger.error(f"Error parsing extraction response: {e}")
        extracted_memories = []

    if not extracted_memories:
        return []
    mem_texts = [m.get("text", "") for m in extracted_memories if m.get("text")]
    for mem in extracted_memories:
        text = mem.get("text")
    return mem_texts

async def async_extract(self):
    uuid_mapping = {"0": "uuid-0", "1": "uuid-1"}
    response = await self.llm.generate_response(messages=[], response_format={"type": "json_object"})
    # Parse response
    try:
        response = remove_code_blocks(response)
        if not response or not response.strip():
            extracted_memories = []
        else:
            try:
                extracted_memories = json.loads(response, strict=False).get("memory", [])
            except json.JSONDecodeError:
                extracted_json = extract_json(response)
                extracted_memories = json.loads(extracted_json, strict=False).get("memory", [])
    except Exception as e:
        logger.error(f"Error parsing extraction response (async): {e}")
        extracted_memories = []

    if not extracted_memories:
        return []
    mem_texts = [m.get("text", "") for m in extracted_memories if m.get("text")]
    for mem in extracted_memories:
        text = mem.get("text")
    return mem_texts
'''

FIXTURE = "class Dummy:\n" + textwrap.indent(textwrap.dedent(_FIXTURE_BODY), "    ")


def load_patch_module():
    spec = importlib.util.spec_from_file_location("patch_mem0_extractor_logging", PATCH_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExtractorLoggingPatchTests(unittest.TestCase):
    def test_docker_build_runs_extractor_logging_patch(self) -> None:
        dockerfile = (ROOT / "docker/mem0/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("python /app/patch_mem0_extractor_logging.py", dockerfile)

    def test_patch_logs_raw_response_and_normalizes_both_pipelines(self) -> None:
        module = load_patch_module()
        patched = module.patch_source(FIXTURE)

        self.assertEqual(patched.count("raw_response = response"), 2)
        self.assertEqual(patched.count("Invalid extractor memory schema"), 4)
        self.assertEqual(patched.count("Error normalizing extracted memories"), 2)
        self.assertEqual(patched.count("raw_response=%r"), 8)
        self.assertLess(patched.index("raw_response = response"), patched.index("remove_code_blocks"))
        self.assertIn("isinstance(extracted_memories, list)", patched)
        self.assertIn("isinstance(item, dict)", patched)
        self.assertIn("for item in extracted_memories", patched)
        compile(patched, "patched_mem0_main.py", "exec")
        self.assertEqual(module.patch_source(patched), patched)

    def test_patch_salvages_text_strings_but_drops_existing_memory_ids(self) -> None:
        module = load_patch_module()
        patched = module.patch_source(FIXTURE)
        logger = Mock()
        namespace = {
            "json": json,
            "logger": logger,
            "remove_code_blocks": lambda value: value,
            "extract_json": lambda value: value,
        }
        exec(patched, namespace)

        raw_response = json.dumps({
            "memory": [
                {"id": "0", "text": "A valid dictionary memory"},
                "A useful memory missing its object wrapper",
                "1",
                "uuid-0",
                7,
            ]
        })

        class FakeLLM:
            def generate_response(self, **kwargs):
                return raw_response

        instance = namespace["Dummy"]()
        instance.llm = FakeLLM()

        self.assertEqual(
            instance.sync_extract(),
            ["A valid dictionary memory", "A useful memory missing its object wrapper"],
        )
        self.assertTrue(logger.error.called)

    def test_patch_reraises_unrecoverable_json_in_both_pipelines(self) -> None:
        module = load_patch_module()
        patched = module.patch_source(FIXTURE)
        logger = Mock()

        class LLMError(Exception):
            pass

        namespace = {
            "json": json,
            "logger": logger,
            "LLMError": LLMError,
            "remove_code_blocks": lambda value: value,
            "extract_json": lambda value: value,
        }
        exec(patched, namespace)

        truncated_response = '{"memory": [{"id": "0", "text": "truncated'

        class SyncLLM:
            def generate_response(self, **kwargs):
                return truncated_response

        class AsyncLLM:
            async def generate_response(self, **kwargs):
                return truncated_response

        sync_instance = namespace["Dummy"]()
        sync_instance.llm = SyncLLM()
        with self.assertRaisesRegex(LLMError, "Error parsing extraction response"):
            sync_instance.sync_extract()

        async_instance = namespace["Dummy"]()
        async_instance.llm = AsyncLLM()
        with self.assertRaisesRegex(LLMError, "Error parsing extraction response"):
            asyncio.run(async_instance.async_extract())

        self.assertEqual(logger.error.call_count, 2)

    def test_patch_upgrades_existing_parse_error_swallowing_version(self) -> None:
        module = load_patch_module()
        old_patched = module.patch_source(FIXTURE)
        old_patched = old_patched.replace(
            '            raise LLMError(f"Error parsing extraction response: {e}") from e\n',
            "            extracted_memories = []\n",
        ).replace(
            '            raise LLMError(f"Error parsing extraction response (async): {e}") from e\n',
            "            extracted_memories = []\n",
        )

        upgraded = module.patch_source(old_patched)

        self.assertEqual(upgraded.count("raise LLMError(f\"Error parsing extraction response"), 2)
        self.assertEqual(module.patch_source(upgraded), upgraded)

    def test_patch_fails_loudly_when_one_pipeline_anchor_is_missing(self) -> None:
        module = load_patch_module()
        incomplete = FIXTURE.replace(
            '    mem_texts = [m.get("text", "") for m in extracted_memories if m.get("text")]\n',
            "",
            1,
        )
        with self.assertRaisesRegex(RuntimeError, "mem_texts anchors"):
            module.patch_source(incomplete)


if __name__ == "__main__":
    unittest.main()
