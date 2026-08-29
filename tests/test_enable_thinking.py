from __future__ import annotations

import asyncio
import importlib.util
import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from benchmarks.common import llm_client
from benchmarks.common.llm_client import LLMClient


ROOT = Path(__file__).resolve().parents[1]


class _FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        content = '{"label": "CORRECT"}' if "response_format" in kwargs else "ok"
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content),
                    finish_reason="stop",
                )
            ]
        )


def _make_client(enable_thinking: bool | None) -> tuple[LLMClient, _FakeCompletions]:
    client = LLMClient(
        model="qwen3.6-max-preview",
        provider="openai",
        api_key="test-key",
        max_retries=1,
        enable_thinking=enable_thinking,
    )
    completions = _FakeCompletions()
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions


class EnableThinkingParserTests(unittest.TestCase):
    def test_optional_bool_env_supports_true_false_and_none(self) -> None:
        parser = getattr(llm_client, "parse_optional_bool_env", None)
        self.assertTrue(callable(parser), "parse_optional_bool_env is missing")

        for raw, expected in (("true", True), ("FALSE", False), ("none", None)):
            with self.subTest(raw=raw), patch.dict(os.environ, {"TEST_THINKING": raw}):
                self.assertIs(parser("TEST_THINKING"), expected)

    def test_optional_bool_env_rejects_invalid_values(self) -> None:
        parser = getattr(llm_client, "parse_optional_bool_env", None)
        self.assertTrue(callable(parser), "parse_optional_bool_env is missing")

        for raw in ("sometimes", "", "null", "1", "0", "yes", "no", "on", "off"):
            with self.subTest(raw=raw), patch.dict(os.environ, {"TEST_THINKING": raw}):
                with self.assertRaisesRegex(ValueError, "TEST_THINKING"):
                    parser("TEST_THINKING")


class LLMClientEnableThinkingTests(unittest.IsolatedAsyncioTestCase):
    async def test_text_generation_sends_true_and_false(self) -> None:
        for value in (True, False):
            with self.subTest(value=value):
                client, completions = _make_client(value)
                await client.generate(system="", user="hello")
                self.assertEqual(
                    completions.calls[0].get("extra_body"),
                    {"enable_thinking": value},
                )

    async def test_text_generation_omits_parameter_for_none(self) -> None:
        client, completions = _make_client(None)
        await client.generate(system="", user="hello")
        self.assertNotIn("extra_body", completions.calls[0])

    async def test_structured_generation_uses_same_setting(self) -> None:
        client, completions = _make_client(False)
        result = await client.generate_structured(system="judge", user="hello")
        self.assertEqual(result, {"label": "CORRECT"})
        self.assertEqual(
            completions.calls[0].get("extra_body"),
            {"enable_thinking": False},
        )


class RoleWiringTests(unittest.TestCase):
    def test_every_benchmark_wires_answerer_and_judge_variables(self) -> None:
        for relative in (
            "benchmarks/locomo/run.py",
            "benchmarks/longmemeval/run.py",
            "benchmarks/beam/run.py",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(file=relative, role="answerer"):
                self.assertRegex(
                    source,
                    re.compile(
                        r"LLMClient\([\s\S]{0,300}?enable_thinking="
                        r"parse_optional_bool_env\(\"ANSWERER_ENABLE_THINKING\"\)"
                    ),
                )
            with self.subTest(file=relative, role="judge"):
                self.assertRegex(
                    source,
                    re.compile(
                        r"LLMClient\([\s\S]{0,300}?enable_thinking="
                        r"parse_optional_bool_env\(\"JUDGE_ENABLE_THINKING\"\)"
                    ),
                )


class ExtractorPatchTests(unittest.TestCase):
    def test_mem0_patch_injects_tristate_request_parameter(self) -> None:
        patch_path = ROOT / "docker/mem0/patch_mem0_enable_thinking.py"
        self.assertTrue(patch_path.exists(), "mem0 enable_thinking patch is missing")

        spec = importlib.util.spec_from_file_location("patch_mem0_enable_thinking", patch_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        fixture = '''import os


class LLMBase:
    pass


class OpenAILLM(LLMBase):
    def generate_response(self):
        params = {"model": "test"}
        response = self.client.chat.completions.create(**params)
        return response
'''
        patched = module.patch_source(fixture)

        self.assertIn('"EXTRACTOR_ENABLE_THINKING"', patched)
        self.assertIn('extra_body["enable_thinking"] = enable_thinking', patched)
        self.assertEqual(module.patch_source(patched), patched)
        compile(patched, "patched_mem0_openai.py", "exec")

        namespace = {}
        exec(patched, namespace)
        parser = namespace["_parse_optional_bool_env"]
        for raw, expected in (("true", True), (" FALSE ", False), ("none", None)):
            with self.subTest(raw=raw), patch.dict(os.environ, {"TEST_THINKING": raw}):
                self.assertIs(parser("TEST_THINKING"), expected)
        for raw in ("", "null", "1", "0", "yes", "no", "on", "off"):
            with self.subTest(raw=raw), patch.dict(os.environ, {"TEST_THINKING": raw}):
                with self.assertRaisesRegex(ValueError, "TEST_THINKING"):
                    parser("TEST_THINKING")

    def test_docker_build_runs_patch_and_forwards_extractor_variable(self) -> None:
        dockerfile = (ROOT / "docker/mem0/Dockerfile").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("python /app/patch_mem0_enable_thinking.py", dockerfile)
        self.assertIn(
            "EXTRACTOR_ENABLE_THINKING=${EXTRACTOR_ENABLE_THINKING:-none}",
            compose,
        )


class EnvironmentDefaultsTests(unittest.TestCase):
    def test_env_files_default_all_roles_to_none(self) -> None:
        for relative in (".env.example",):
            values = {}
            for line in (ROOT / relative).read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip()

            with self.subTest(file=relative):
                self.assertEqual(values.get("EXTRACTOR_ENABLE_THINKING"), "none")
                self.assertEqual(values.get("ANSWERER_ENABLE_THINKING"), "none")
                self.assertEqual(values.get("JUDGE_ENABLE_THINKING"), "none")

    def test_local_env_has_valid_values_for_all_roles(self) -> None:
        values = {}
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().lower()

        for name in (
            "EXTRACTOR_ENABLE_THINKING",
            "ANSWERER_ENABLE_THINKING",
            "JUDGE_ENABLE_THINKING",
        ):
            with self.subTest(name=name):
                self.assertIn(values.get(name), {"true", "false", "none"})


if __name__ == "__main__":
    unittest.main()
