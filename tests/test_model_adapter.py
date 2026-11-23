"""Synthetic injected-runtime contract tests; no weights or real inference."""

import importlib
import sys
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.model_adapters.smolvlm import MODEL_ID, MODEL_REVISION, SmolVLMAdapter

PNG = b"\x89PNG\r\n\x1a\nsynthetic-contract-fixture-not-a-real-png"


class TestModelAdapter(unittest.TestCase):
    def setUp(self):
        self.decoded = MagicMock()
        self.opened = MagicMock()
        self.opened.size = (64, 32)
        self.opened.n_frames = 1
        self.opened.convert.return_value = self.decoded
        self.opened.__enter__.return_value = self.opened
        self.image = SimpleNamespace(
            open=MagicMock(return_value=self.opened),
            DecompressionBombWarning=type("TestBombWarning", (Warning,), {}),
            DecompressionBombError=type("TestBombError", (Exception,), {}),
        )
        self.torch = SimpleNamespace(
            float32="test-float32",
            float16="test-float16",
            cuda=SimpleNamespace(is_available=MagicMock(return_value=False)),
            inference_mode=MagicMock(side_effect=nullcontext),
        )
        self.model = MagicMock()
        self.generated = MagicMock()
        self.model.generate.return_value = self.generated
        self.processor = MagicMock()
        self.processor.apply_chat_template.return_value = "synthetic rendered template"
        self.processor.batch_decode.return_value = [" blue "]

        class TestInputs(dict):
            def to(inner, *args, **kwargs):
                inner.transfer = (args, kwargs)
                return inner

        self.inputs = TestInputs(
            input_ids=SimpleNamespace(shape=(1, 8)), pixel_values="test-pixels"
        )
        self.processor.return_value = self.inputs
        self.transformers = SimpleNamespace(
            AutoProcessor=SimpleNamespace(
                from_pretrained=MagicMock(return_value=self.processor)
            ),
            AutoModelForImageTextToText=SimpleNamespace(
                from_pretrained=MagicMock(return_value=self.model)
            ),
        )
        self.adapter = SmolVLMAdapter(
            processor=self.processor,
            model=self.model,
            torch=self.torch,
            image_module=self.image,
        )

    def test_module_import_does_not_import_optional_dependencies(self):
        with patch(
            "importlib.import_module",
            side_effect=AssertionError("optional import must remain lazy"),
        ):
            importlib.reload(sys.modules["core.model_adapters.smolvlm"])

    def test_offline_snapshot_security_parameters(self):
        with patch(
            "core.model_adapters.smolvlm._runtime",
            return_value=(self.torch, self.transformers, self.image),
        ):
            SmolVLMAdapter.from_pretrained()
        for factory in [
            self.transformers.AutoProcessor.from_pretrained,
            self.transformers.AutoModelForImageTextToText.from_pretrained,
        ]:
            args, kwargs = factory.call_args
            self.assertEqual(args, (MODEL_ID,))
            self.assertEqual(kwargs["revision"], MODEL_REVISION)
            self.assertTrue(kwargs["local_files_only"])
            self.assertFalse(kwargs["trust_remote_code"])
            self.assertFalse(kwargs["token"])
        factory = self.transformers.AutoModelForImageTextToText.from_pretrained
        model_kwargs = factory.call_args.kwargs
        self.assertTrue(model_kwargs["use_safetensors"])
        self.assertFalse(model_kwargs["use_kernels"])
        self.assertFalse(model_kwargs["allow_all_kernels"])
        self.assertEqual(model_kwargs["attn_implementation"], "eager")
        self.model.to.assert_called_once_with("cpu")
        self.model.eval.assert_called_once_with()

    def test_explicit_download_and_cuda_policy(self):
        with patch(
            "core.model_adapters.smolvlm._runtime",
            return_value=(self.torch, self.transformers, self.image),
        ):
            with self.assertRaisesRegex(RuntimeError, "CUDA"):
                SmolVLMAdapter.from_pretrained(device="cuda")
            self.transformers.AutoProcessor.from_pretrained.assert_not_called()
            self.torch.cuda.is_available.return_value = True
            SmolVLMAdapter.from_pretrained(allow_download=True, device="cuda")
        self.assertFalse(
            self.transformers.AutoProcessor.from_pretrained.call_args.kwargs[
                "local_files_only"
            ]
        )
        self.model.to.assert_called_with("cuda")
        self.assertEqual(
            self.transformers.AutoModelForImageTextToText.from_pretrained.call_args.kwargs[
                "dtype"
            ],
            "test-float16",
        )

    def test_missing_runtime_and_missing_offline_snapshot(self):
        with patch(
            "importlib.import_module",
            side_effect=ImportError("synthetic missing package"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Optional VLM runtime"):
                SmolVLMAdapter.from_pretrained()
        self.transformers.AutoProcessor.from_pretrained.side_effect = OSError(
            "synthetic missing cache"
        )
        with patch(
            "core.model_adapters.smolvlm._runtime",
            return_value=(self.torch, self.transformers, self.image),
        ):
            with self.assertRaisesRegex(RuntimeError, "offline"):
                SmolVLMAdapter.from_pretrained()

    def test_invalid_loader_options_before_any_optional_import(self):
        with patch(
            "core.model_adapters.smolvlm._runtime",
            side_effect=AssertionError("must not import"),
        ):
            for options in [{"allow_download": 1}, {"device": "auto"}, {"device": []}]:
                with self.assertRaises(ValueError):
                    SmolVLMAdapter.from_pretrained(**options)

    def test_answer_is_greedy_bounded_and_does_not_echo_input_tokens(self):
        self.assertEqual(self.adapter.answer(PNG, "What color?"), "blue")
        self.processor.assert_called_once_with(
            text="synthetic rendered template",
            images=[self.decoded],
            return_tensors="pt",
            do_image_splitting=False,
            size={"longest_edge": 512},
        )
        self.model.generate.assert_called_once_with(
            **self.inputs, do_sample=False, num_beams=1, max_new_tokens=64
        )
        self.generated.__getitem__.assert_called_once_with(
            (slice(None), slice(8, None))
        )
        self.torch.inference_mode.assert_called_once()
        self.decoded.close.assert_called_once()
        self.assertEqual(self.inputs.transfer, (("cpu",), {"dtype": "test-float32"}))

    def test_invalid_input_rejected_before_decoder_or_model(self):
        for image, prompt, tokens in [
            (b"", "x", 1),
            (b"GIF89a", "x", 1),
            (b"x" * (2 * 1024 * 1024 + 1), "x", 1),
            (PNG, " ", 1),
            (PNG, "x" * 2049, 1),
            (PNG, "\ud800", 1),
            (PNG, "x", True),
            (PNG, "x", 0),
            (PNG, "x", 129),
        ]:
            with (
                self.subTest(prompt_length=len(prompt), tokens=tokens),
                self.assertRaises(ValueError),
            ):
                self.adapter.answer(image, prompt, max_new_tokens=tokens)
        self.image.open.assert_not_called()
        self.model.generate.assert_not_called()

    def test_decoder_failure_and_dimension_frame_limits(self):
        for size, frames in [((2048, 1), 1), ((0, 1), 1), ((10, 10), 2)]:
            self.opened.size, self.opened.n_frames = size, frames
            with self.assertRaises(ValueError):
                self.adapter.answer(PNG, "x")
        self.opened.size, self.opened.n_frames = (10, 10), 1
        for error in [
            OSError("synthetic invalid data"),
            self.image.DecompressionBombError("synthetic bomb"),
        ]:
            self.image.open.side_effect = error
            with self.assertRaises(ValueError):
                self.adapter.answer(PNG, "x")
        self.model.generate.assert_not_called()

    def test_processed_token_limit_and_cleanup(self):
        self.inputs["input_ids"].shape = (1, 2049)
        with self.assertRaisesRegex(ValueError, "2048 tokens"):
            self.adapter.answer(PNG, "x")
        self.model.generate.assert_not_called()
        self.decoded.close.assert_called_once()

    def test_empty_or_malformed_decode_fails_and_closes_image(self):
        for value in [[], [None], [""], ["x" * 8193]]:
            self.processor.batch_decode.return_value = value
            with self.assertRaises(RuntimeError):
                self.adapter.answer(PNG, "x")
        self.assertEqual(self.decoded.close.call_count, 4)

    def test_model_failure_closes_decoded_image(self):
        self.model.generate.side_effect = RuntimeError("synthetic model failure")
        with self.assertRaisesRegex(RuntimeError, "synthetic model failure"):
            self.adapter.answer(PNG, "x")
        self.decoded.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
