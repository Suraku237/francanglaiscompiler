import builtins
import importlib.util
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from data_collector import audio_utils, dataset
from data_collector.tests.support import IsolatedDatasetTest


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.stream = Mock()
        self.device = SimpleNamespace(InputStream=Mock(return_value=self.stream))
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(audio_utils, "AUDIO_RECORDING_AVAILABLE", True))
        self.stack.enter_context(patch.object(audio_utils, "sd", self.device))
        self.stack.enter_context(patch.object(
            audio_utils, "np", SimpleNamespace(concatenate=Mock(return_value="samples")),
        ))
        self.recorder = audio_utils.Recorder()

    def test_device_creation_failure_leaves_recorder_idle(self):
        self.device.InputStream.side_effect = OSError("device unplugged")
        with self.assertRaises(audio_utils.AudioError):
            self.recorder.start()
        self.assertFalse(self.recorder.recording)
        self.assertIsNone(self.recorder.stream)

    def test_start_failure_closes_stream_and_allows_retry(self):
        self.stream.start.side_effect = OSError("device busy")
        with self.assertRaises(audio_utils.AudioError):
            self.recorder.start()
        self.assertFalse(self.recorder.recording)
        self.assertIsNone(self.recorder.stream)
        self.stream.close.assert_called_once()
        self.stream.start.side_effect = None
        self.recorder.start()
        self.assertTrue(self.recorder.recording)

    def test_stop_failure_still_closes_stream_and_preserves_frames(self):
        self.recorder.start()
        self.recorder.frames = [[1, 2]]
        self.stream.stop.side_effect = OSError("device lost")
        with self.assertRaises(audio_utils.AudioError):
            self.recorder.stop()
        self.stream.close.assert_called_once()
        self.assertFalse(self.recorder.recording)
        self.assertIsNone(self.recorder.stream)
        self.assertEqual(self.recorder.stop(), "samples")

    def test_repeated_start_does_not_replace_an_active_stream(self):
        self.recorder.start()
        with self.assertRaises(audio_utils.AudioError):
            self.recorder.start()
        self.device.InputStream.assert_called_once()
        self.assertTrue(self.recorder.recording)
        self.stream.close.assert_not_called()

    def test_stop_without_samples_and_repeated_close_are_safe(self):
        self.assertIsNone(self.recorder.stop())
        self.recorder.start()
        self.assertIsNone(self.recorder.stop())
        self.recorder.close()
        self.recorder.close()
        self.assertFalse(self.recorder.recording)
        self.assertIsNone(self.recorder.stream)
        self.stream.close.assert_called_once()

    def test_close_failure_retains_handle_for_retry(self):
        self.recorder.start()
        self.stream.close.side_effect = OSError("still busy")
        with self.assertRaises(audio_utils.AudioError):
            self.recorder.close()
        self.assertFalse(self.recorder.recording)
        self.assertIs(self.recorder.stream, self.stream)
        self.stream.close.side_effect = None
        self.recorder.close()
        self.assertIsNone(self.recorder.stream)
        self.assertEqual(self.recorder.frames, [])

    def test_unexpected_start_failure_propagates_but_releases_stream(self):
        self.stream.start.side_effect = TypeError("programming error")
        with self.assertRaises(TypeError):
            self.recorder.start()
        self.stream.close.assert_called_once()
        self.assertFalse(self.recorder.recording)
        self.assertIsNone(self.recorder.stream)

    def test_callback_copies_frames_and_ignores_late_samples(self):
        self.recorder.start()
        callback = self.device.InputStream.call_args.kwargs["callback"]
        samples = [1, 2]
        callback(samples, 2, None, None)
        samples[0] = 99
        self.assertEqual(self.recorder.frames, [[1, 2]])
        self.recorder.stop()
        callback([3], 1, None, None)
        self.assertEqual(self.recorder.frames, [[1, 2]])

    def test_device_creation_failure_keeps_previous_samples(self):
        self.recorder.frames = [[1]]
        self.device.InputStream.side_effect = OSError("device missing")
        with self.assertRaises(audio_utils.AudioError):
            self.recorder.start()
        self.assertEqual(self.recorder.frames, [[1]])

    def test_unavailable_dependencies_raise_actionable_error(self):
        with patch.object(audio_utils, "AUDIO_RECORDING_AVAILABLE", False):
            with self.assertRaisesRegex(audio_utils.AudioError, "Attach an audio file"):
                self.recorder.start()
        self.assertFalse(self.recorder.recording)


