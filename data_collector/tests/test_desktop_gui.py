import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from data_collector import App as desktop
from data_collector import audio_utils, dataset
from data_collector.tests.support import IsolatedDatasetTest, synthetic_entry


class Widget:
    def __init__(self, value=""):
        self.value = value
        self.label = ""
        self.options = {}
        self.modified = False

    def get(self, *_args):
        return self.value

    def set(self, value):
        self.value = value

    def delete(self, *_args):
        self.value = ""

    def insert(self, _position, value):
        self.value = value

    def configure(self, **options):
        self.options.update(options)
        if "text" in options:
            self.label = options["text"]

    def edit_modified(self, value=None):
        if value is not None:
            self.modified = value
        return self.modified

    def focus_set(self):
        pass


class FormHarness:
    """Use the real handlers without creating Tk or opening a microphone."""

    def __init__(self):
        defaults = {
            "text_entry": "", "fr_entry": "", "en_entry": "", "source_location_entry": "",
            "notes_entry": "", "contributor_entry": "Synthetic contributor",
            "type_menu": "Word", "category_menu": "Other", "language_menu": "unspecified",
            "review_menu": "unreviewed", "lexical_menu": desktop.NO_LEXICAL_CATEGORY,
            "edit_text": "", "edit_fr": "", "edit_en": "", "edit_source_location": "",
            "edit_notes": "", "edit_type": "Word", "edit_category": "Other",
            "edit_language": "unspecified", "edit_review": "unreviewed",
            "edit_lexical": desktop.NO_LEXICAL_CATEGORY, "search_entry": "",
        }
        for name, value in defaults.items():
            setattr(self, name, Widget(value))
        for name in (
            "status_label", "audio_status_label", "dup_warning_label", "browse_status_label",
            "stats_total_label", "record_btn", "save_btn", "attach_audio_btn", "clear_btn",
            "play_pending_btn", "edit_play_btn",
        ):
            setattr(self, name, Widget())
        self.pending_audio_path = None
        self.selected_browse_id = None
        self.selected_browse_audio = None
        self.recorder = None
        self._loading_forms = False
        self._closed = False
        self._dup_check_job = None
        self._staged_audio_files = set()
        self._captured_audio = None
        self._recording_pending_stop = False
        self._recording_check_job = None
        self._collect_approval = None
        self._browse_approval = None
        self._selected_browse_entry = None
        self._browse_entries_by_id = {}
        self.after = Mock(return_value="duplicate-job")
        self.after_cancel = Mock()
        self._refresh_views = Mock(return_value=False)
        self.destroy = Mock()

    def __getattr__(self, name):
        method = desktop.App.__dict__.get(name)
        if callable(method):
            return MethodType(method, self)
        raise AttributeError(name)


