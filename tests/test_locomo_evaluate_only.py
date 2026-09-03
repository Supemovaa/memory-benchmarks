from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarks.locomo.run import (
    _evaluate_saved_locomo_question,
    apply_locomo_judge_to_saved_result,
)


class _TrackingLLM:
    def __init__(self, shared: dict[str, int]) -> None:
        self.shared = shared
        self.max_active = 0

    async def _run(self, response):
        self.shared["active"] += 1
        self.max_active = max(self.max_active, self.shared["active"])
        await asyncio.sleep(0.01)
        self.shared["active"] -= 1
        return response

    async def generate(self, **kwargs):
        return await self._run("generated answer")

    async def generate_structured(self, **kwargs):
        return await self._run({"label": "CORRECT", "reasoning": "ok"})


class LoCoMoEvaluateOnlyConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_cutoffs_run_concurrently_with_global_limit(self) -> None:
        shared = {"active": 0}
        answerer = _TrackingLLM(shared)
        judge = _TrackingLLM(shared)
        result = {
            "question": "When was the event?",
            "reference_date": None,
            "retrieval": {"search_results": [{"memory": "The event was in May."}]},
        }
        qa = {"category": 2, "answer": "May", "evidence": []}

        await apply_locomo_judge_to_saved_result(
            result,
            qa,
            conv_idx=0,
            answerer=answerer,
            judge_llm=judge,
            cutoffs=[10, 20, 50, 100],
            evidence_lookup=None,
            cutoff_semaphore=asyncio.Semaphore(2),
        )

        self.assertGreaterEqual(max(answerer.max_active, judge.max_active), 2)
        self.assertLessEqual(max(answerer.max_active, judge.max_active), 2)
        self.assertEqual(
            list(result["cutoff_results"]),
            ["top_10", "top_20", "top_50", "top_100"],
        )

    async def test_writes_question_once_after_all_cutoffs(self) -> None:
        source = Path(
            "results/locomo/predicted_locomo-qwen25-7b-instruct-extract/conv0_q8.json"
        )
        if not source.exists():
            self.skipTest("the requested LOCOMO prediction fixture is not available")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory, "conv0_q8.json")
            data = json.loads(source.read_text())
            data.pop("cutoff_results", None)
            output.write_text(json.dumps(data))

            shared = {"active": 0}
            answerer = _TrackingLLM(shared)
            judge = _TrackingLLM(shared)
            writes: list[dict] = []
            active_at_write: list[int] = []

            def record_write(path: str, value: dict) -> None:
                active_at_write.append(shared["active"])
                writes.append(json.loads(json.dumps(value)))

            with patch("benchmarks.locomo.run.save_result_json", record_write):
                saved = await _evaluate_saved_locomo_question(
                    str(output),
                    "conv0_q8",
                    0,
                    {"category": 2, "answer": "June 9, 2023", "evidence": []},
                    answerer,
                    judge,
                    [10, 20, 50, 100],
                    None,
                    asyncio.Semaphore(2),
                    rejudge=False,
                )

        self.assertTrue(saved)
        self.assertEqual(len(writes), 1)
        self.assertEqual(active_at_write, [0])
        self.assertEqual(
            list(writes[0]["cutoff_results"]),
            ["top_10", "top_20", "top_50", "top_100"],
        )
