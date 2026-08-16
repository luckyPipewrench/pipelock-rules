#!/usr/bin/env python3
"""Focused unit tests for scripts/pr-review.py and its trusted workflow."""

import importlib.util
import pathlib
import unittest
from unittest import mock


SCRIPT_PATH = pathlib.Path(__file__).with_name("pr-review.py")
WORKFLOW_PATH = SCRIPT_PATH.parents[1] / ".github" / "workflows" / "pr-review.yaml"
SPEC = importlib.util.spec_from_file_location("pr_review", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"failed to load {SCRIPT_PATH}")
pr_review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pr_review)


class FakeResponse:
    def __init__(self, data: dict, status_code: int = 200, text: str = "") -> None:
        self._data = data
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        return self._data


class ModelRoutingTest(unittest.TestCase):
    def test_default_models_are_the_reviewed_cost_routes(self) -> None:
        self.assertEqual(pr_review.DEFAULT_MODEL_FAST, "gpt-5.6-luna")
        self.assertEqual(pr_review.DEFAULT_MODEL_DEEP, "gpt-5.6-terra")

    def test_workflow_delegates_model_defaults_to_runner_constants(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "PR_REVIEW_MODEL_FAST: ${{ vars.PR_REVIEW_MODEL_FAST }}", workflow
        )
        self.assertIn(
            "PR_REVIEW_MODEL_DEEP: ${{ vars.PR_REVIEW_MODEL_DEEP }}", workflow
        )
        self.assertNotRegex(workflow, r"PR_REVIEW_MODEL_(?:FAST|DEEP): gpt-")

    def test_workflow_keeps_the_secret_runner_trusted_and_owner_gated(self) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("github.event.comment.user.login == 'luckyPipewrench'", workflow)
        self.assertIn("github.event.comment.author_association == 'OWNER'", workflow)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("timeout-minutes: 10", workflow)
        self.assertIn("group: pr-review-${{ github.repository }}-${{ github.event.issue.number }}", workflow)
        self.assertIn("cancel-in-progress: true", workflow)
        self.assertIn("python -m unittest scripts/pr_review_test.py", workflow)
        self.assertNotIn("/review fast", workflow)

    def test_gpt5_payload_uses_reasoning_effort_without_temperature(self) -> None:
        payload = pr_review.build_llm_payload("gpt-5.6-luna", "diff")
        self.assertNotIn("temperature", payload)
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertEqual(payload["max_completion_tokens"], 8192)

    def test_deep_gpt5_payload_uses_xhigh_reasoning(self) -> None:
        payload = pr_review.build_llm_payload(
            "gpt-5.6-terra",
            "diff",
            max_completion_tokens=pr_review.DEEP_MAX_COMPLETION_TOKENS,
            reasoning_effort=pr_review.DEEP_REASONING_EFFORT,
        )
        self.assertEqual(payload["reasoning_effort"], "xhigh")
        self.assertEqual(payload["max_completion_tokens"], 64000)

    def test_empty_overrides_fall_back_to_python_defaults(self) -> None:
        with mock.patch.dict(
            pr_review.os.environ,
            {"PR_REVIEW_MODEL_FAST": "", "PR_REVIEW_MODEL_DEEP": ""},
            clear=True,
        ):
            self.assertEqual(pr_review.model_for_mode("default"), "gpt-5.6-luna")
            self.assertEqual(pr_review.model_for_mode("deep"), "gpt-5.6-terra")


class ResponseParsingTest(unittest.TestCase):
    def test_shape_errors_are_generic_and_fail_closed(self) -> None:
        with self.assertRaises(pr_review.LLMReviewError) as ctx:
            pr_review.extract_chat_content(
                {"choices": [], "private": "provider detail"}
            )
        self.assertIn("no choices", str(ctx.exception))
        self.assertNotIn("provider detail", str(ctx.exception))

        with self.assertRaisesRegex(pr_review.LLMReviewError, "empty content"):
            pr_review.extract_chat_content({"choices": [None]})

    def test_extracts_text_content_parts(self) -> None:
        data = {
            "choices": [
                {"message": {"content": [{"text": "review "}, {"text": "body"}]}}
            ]
        }
        self.assertEqual(pr_review.extract_chat_content(data), "review body")

    def test_rejects_empty_reasoning_only_response(self) -> None:
        data = {
            "choices": [{"finish_reason": "length", "message": {"content": ""}}],
            "usage": {"completion_tokens_details": {"reasoning_tokens": 4096}},
        }
        with self.assertRaisesRegex(pr_review.LLMReviewError, "empty content.*reasoning=4096"):
            pr_review.extract_chat_content(data)

    def test_marks_nonempty_truncated_response_incomplete(self) -> None:
        data = {
            "choices": [{"finish_reason": "length", "message": {"content": "partial"}}],
            "usage": {"completion_tokens_details": {"reasoning_tokens": 22000}},
        }
        result = pr_review.extract_chat_content(data)
        self.assertIn("partial", result)
        self.assertIn("Warning", result)
        self.assertIn("reasoning=22000", result)


class CallLLMTest(unittest.TestCase):
    def test_default_mode_cannot_drift_to_deep_budget_or_effort(self) -> None:
        response = FakeResponse({"choices": [{"message": {"content": "review"}}]})
        with mock.patch.dict(
            pr_review.os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True
        ), mock.patch.object(pr_review.requests, "post", return_value=response) as post:
            self.assertEqual(pr_review.call_llm("diff", "default"), "review")

        _, kwargs = post.call_args
        self.assertEqual(kwargs["json"]["model"], "gpt-5.6-luna")
        self.assertEqual(kwargs["json"]["reasoning_effort"], "low")
        self.assertEqual(kwargs["timeout"], pr_review.DEFAULT_LLM_TIMEOUT_SECONDS)

    def test_deep_mode_uses_terra_xhigh_reasoning_and_longer_timeout(self) -> None:
        response = FakeResponse({"choices": [{"message": {"content": "review"}}]})
        with mock.patch.dict(
            pr_review.os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True
        ), mock.patch.object(pr_review.requests, "post", return_value=response) as post:
            self.assertEqual(pr_review.call_llm("diff", "deep"), "review")

        _, kwargs = post.call_args
        self.assertEqual(kwargs["json"]["model"], "gpt-5.6-terra")
        self.assertEqual(kwargs["json"]["reasoning_effort"], "xhigh")
        self.assertEqual(kwargs["json"]["max_completion_tokens"], 64000)
        self.assertEqual(kwargs["timeout"], pr_review.DEEP_LLM_TIMEOUT_SECONDS)

    def test_non_200_is_an_error_not_a_published_review(self) -> None:
        response = FakeResponse({}, status_code=500, text="upstream failure")
        with mock.patch.dict(
            pr_review.os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True
        ), mock.patch.object(pr_review.requests, "post", return_value=response):
            with self.assertRaises(pr_review.LLMReviewError) as ctx:
                pr_review.call_llm("diff", "default")
        self.assertIn("returned 500", str(ctx.exception))
        self.assertNotIn("upstream failure", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