class DesktopHandlerTests(IsolatedDatasetTest):
    def setUp(self):
        super().setUp()
        self.app = FormHarness()
        self.errors = self.stack.enter_context(patch.object(desktop.messagebox, "showerror"))
        self.warnings = self.stack.enter_context(patch.object(desktop.messagebox, "showwarning"))
        self.information = self.stack.enter_context(patch.object(desktop.messagebox, "showinfo"))
        self.confirm = self.stack.enter_context(patch.object(desktop.messagebox, "askyesno", return_value=True))
        self.playback_stop = self.stack.enter_context(patch.object(audio_utils, "stop_playback"))

    def stage(self, filename="draft.wav"):
        path = Path(dataset.AUDIO_DIR, filename)
        path.write_bytes(b"synthetic attachment")
        self.app.pending_audio_path = filename
        self.app._staged_audio_files.add(filename)
        return path

    def select_entry(self, **changes):
        entry = synthetic_entry(**changes)
        dataset.append_entry(entry)
        self.app._populate_browse_entry(entry)
        return entry

    def test_active_recording_blocks_save_and_keeps_draft(self):
        self.app.text_entry.set("Synthetic speech")
        self.app.recorder = SimpleNamespace(recording=True, stream=object())
        attachment = self.stage()
        with patch.object(dataset, "append_entry") as append:
            self.app.save_entry()
        append.assert_not_called()
        self.warnings.assert_called_once()
        self.assertEqual(self.app.text_entry.get(), "Synthetic speech")
        self.assertTrue(attachment.exists())
        self.assertEqual(dataset.total_count(), 0)

    def test_buffered_audio_blocks_save_until_it_is_saved_or_discarded(self):
        self.app.text_entry.set("Synthetic speech")
        self.app._captured_audio = [1]
        with patch.object(dataset, "append_entry") as append:
            self.app.save_entry()
        append.assert_not_called()
        self.assertIn("Retry", self.warnings.call_args.args[1])

    def test_blank_text_is_rejected_without_a_write(self):
        self.app.text_entry.set("   ")
        self.app.save_entry()
        self.warnings.assert_called_once()
        self.assertEqual(dataset.total_count(), 0)

    def test_failed_save_keeps_text_and_staged_audio_with_visible_error(self):
        self.app.text_entry.set("Synthetic speech")
        attachment = self.stage()
        with patch.object(dataset, "append_entry", side_effect=PermissionError("disk unavailable")):
            self.app.save_entry()
        self.errors.assert_called_once()
        self.assertEqual(self.app.text_entry.get(), "Synthetic speech")
        self.assertEqual(self.app.pending_audio_path, attachment.name)
        self.assertIn(attachment.name, self.app._staged_audio_files)
        self.assertTrue(attachment.exists())
        self.assertEqual(dataset.total_count(), 0)
        self.app._refresh_views.assert_not_called()

    def test_successful_save_keeps_committed_audio_and_resets_safe_defaults(self):
        self.app.text_entry.set("Synthetic speech")
        self.app.language_menu.set("pidgin")
        self.app.lexical_menu.set("NOUN")
        attachment = self.stage()
        self.app.save_entry()
        entry = dataset.load_all()[0]
        self.assertEqual(entry["audio_filename"], attachment.name)
        self.assertEqual(entry["language"], "pidgin")
        self.assertEqual(entry["lexical_category"], "NOUN")
        self.assertEqual(entry["review_status"], "unreviewed")
        self.assertEqual(len(entry["id"]), 10)
        self.assertTrue(entry["timestamp"])
        self.assertTrue(attachment.exists())
        self.assertNotIn(attachment.name, self.app._staged_audio_files)
        self.assertEqual(self.app.text_entry.get(), "")
        self.assertEqual(self.app.contributor_entry.get(), "Synthetic contributor")
        self.assertEqual(self.app.language_menu.get(), "unspecified")
        self.assertEqual(self.app.review_menu.get(), "unreviewed")
        self.assertEqual(self.app.lexical_menu.get(), desktop.NO_LEXICAL_CATEGORY)
        self.assertIn("Saved", self.app.status_label.label)

    def test_approval_requires_review_of_the_exact_current_draft(self):
        self.app.text_entry.set("First synthetic version")
        self.app.review_menu.set("approved")
        self.app._on_collect_review_change("approved")
        self.app.text_entry.set("Changed before the queued edit event")
        self.app.save_entry()
        self.assertEqual(dataset.load_all()[0]["review_status"], "unreviewed")

    def test_explicit_review_of_current_draft_is_preserved(self):
        self.app.text_entry.set("Reviewed synthetic version")
        self.app.language_menu.set("francanglais")
        self.app.review_menu.set("approved")
        self.app._on_collect_review_change("approved")
        self.app.save_entry()
        self.assertEqual(dataset.load_all()[0]["review_status"], "approved")

    def test_missing_selected_id_cannot_report_success(self):
        entry = self.select_entry()
        dataset.delete_entry(entry["id"])
        self.app.edit_text.set("Unsaved correction")
        self.app._save_browse_edit()
        self.errors.assert_called_once()
        self.assertIn("not saved", self.app.browse_status_label.label)
        self.assertEqual(self.app.edit_text.get(), "Unsaved correction")
        self.assertEqual(dataset.total_count(), 0)

    def test_failed_edit_keeps_saved_data_and_editor_draft(self):
        self.select_entry()
        before = Path(dataset.DATASET_PATH).read_bytes()
        self.app.edit_text.set("Unsaved correction")
        with patch.object(dataset, "_write_entries", side_effect=PermissionError("locked")):
            self.app._save_browse_edit()
        self.errors.assert_called_once()
        self.assertIn("not saved", self.app.browse_status_label.label)
        self.assertEqual(self.app.edit_text.get(), "Unsaved correction")
        self.assertEqual(Path(dataset.DATASET_PATH).read_bytes(), before)

    def test_edit_invalidates_approval_without_changing_untouched_provenance(self):
        original = self.select_entry(
            text="  Unchanged exact speech  ", review_status="approved",
            audio_filename="saved.wav", language="pidgin",
        )
        self.app.edit_notes.set(" New synthetic note ")
        self.app._save_browse_edit()
        saved = dataset.load_all()[0]
        self.assertEqual(saved["notes"], "New synthetic note")
        self.assertEqual(saved["review_status"], "unreviewed")
        for field in ("text", "id", "timestamp", "audio_filename", "contributor", "language"):
            self.assertEqual(saved[field], original[field])

    def test_explicit_reapproval_applies_to_the_new_editor_values(self):
        self.select_entry(review_status="approved")
        self.app.edit_text.set("Reviewed correction")
        self.app.edit_review.set("approved")
        self.app._on_browse_review_change("approved")
        self.app._save_browse_edit()
        saved = dataset.load_all()[0]
        self.assertEqual(saved["text"], "Reviewed correction")
        self.assertEqual(saved["review_status"], "approved")
        self.assertIn("Changes saved", self.app.browse_status_label.label)
        self.assertIn("Refresh unavailable", self.app.browse_status_label.label)

    def test_no_selection_and_cancelled_delete_never_mutate_data(self):
        self.app._save_browse_edit()
        self.information.assert_called_once()
        original = self.select_entry()
        self.confirm.return_value = False
        self.app._delete_browse_entry()
        self.assertEqual(dataset.load_all(), [original])

    def test_confirmed_delete_retains_audio_and_clears_selection(self):
        saved_audio = Path(dataset.AUDIO_DIR, "saved.wav")
        saved_audio.write_bytes(b"previously saved fixture")
        self.select_entry(audio_filename=saved_audio.name)
        self.app._delete_browse_entry()
        self.assertEqual(dataset.total_count(), 0)
        self.assertTrue(saved_audio.exists())
        self.assertIsNone(self.app.selected_browse_id)
        self.assertIsNone(self.app.selected_browse_audio)

    def test_microphone_start_error_preserves_attachment_and_allows_retry(self):
        attachment = self.stage()
        self.app.recorder = SimpleNamespace(
            recording=False, stream=None, start=Mock(side_effect=audio_utils.AudioError("device missing")),
        )
        self.app.toggle_recording()
        self.errors.assert_called_once()
        self.assertFalse(self.app._audio_unfinished())
        self.assertEqual(self.app.pending_audio_path, attachment.name)
        self.assertTrue(attachment.exists())
        self.assertEqual(self.app.save_btn.options["state"], "normal")

    def test_failed_wav_save_retains_samples_until_explicit_retry(self):
        samples = [1, 2]
        self.app.recorder = SimpleNamespace(recording=False, stream=None, sample_rate=48000, warning="")
        self.app._captured_audio = samples
        with patch.object(audio_utils, "save_recording", side_effect=audio_utils.AudioError("disk full")):
            self.app.toggle_recording()
        self.assertIs(self.app._captured_audio, samples)
        self.assertEqual(self.app.save_btn.options["state"], "disabled")
        self.assertIn("Retry audio save", self.app.record_btn.label)

        def save(_samples, audio_dir, sample_rate):
            self.assertEqual(sample_rate, 48000)
            Path(audio_dir, "new.wav").write_bytes(b"synthetic recording")
            return "new.wav"

        with patch.object(audio_utils, "save_recording", side_effect=save):
            self.app.toggle_recording()
        self.assertIsNone(self.app._captured_audio)
        self.assertEqual(self.app.pending_audio_path, "new.wav")
        self.assertEqual(self.app.save_btn.options["state"], "normal")
        self.assertEqual(dataset.total_count(), 0)

    def test_device_failure_is_detected_and_warning_precedes_audio_review(self):
        self.app.recorder = SimpleNamespace(
            recording=False, stream=object(), sample_rate=48000,
            warning="The microphone stopped unexpectedly.", stop=Mock(return_value=[1, 2]),
        )
        self.app._recording_pending_stop = True
        self.app._save_captured_audio = Mock()
        self.app._check_recording()
        self.warnings.assert_called_once_with("Review captured audio", "The microphone stopped unexpectedly.")
        self.app._save_captured_audio.assert_called_once()
        self.assertEqual(self.app._captured_audio, [1, 2])
        self.assertFalse(self.app._recording_pending_stop)

    def test_live_recording_monitor_is_rescheduled_and_cancelled_on_cleanup(self):
        self.app.recorder = SimpleNamespace(recording=True, stream=object(), close=Mock())
        self.app._recording_pending_stop = True
        self.app._check_recording()
        self.app.after.assert_called_once()
        self.assertEqual(self.app.after.call_args.args[0], 250)
        self.app._release_audio()
        self.app.after_cancel.assert_called_once_with("duplicate-job")
        self.assertIsNone(self.app._recording_check_job)

    def test_missing_recorder_cannot_silently_save_unknown_rate(self):
        self.app._captured_audio = [1]
        with patch.object(audio_utils, "save_recording") as save:
            self.app._save_captured_audio()
        self.errors.assert_called_once()
        save.assert_not_called()
        self.assertEqual(self.app._captured_audio, [1])

    def test_cancelled_or_failed_attachment_keeps_previous_audio(self):
        attachment = self.stage()
        with patch.object(desktop.filedialog, "askopenfilename", return_value=""):
            self.app.attach_audio_file()
        self.assertEqual(self.app.pending_audio_path, attachment.name)
        with (
            patch.object(desktop.filedialog, "askopenfilename", return_value="selected.wav"),
            patch.object(audio_utils, "attach_file", side_effect=audio_utils.AudioError("cannot copy")),
        ):
            self.app.attach_audio_file()
        self.errors.assert_called_once()
        self.assertTrue(attachment.exists())
        self.assertEqual(self.app.pending_audio_path, attachment.name)

    def test_clear_discards_only_draft_owned_audio(self):
        draft = self.stage()
        saved = Path(dataset.AUDIO_DIR, "saved.wav")
        saved.write_bytes(b"saved audio")
        self.app.text_entry.set("Unsaved text")
        self.app.clear_form(keep_contributor=True)
        self.assertFalse(draft.exists())
        self.assertTrue(saved.exists())
        self.assertEqual(self.app.text_entry.get(), "")
        self.assertEqual(self.app.contributor_entry.get(), "Synthetic contributor")

    def test_clear_is_blocked_during_recording(self):
        draft = self.stage()
        self.app.text_entry.set("Still recording")
        self.app.recorder = SimpleNamespace(recording=True, stream=object())
        self.app.clear_form()
        self.warnings.assert_called_once()
        self.assertTrue(draft.exists())
        self.assertEqual(self.app.text_entry.get(), "Still recording")

    def test_refresh_uses_one_snapshot_for_all_views(self):
        del self.app._refresh_views
        entries = [synthetic_entry()]
        for name in ("_refresh_count", "_refresh_recent", "_refresh_browse_list", "_refresh_stats"):
            setattr(self.app, name, Mock())
        with patch.object(dataset, "load_all", return_value=entries) as load:
            self.assertTrue(self.app._refresh_views())
        load.assert_called_once()
        for name in ("_refresh_count", "_refresh_recent", "_refresh_browse_list", "_refresh_stats"):
            getattr(self.app, name).assert_called_once_with(entries)

    def test_failed_refresh_does_not_erase_current_views(self):
        del self.app._refresh_views
        self.app._refresh_count = Mock()
        with patch.object(dataset, "load_all", side_effect=PermissionError("temporarily unavailable")):
            self.assertFalse(self.app._refresh_views())
        self.errors.assert_called_once()
        self.app._refresh_count.assert_not_called()

    def test_duplicate_lookup_uses_selected_language_and_reports_failures_inline(self):
        self.app.text_entry.set(" Synthetic text ")
        self.app.language_menu.set("pidgin")
        with patch.object(dataset, "text_exists", return_value=True) as exists:
            self.app._check_duplicate()
        exists.assert_called_once_with("Synthetic text", language="pidgin")
        self.assertIn("saving is still allowed", self.app.dup_warning_label.label)
        with patch.object(dataset, "text_exists", side_effect=PermissionError("unreadable")):
            self.app._check_duplicate()
        self.assertIn("unavailable", self.app.dup_warning_label.label)

    def test_close_confirmation_protects_unsaved_text(self):
        self.app.text_entry.set("Unsaved text")
        self.confirm.return_value = False
        self.app._on_close()
        self.app.destroy.assert_not_called()
        self.confirm.return_value = True
        self.app._on_close()
        self.app.destroy.assert_called_once()

    def test_destroy_releases_resources_and_draft_files_once(self):
        draft = self.stage()
        close = Mock()
        self.app.recorder = SimpleNamespace(recording=False, stream=None, close=close)
        self.app._dup_check_job = "queued-job"
        instance = object.__new__(desktop.App)
        instance.__dict__.update(vars(self.app))
        with patch.object(desktop.ctk.CTk, "destroy") as tk_destroy:
            desktop.App.destroy(instance)
            desktop.App.destroy(instance)
        close.assert_called_once()
        tk_destroy.assert_called_once()
        self.app.after_cancel.assert_called_once_with("queued-job")
        self.assertFalse(draft.exists())
        self.assertTrue(instance._closed)


if __name__ == "__main__":
    unittest.main()