class AudioFileTests(IsolatedDatasetTest):
    def setUp(self):
        super().setUp()
        self.source = self.directory / "source.wav"
        self.source.write_bytes(b"synthetic audio fixture")
        self.device = SimpleNamespace(play=Mock(), stop=Mock())
        self.codec = SimpleNamespace(read=Mock(return_value=([1], 44100)), write=Mock())
        self.stack.enter_context(patch.object(audio_utils, "AUDIO_RECORDING_AVAILABLE", True))
        self.stack.enter_context(patch.object(audio_utils, "sd", self.device))
        self.stack.enter_context(patch.object(audio_utils, "sf", self.codec))

    def test_attachment_copies_without_altering_source(self):
        filename = audio_utils.attach_file(str(self.source), dataset.AUDIO_DIR)
        self.assertNotEqual(filename, self.source.name)
        self.assertEqual(Path(dataset.AUDIO_DIR, filename).read_bytes(), self.source.read_bytes())
        self.assertEqual(len(list(Path(dataset.AUDIO_DIR).iterdir())), 1)

    def test_attachment_failure_removes_partial_copy(self):
        def partial_copy(_source, target):
            Path(target).write_bytes(b"partial")
            raise PermissionError("destination locked")

        with patch.object(audio_utils.shutil, "copy2", side_effect=partial_copy):
            with self.assertRaises(audio_utils.AudioError):
                audio_utils.attach_file(str(self.source), dataset.AUDIO_DIR)
        self.assertEqual(list(Path(dataset.AUDIO_DIR).iterdir()), [])
        self.assertEqual(self.source.read_bytes(), b"synthetic audio fixture")

    def test_missing_attachment_has_no_partial_destination(self):
        with self.assertRaises(audio_utils.AudioError):
            audio_utils.attach_file(str(self.directory / "missing.wav"), dataset.AUDIO_DIR)
        self.assertEqual(list(Path(dataset.AUDIO_DIR).iterdir()), [])

    def test_recording_failure_removes_partial_wav(self):
        def partial_write(target, _samples, _rate):
            Path(target).write_bytes(b"partial")
            raise OSError("disk full")

        self.codec.write.side_effect = partial_write
        with self.assertRaises(audio_utils.AudioError):
            audio_utils.save_recording([1], dataset.AUDIO_DIR)
        self.assertEqual(list(Path(dataset.AUDIO_DIR).iterdir()), [])

    def test_successful_recording_is_published_as_wav(self):
        self.codec.write.side_effect = lambda target, *_args: Path(target).write_bytes(b"wav fixture")
        filename = audio_utils.save_recording([1], dataset.AUDIO_DIR)
        self.assertTrue(filename.endswith(".wav"))
        self.assertEqual(Path(dataset.AUDIO_DIR, filename).read_bytes(), b"wav fixture")
        self.assertEqual(len(list(Path(dataset.AUDIO_DIR).iterdir())), 1)

    def test_atomic_publish_failure_cleans_staging_file(self):
        with patch.object(audio_utils.os, "replace", side_effect=PermissionError("locked")):
            with self.assertRaises(audio_utils.AudioError):
                audio_utils.attach_file(str(self.source), dataset.AUDIO_DIR)
        self.assertEqual(list(Path(dataset.AUDIO_DIR).iterdir()), [])

    def test_missing_playback_file_is_reported_without_opening_device(self):
        self.assertFalse(audio_utils.play_audio(str(self.directory / "missing.wav")))
        self.device.play.assert_not_called()
        self.codec.read.assert_not_called()

    def test_native_playback_uses_file_sample_rate(self):
        self.assertTrue(audio_utils.play_audio(str(self.source)))
        self.device.play.assert_called_once_with([1], 44100)

    def test_expected_codec_error_uses_os_player(self):
        self.codec.read.side_effect = ValueError("unsupported codec")
        with patch.object(audio_utils.os, "name", "nt"), patch.object(audio_utils.os, "startfile", create=True) as launch:
            self.assertTrue(audio_utils.play_audio(str(self.source)))
            launch.assert_called_once_with(str(self.source))

    def test_os_player_failure_returns_false(self):
        with (
            patch.object(audio_utils, "AUDIO_RECORDING_AVAILABLE", False),
            patch.object(audio_utils.os, "name", "nt"),
            patch.object(audio_utils.os, "startfile", side_effect=OSError("no player"), create=True),
        ):
            self.assertFalse(audio_utils.play_audio(str(self.source)))

    def test_optional_dependencies_are_not_needed_for_attachment_or_os_playback(self):
        with (
            patch.object(audio_utils, "AUDIO_RECORDING_AVAILABLE", False),
            patch.object(audio_utils.os, "name", "nt"),
            patch.object(audio_utils.os, "startfile", create=True) as launch,
        ):
            filename = audio_utils.attach_file(str(self.source), dataset.AUDIO_DIR)
            self.assertTrue(audio_utils.play_audio(str(Path(dataset.AUDIO_DIR, filename))))
            launch.assert_called_once()
        self.device.play.assert_not_called()

    def test_unexpected_codec_failure_is_not_swallowed(self):
        self.codec.read.side_effect = TypeError("programming error")
        with self.assertRaises(TypeError):
            audio_utils.play_audio(str(self.source))

    def test_stop_playback_failure_is_retryable(self):
        self.device.stop.side_effect = OSError("output device disconnected")
        with self.assertRaises(audio_utils.AudioError):
            audio_utils.stop_playback()
        self.device.stop.side_effect = None
        audio_utils.stop_playback()
        self.assertEqual(self.device.stop.call_count, 2)


class OptionalDependencyTests(unittest.TestCase):
    def test_missing_or_unavailable_audio_backend_does_not_break_import(self):
        original_import = builtins.__import__
        for failure in (ImportError("not installed"), OSError("PortAudio library unavailable")):
            with self.subTest(failure=type(failure).__name__):
                def import_without_device(name, *args, **kwargs):
                    if name == "sounddevice":
                        raise failure
                    return original_import(name, *args, **kwargs)

                spec = importlib.util.spec_from_file_location("isolated_audio_utils", audio_utils.__file__)
                assert spec is not None and spec.loader is not None
                module = importlib.util.module_from_spec(spec)
                with patch("builtins.__import__", side_effect=import_without_device):
                    spec.loader.exec_module(module)
                self.assertFalse(module.AUDIO_RECORDING_AVAILABLE)
                self.assertIsNone(module.sd)
                module.stop_playback()


if __name__ == "__main__":
    unittest.main()
