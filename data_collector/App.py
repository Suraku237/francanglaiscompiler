"""
Francanglais Dataset Collector
--------------------------------
A desktop GUI (CustomTkinter) for collecting the CS4110 course dataset:
words, phrases and sentences manually transcribed from real speech
around Yaoundé, each tagged with a topic category (matching the
assignment's required topics), French/English glosses, where it was
heard, and optional audio (recorded live or attached from a file) as
extra raw material for the word-prediction extension.

Designed to be usable by every group member, technical or not — plain
language, grouped fields, and a built-in Help dialog (❓ top-right).

Three tabs:
  - Collect         : add new entries (with duplicate warning + recent list)
  - Browse & Edit    : search, edit, delete, and play back existing entries
  - Stats            : counts by category, type, language and review

Run:
    pip install -r ../requirements-desktop.txt
    python App.py
"""

import os
import sys
import csv
import uuid
import datetime
from collections import Counter
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
import tkinter.ttk as ttk

import customtkinter as ctk
from filelock import Timeout

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_collector import audio_utils, dataset


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT_GREEN = "#2FA572"
ACCENT_GREEN_HOVER = "#248858"
ACCENT_RED = "#8B2E2E"
ACCENT_RED_HOVER = "#6E2424"
NO_LEXICAL_CATEGORY = "(none)"
REVIEW_STATUSES = ["unreviewed", "approved"]
DATASET_ERRORS = (OSError, ValueError, csv.Error, Timeout)
AUDIO_ERRORS = (audio_utils.AudioError, OSError)

HELP_TEXT = """WHAT IS THIS APP FOR?

We're collecting real, everyday speech from around Yaoundé — the mix
of French, English, Pidgin and slang people actually use — for our
CS4110 compiler project. This app is just a notebook for that speech:
it doesn't judge or auto-correct anything you type.

THE GOLDEN RULE
Type exactly what was said. Keep the slang, the accent, the mixed-up
grammar, even mistakes. "Correcting" it defeats the whole point —
we're studying real speech, not proper French or English.

THE THREE TABS

1) Collect
   Add a new entry. Only the first box (the actual words) is
   required — everything else is optional but genuinely helps later
   (the meaning, where you heard it, which topic it fits).

2) Browse & Edit
   See everything collected so far. Search, fix a typo, or delete an
   entry you added by mistake. Click any row to load it below.

3) Stats
   A quick look at how balanced the collection is — e.g. if you have
   loads of "Market Bargaining" but nothing for "Rainy Season" yet,
   this tab shows it at a glance.

TIPS
• Duplicate warning: if the same text is saved in this language, you'll see a
  small orange note — that's just a heads-up, not an error.
• Language starts as "unspecified"; do not guess. "mixed" is distinct
  from Francanglais and Pidgin.
• Entries start "unreviewed". Choose "approved" only after human review.
  Editing evidence resets approval; explicitly approve again after editing.
  A lexical category is optional and applies to Word entries.
• Audio is entirely optional. The assignment only requires you to
  write down what you heard. Stop recording before saving or attaching.
  If audio saving fails, use "Retry audio save"; your draft stays intact.
• Clear/close discards unsaved audio copies, never the original attachment
  or audio already saved with an entry.
• Ctrl+Enter saves the current entry; Esc clears the form.
"""


class Tooltip:
    """A small hover tooltip for a single widget."""

    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, event=None):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip_window = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        label = ctk.CTkLabel(
            tw, text=self.text, fg_color="#3a3a3a", text_color="white",
            corner_radius=6, font=ctk.CTkFont(size=11), justify="left",
            wraplength=280, padx=10, pady=6,
        )
        label.pack()

    def _hide(self, event=None):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


def section_frame(parent, icon_and_title: str, subtitle: str = ""):
    """A visually distinct, titled section container for grouping related fields."""
    outer = ctk.CTkFrame(parent, corner_radius=10, border_width=1, border_color="#3a3a3a")
    header = ctk.CTkLabel(
        outer, text=icon_and_title, font=ctk.CTkFont(size=14, weight="bold"),
        anchor="w",
    )
    header.grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(12, 0))
    if subtitle:
        ctk.CTkLabel(
            outer, text=subtitle, font=ctk.CTkFont(size=11), text_color="gray60", anchor="w",
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=14, pady=(0, 8))
        next_row = 2
    else:
        next_row = 1
    outer.grid_columnconfigure(1, weight=1)
    return outer, next_row


def style_treeview_dark():
    """Make the ttk.Treeview (used in Browse & Edit) match the dark theme."""
    style = ttk.Style()
    style.theme_use("default")
    style.configure(
        "Treeview",
        background="#2b2b2b", foreground="white",
        fieldbackground="#2b2b2b", rowheight=28, borderwidth=0,
        font=ctk.CTkFont(size=12),
    )
    style.map("Treeview", background=[("selected", "#1f6aa5")])
    style.configure(
        "Treeview.Heading",
        background="#1f1f1f", foreground="white", borderwidth=0,
        font=ctk.CTkFont(size=12, weight="bold"),
    )


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Francanglais Dataset Collector — CS4110")
        self.geometry("920x780")
        self.minsize(780, 640)

        style_treeview_dark()

        self.pending_audio_path = None      # filename staged for the new entry (Collect tab)
        self.selected_browse_id = None       # id of the entry currently loaded in Browse & Edit
        self.selected_browse_audio = None    # audio filename of the selected browse entry
        self.recorder = audio_utils.Recorder() if audio_utils.AUDIO_RECORDING_AVAILABLE else None
        self._dup_check_job = None
        self._staged_audio_files: set[str] = set()
        self._captured_audio = None
        self._recording_pending_stop = False
        self._recording_check_job = None
        self._collect_approval = None
        self._browse_approval = None
        self._selected_browse_entry = None
        self._browse_entries_by_id = {}
        self._field_variables = []
        self._loading_forms = True
        self._closed = False

        self._build_header()

        self.tabs = ctk.CTkTabview(self, command=self._on_tab_changed)
        self.tabs.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.tabs.add("📝  Collect")
        self.tabs.add("🔍  Browse & Edit")
        self.tabs.add("📊  Stats")

        self._build_collect_tab(self.tabs.tab("📝  Collect"))
        self._build_browse_tab(self.tabs.tab("🔍  Browse & Edit"))
        self._build_stats_tab(self.tabs.tab("📊  Stats"))
        self._watch_evidence_fields()
        self._loading_forms = False
        self._sync_audio_controls()

        # Keyboard shortcuts (active anywhere in the window)
        self.bind("<Control-Return>", lambda e: self.save_entry())
        self.bind("<Escape>", lambda e: self.clear_form(keep_contributor=True))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._refresh_views()

    # ==================================================================
    # HEADER
    # ==================================================================
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(14, 0))
        header.grid_columnconfigure(0, weight=1)

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_box, text="🗣️  Francanglais Dataset Collector",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box, text="CS4110 — Lexical & Syntactic Analysis of Yaoundé Speech",
            font=ctk.CTkFont(size=12), text_color="gray60",
        ).pack(anchor="w")

        ctk.CTkButton(
            header, text="❓ Help", command=self._show_help, width=90, height=32,
            fg_color="gray30", hover_color="gray20",
        ).grid(row=0, column=1, sticky="e")

    def _show_help(self):
        win = ctk.CTkToplevel(self)
        win.title("Help — How to use this app")
        win.geometry("560x560")
        win.attributes("-topmost", True)

        box = ctk.CTkTextbox(win, wrap="word", font=ctk.CTkFont(size=13))
        box.pack(fill="both", expand=True, padx=16, pady=16)
        box.insert("1.0", HELP_TEXT)
        box.configure(state="disabled")

    # ==================================================================
    # COLLECT TAB
    # ==================================================================
    def _build_collect_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        self.count_label = ctk.CTkLabel(parent, text="", text_color="gray70", font=ctk.CTkFont(size=12))
        self.count_label.grid(row=0, column=0, sticky="w", padx=4, pady=(6, 8))

        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        scroll.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        # --- Section 1: What did you hear? ---
        sec1, r = section_frame(
            scroll, "📝  What did you hear?",
            "Write it exactly as spoken — slang, accent, and mistakes included.",
        )
        sec1.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 10))

        ctk.CTkLabel(sec1, text="The words *").grid(row=r, column=0, sticky="w", padx=14, pady=(0, 4))
        self.text_entry = ctk.CTkTextbox(sec1, height=64)
        self.text_entry.grid(row=r, column=1, columnspan=2, sticky="ew", padx=14, pady=(0, 4))
        self.text_entry.bind("<<Modified>>", self._on_text_change)
        Tooltip(self.text_entry, 'e.g. "Le taxi don refuse for carry me go quartier"')
        r += 1

        self.dup_warning_label = ctk.CTkLabel(
            sec1, text="", text_color="#E0A93B", font=ctk.CTkFont(size=12))
        self.dup_warning_label.grid(row=r, column=1, columnspan=2, sticky="w", padx=14)
        r += 1

        ctk.CTkLabel(sec1, text="Is it a...").grid(row=r, column=0, sticky="w", padx=14, pady=(6, 12))
        self.type_menu = ctk.CTkOptionMenu(
            sec1, values=dataset.ENTRY_TYPES, command=self._on_collect_type_change,
        )
        self.type_menu.grid(row=r, column=1, sticky="w", padx=14, pady=(6, 12))
        r += 1

        ctk.CTkLabel(sec1, text="Language").grid(row=r, column=0, sticky="w", padx=14, pady=4)
        self.language_menu = ctk.CTkOptionMenu(
            sec1, values=dataset.DATASET_LANGUAGES, command=self._on_collect_evidence_change,
        )
        self.language_menu.set("unspecified")
        self.language_menu.grid(row=r, column=1, sticky="w", padx=14, pady=4)
        r += 1

        ctk.CTkLabel(sec1, text="Lexical category").grid(row=r, column=0, sticky="w", padx=14, pady=4)
        self.lexical_menu = ctk.CTkOptionMenu(
            sec1, values=[NO_LEXICAL_CATEGORY, *dataset.LEXICAL_CATEGORIES],
            command=self._on_collect_evidence_change, width=220,
        )
        self.lexical_menu.grid(row=r, column=1, sticky="w", padx=14, pady=4)
        Tooltip(self.lexical_menu, "Optional lexer category for a Word; this is not proof of meaning or language.")
        r += 1

        ctk.CTkLabel(sec1, text="Review").grid(row=r, column=0, sticky="w", padx=14, pady=(4, 12))
        self.review_menu = ctk.CTkOptionMenu(
            sec1, values=REVIEW_STATUSES, command=self._on_collect_review_change,
        )
        self.review_menu.grid(row=r, column=1, sticky="w", padx=14, pady=(4, 12))
        Tooltip(self.review_menu, "Approve only after human review. Editing evidence resets approval.")

        # --- Section 2: What does it mean? ---
        sec2, r2 = section_frame(
            scroll, "🌍  What does it mean?",
            "Optional — only fill in if you actually know the standard-language meaning.",
        )
        sec2.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 10))

        ctk.CTkLabel(sec2, text="In French").grid(row=r2, column=0, sticky="w", padx=14, pady=4)
        self.fr_entry = ctk.CTkEntry(sec2, placeholder_text="Meaning in standard French")
        self.fr_entry.grid(row=r2, column=1, columnspan=2, sticky="ew", padx=14, pady=4)
        r2 += 1

        ctk.CTkLabel(sec2, text="In English").grid(row=r2, column=0, sticky="w", padx=14, pady=(4, 12))
        self.en_entry = ctk.CTkEntry(sec2, placeholder_text="Meaning in standard English")
        self.en_entry.grid(row=r2, column=1, columnspan=2, sticky="ew", padx=14, pady=(4, 12))
        r2 += 1

        # --- Section 3: Where & what topic? ---
        sec3, r3 = section_frame(
            scroll, "📍  Where & what topic?",
            "Helps us make sure all 10 required topics get covered.",
        )
        sec3.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 10))

        ctk.CTkLabel(sec3, text="Topic").grid(row=r3, column=0, sticky="w", padx=14, pady=4)
        self.category_menu = ctk.CTkOptionMenu(
            sec3, values=dataset.CATEGORIES, command=self._on_collect_evidence_change,
        )
        self.category_menu.grid(row=r3, column=1, sticky="w", padx=14, pady=4)
        r3 += 1

        ctk.CTkLabel(sec3, text="Heard where?").grid(row=r3, column=0, sticky="w", padx=14, pady=4)
        self.source_location_entry = ctk.CTkEntry(
            sec3, placeholder_text="e.g. taxi Mvan / Marché Mokolo / ICT campus")
        self.source_location_entry.grid(row=r3, column=1, columnspan=2, sticky="ew", padx=14, pady=4)
        r3 += 1

        ctk.CTkLabel(sec3, text="Notes").grid(row=r3, column=0, sticky="w", padx=14, pady=4)
        self.notes_entry = ctk.CTkEntry(sec3, placeholder_text="Optional: register, accent, anything unusual")
        self.notes_entry.grid(row=r3, column=1, columnspan=2, sticky="ew", padx=14, pady=4)
        r3 += 1

        ctk.CTkLabel(sec3, text="Group / name").grid(row=r3, column=0, sticky="w", padx=14, pady=(4, 12))
        self.contributor_entry = ctk.CTkEntry(sec3, placeholder_text="Group name or your initials")
        self.contributor_entry.grid(row=r3, column=1, columnspan=2, sticky="ew", padx=14, pady=(4, 12))
        r3 += 1

        # --- Section 4: Audio (optional) ---
        sec4, r4 = section_frame(
            scroll, "🎙️  Audio (optional)",
            "Not required by the assignment — nice-to-have extra material.",
        )
        sec4.grid(row=3, column=0, sticky="ew", padx=4, pady=(0, 10))

        audio_row = ctk.CTkFrame(sec4, fg_color="transparent")
        audio_row.grid(row=r4, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 12))

        self.record_btn = ctk.CTkButton(
            audio_row, text="● Record", command=self.toggle_recording,
            fg_color=ACCENT_RED if audio_utils.AUDIO_RECORDING_AVAILABLE else "gray40",
            hover_color=ACCENT_RED_HOVER,
            state="normal" if audio_utils.AUDIO_RECORDING_AVAILABLE else "disabled",
            width=110,
        )
        self.record_btn.pack(side="left", padx=(0, 8))

        self.attach_audio_btn = ctk.CTkButton(
            audio_row, text="Attach file...", command=self.attach_audio_file, width=120,
        )
        self.attach_audio_btn.pack(side="left", padx=(0, 8))

        self.play_pending_btn = ctk.CTkButton(
            audio_row, text="▶ Play", command=self.play_pending_audio,
            width=80, state="disabled")
        self.play_pending_btn.pack(side="left", padx=(0, 8))

        self.audio_status_label = ctk.CTkLabel(
            sec4, text="No audio attached", text_color="gray70", wraplength=600, anchor="w",
        )
        self.audio_status_label.grid(
            row=r4 + 1, column=0, columnspan=3, sticky="w", padx=14, pady=(0, 8),
        )

        if not audio_utils.AUDIO_RECORDING_AVAILABLE:
            ctk.CTkLabel(
                sec4,
                text="(Live recording needs the 'sounddevice' package + a working microphone. "
                     "You can still attach an existing audio file instead.)",
                text_color="gray60", font=ctk.CTkFont(size=11), wraplength=760, justify="left",
            ).grid(row=r4 + 2, column=0, columnspan=3, sticky="w", padx=14, pady=(0, 12))

        # --- Save / clear buttons ---
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.grid(row=4, column=0, sticky="ew", padx=4, pady=(4, 4))
        btn_frame.grid_columnconfigure(0, weight=1)

        self.save_btn = ctk.CTkButton(
            btn_frame, text="✓  Save entry   (Ctrl+Enter)", command=self.save_entry,
            height=44, font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=ACCENT_GREEN, hover_color=ACCENT_GREEN_HOVER,
        )
        self.save_btn.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.clear_btn = ctk.CTkButton(
            btn_frame, text="Clear (Esc)", command=lambda: self.clear_form(),
            fg_color="gray30", hover_color="gray20", height=44, width=120,
        )
        self.clear_btn.grid(row=0, column=1)

        self.status_label = ctk.CTkLabel(scroll, text="", text_color=ACCENT_GREEN, font=ctk.CTkFont(size=13))
        self.status_label.grid(row=5, column=0, sticky="w", padx=4, pady=(8, 4))

        ctk.CTkLabel(scroll, text="🕓  Recently added", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=6, column=0, sticky="w", padx=4, pady=(6, 4))
        self.recent_frame = ctk.CTkFrame(scroll, corner_radius=10, border_width=1, border_color="#3a3a3a")
        self.recent_frame.grid(row=7, column=0, sticky="ew", padx=4, pady=(0, 12))

    def _watch_evidence_fields(self):
        groups = (
            ((self.fr_entry, self.en_entry, self.source_location_entry, self.notes_entry,
              self.contributor_entry), self._on_collect_evidence_change),
            ((self.edit_text, self.edit_fr, self.edit_en, self.edit_source_location,
              self.edit_notes), self._on_browse_evidence_change),
        )
        for widgets, changed in groups:
            for widget in widgets:
                variable = ctk.StringVar(value=widget.get())
                variable.trace_add("write", lambda *_, callback=changed: callback())
                widget.configure(textvariable=variable)
                self._field_variables.append(variable)

    def _on_text_change(self, event=None):
        if event is not None:
            if not self.text_entry.edit_modified():
                return
            self.text_entry.edit_modified(False)
        self._on_collect_evidence_change()

    def _cancel_duplicate_check(self):
        if self._dup_check_job is not None:
            self.after_cancel(self._dup_check_job)
            self._dup_check_job = None

    def _on_collect_evidence_change(self, _value=None):
        if self._loading_forms:
            return
        self.review_menu.set("unreviewed")
        self._collect_approval = None
        self._cancel_duplicate_check()
        self._dup_check_job = self.after(400, self._check_duplicate)

    def _on_collect_type_change(self, value):
        if value != "Word":
            self.lexical_menu.set(NO_LEXICAL_CATEGORY)
        self.lexical_menu.configure(state="normal" if value == "Word" else "disabled")
        self._on_collect_evidence_change()

    def _on_collect_review_change(self, value):
        self.text_entry.edit_modified(False)
        self._collect_approval = self._collect_values() if value == "approved" else None

    def _collect_values(self):
        return {
            "text": self.text_entry.get("1.0", "end").strip(),
            "entry_type": self.type_menu.get(),
            "french_gloss": self.fr_entry.get().strip(),
            "english_gloss": self.en_entry.get().strip(),
            "category": self.category_menu.get(),
            "source_location": self.source_location_entry.get().strip(),
            "notes": self.notes_entry.get().strip(),
            "audio_filename": self.pending_audio_path or "",
            "contributor": self.contributor_entry.get().strip(),
            "language": self.language_menu.get(),
            "lexical_category": (
                self.lexical_menu.get()
                if self.type_menu.get() == "Word" and self.lexical_menu.get() != NO_LEXICAL_CATEGORY
                else ""
            ),
        }

    def _check_duplicate(self):
        self._dup_check_job = None
        text = self.text_entry.get("1.0", "end").strip()
        try:
            duplicate = text and dataset.text_exists(text, language=self.language_menu.get())
        except DATASET_ERRORS as error:
            self.dup_warning_label.configure(text=f"⚠ Duplicate check unavailable: {error}")
            return
        self.dup_warning_label.configure(
            text="⚠ This text is already saved in this language (saving is still allowed)" if duplicate else "",
        )

    def _audio_unfinished(self):
        return bool(
            (self.recorder and (self.recorder.recording or self.recorder.stream is not None))
            or self._recording_pending_stop or self._captured_audio is not None
        )

    def _block_unfinished_audio(self, action):
        if not self._audio_unfinished():
            return False
        if self.recorder and self.recorder.recording:
            detail = f"Stop the recording before {action}."
        else:
            detail = (
                f"Finish the recording before {action}. Use Retry stop / Retry audio save, "
                "or Clear to discard it. Your draft has not been changed."
            )
        messagebox.showwarning("Recording unfinished", detail)
        return True

    def _sync_audio_controls(self):
        recording = bool(self.recorder and self.recorder.recording)
        unfinished = self._audio_unfinished()
        record_text = "● Record"
        if recording:
            record_text = "■ Stop"
        elif self._recording_pending_stop or (self.recorder and self.recorder.stream is not None):
            record_text = "Retry stop"
        elif self._captured_audio is not None:
            record_text = "Retry audio save"
        self.record_btn.configure(
            text=record_text, fg_color="#B23B3B" if recording else ACCENT_RED,
            state="normal" if self.recorder else "disabled",
        )
        self.save_btn.configure(state="disabled" if unfinished else "normal")
        self.attach_audio_btn.configure(state="disabled" if unfinished else "normal")
        self.clear_btn.configure(state="disabled" if recording else "normal")
        self.play_pending_btn.configure(state="normal" if self.pending_audio_path and not unfinished else "disabled")
        self.edit_play_btn.configure(state="normal" if self.selected_browse_audio and not unfinished else "disabled")

    def toggle_recording(self):
        if self.recorder is None:
            return
        if self.recorder.recording or self._recording_pending_stop or self.recorder.stream is not None:
            self._cancel_recording_check()
            try:
                audio = self.recorder.stop()
            except AUDIO_ERRORS as error:
                self._recording_pending_stop = True
                self.audio_status_label.configure(text="Recording not finished — use Retry stop.")
                messagebox.showerror("Recording failed", f"Your draft is unchanged. Retry stopping the microphone.\n\n{error}")
                self._sync_audio_controls()
                return
            self._recording_pending_stop = False
            if self.recorder.warning:
                messagebox.showwarning("Review captured audio", self.recorder.warning)
            if audio is None or len(audio) == 0:
                suffix = " Previous attachment kept." if self.pending_audio_path else ""
                self.audio_status_label.configure(text=f"No new audio captured.{suffix}")
            else:
                self._captured_audio = audio
                self._save_captured_audio()
        elif self._captured_audio is not None:
            self._save_captured_audio()
        else:
            try:
                audio_utils.stop_playback()
                self.recorder.start()
            except AUDIO_ERRORS as error:
                self._recording_pending_stop = self.recorder.stream is not None
                self.audio_status_label.configure(text="Microphone unavailable — retry or attach a file.")
                messagebox.showerror("Recording failed", f"Your draft and attachment are unchanged.\n\n{error}")
            else:
                self._recording_pending_stop = True
                self.audio_status_label.configure(text="Recording...")
                self._on_collect_evidence_change()
                self._recording_check_job = self.after(250, self._check_recording)
        self._sync_audio_controls()

    def _cancel_recording_check(self):
        if self._recording_check_job is not None:
            self.after_cancel(self._recording_check_job)
            self._recording_check_job = None

    def _check_recording(self):
        self._recording_check_job = None
        if self._closed or self.recorder is None or not self._recording_pending_stop:
            return
        if self.recorder.recording:
            self._recording_check_job = self.after(250, self._check_recording)
        else:
            self.toggle_recording()

    def _save_captured_audio(self):
        try:
            if self.recorder is None:
                raise audio_utils.AudioError("The recorder is unavailable; captured audio cannot be saved.")
            filename = audio_utils.save_recording(
                self._captured_audio, dataset.AUDIO_DIR, self.recorder.sample_rate
            )
        except AUDIO_ERRORS as error:
            self.audio_status_label.configure(text="Recording kept in memory — use Retry audio save.")
            messagebox.showerror("Audio save failed", f"The recording and draft are kept for retry.\n\n{error}")
            return
        self._captured_audio = None
        self._stage_audio(filename, f"Recorded: {filename}")

    def _stage_audio(self, filename, label):
        self._staged_audio_files.add(filename)
        self.pending_audio_path = filename
        self.audio_status_label.configure(text=label)
        self._on_collect_evidence_change()
        self._discard_staged_audio(keep=filename)
        self._sync_audio_controls()

    def _discard_staged_audio(self, keep=None):
        # Delete the current attachment last so a cleanup failure keeps it retryable.
        filenames = sorted(self._staged_audio_files, key=lambda name: name == self.pending_audio_path)
        for filename in filenames:
            if filename == keep:
                continue
            try:
                os.remove(os.path.join(dataset.AUDIO_DIR, filename))
            except FileNotFoundError:
                pass
            except OSError as error:
                messagebox.showerror("Audio cleanup failed", f"Could not remove unsaved audio {filename}. Retry Clear/close.\n\n{error}")
                return False
            self._staged_audio_files.discard(filename)
        return True

    def attach_audio_file(self):
        if self._block_unfinished_audio("attaching another file"):
            return
        path = filedialog.askopenfilename(
            title="Select audio file",
            filetypes=[("Audio files", "*.wav *.mp3 *.m4a *.ogg *.flac"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            filename = audio_utils.attach_file(path, dataset.AUDIO_DIR)
        except AUDIO_ERRORS as error:
            messagebox.showerror("Attachment failed", f"Your previous attachment and draft are unchanged.\n\n{error}")
            return
        self._stage_audio(filename, f"Attached: {os.path.basename(path)}")

    def _play_audio_filename(self, filename):
        if not filename or self._block_unfinished_audio("playing audio"):
            return
        try:
            played = audio_utils.play_audio(os.path.join(dataset.AUDIO_DIR, filename))
        except AUDIO_ERRORS as error:
            messagebox.showerror("Playback failed", str(error))
            return
        if not played:
            messagebox.showerror("Playback failed", "Could not play this audio file. Check the file and your audio player.")

    def play_pending_audio(self):
        self._play_audio_filename(self.pending_audio_path)

    def save_entry(self):
        if self._block_unfinished_audio("saving this entry"):
            return
        values = self._collect_values()
        text = values["text"]
        if not text:
            messagebox.showwarning("Missing text", "Please enter the Francanglais word/phrase/sentence.")
            return
        approved = self.review_menu.get() == "approved" and self._collect_approval == values
        entry = {
            **values, "id": uuid.uuid4().hex[:10],
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "review_status": "approved" if approved else "unreviewed",
        }
        try:
            dataset.append_entry(entry)
        except DATASET_ERRORS as error:
            messagebox.showerror("Save failed", f"Your draft and audio are unchanged. Correct the storage problem and retry.\n\n{error}")
            return
        self._staged_audio_files.discard(self.pending_audio_path)
        self._reset_collect_form(keep_contributor=True)
        self.status_label.configure(text=f'✓ Saved: "{text[:40]}"')
        self._release_audio()
        self._discard_staged_audio()
        self._refresh_views()

    def clear_form(self, keep_contributor=False):
        if self.recorder and self.recorder.recording:
            messagebox.showwarning("Recording in progress", "Stop recording before clearing the form.")
            return
        if not self._release_audio() or not self._discard_staged_audio():
            return
        self._reset_collect_form(keep_contributor)
        self.status_label.configure(text="")

    def _reset_collect_form(self, keep_contributor=False):
        self._cancel_duplicate_check()
        self._loading_forms = True
        try:
            self.text_entry.delete("1.0", "end")
            self.text_entry.edit_modified(False)
            for widget in (self.fr_entry, self.en_entry, self.source_location_entry, self.notes_entry):
                widget.delete(0, "end")
            if not keep_contributor:
                self.contributor_entry.delete(0, "end")
            self.type_menu.set(dataset.ENTRY_TYPES[0])
            self.category_menu.set(dataset.CATEGORIES[0])
            self.language_menu.set("unspecified")
            self.review_menu.set("unreviewed")
            self.lexical_menu.set(NO_LEXICAL_CATEGORY)
            self.lexical_menu.configure(state="normal")
            self.pending_audio_path = None
            self._captured_audio = None
            self._recording_pending_stop = False
            self._collect_approval = None
            self.audio_status_label.configure(text="No audio attached")
            self.dup_warning_label.configure(text="")
        finally:
            self._loading_forms = False
        self._sync_audio_controls()
        self.text_entry.focus_set()

    def _load_entries(self):
        try:
            return dataset.load_all()
        except DATASET_ERRORS as error:
            messagebox.showerror("Dataset unavailable", f"Could not read the collection. Your draft and current view are unchanged.\n\n{error}")
            return None

    def _refresh_views(self):
        entries = self._load_entries()
        if entries is None:
            return False
        self._refresh_count(entries)
        self._refresh_recent(entries)
        self._refresh_browse_list(entries)
        self._refresh_stats(entries)
        return True

    def _refresh_count(self, entries=None):
        entries = self._load_entries() if entries is None else entries
        if entries is not None:
            self.count_label.configure(text=f"📦  {len(entries)} entries saved so far")

    def _refresh_recent(self, entries=None):
        entries = self._load_entries() if entries is None else entries
        if entries is None:
            return
        for widget in self.recent_frame.winfo_children():
            widget.destroy()
        entries = list(reversed(entries[-6:]))
        if not entries:
            ctk.CTkLabel(self.recent_frame, text="No entries yet — add your first one above.",
                         text_color="gray60").pack(anchor="w", padx=14, pady=10)
            return
        for e in entries:
            audio_tag = " 🔊" if e.get("audio_filename") else ""
            line = f'[{e.get("entry_type","")}] {e.get("text","")}{audio_tag}'
            ctk.CTkLabel(self.recent_frame, text=line, anchor="w").pack(fill="x", padx=14, pady=3)

    # ==================================================================
    # BROWSE & EDIT TAB
    # ==================================================================
    def _build_browse_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            parent, text="Find, fix, or remove entries you've already added. Click a row to edit it below.",
            text_color="gray60", font=ctk.CTkFont(size=12),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=4, pady=(6, 8))

        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=(0, 8))
        top.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            top, placeholder_text="🔎 Search text, topic, group, language, review, or lexical category...",
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", lambda e: self._refresh_browse_list())

        ctk.CTkButton(top, text="Refresh", command=self._refresh_browse_list, width=90).grid(row=0, column=1)

        columns = ("text", "type", "language", "review", "category", "contributor", "audio")
        self.tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse", height=5)
        self.tree.heading("text", text="Text")
        self.tree.heading("type", text="Type")
        self.tree.heading("language", text="Language")
        self.tree.heading("review", text="Review")
        self.tree.heading("category", text="Topic")
        self.tree.heading("contributor", text="Group")
        self.tree.heading("audio", text="Audio")
        self.tree.column("text", width=220, minwidth=120)
        self.tree.column("type", width=70, anchor="center")
        self.tree.column("language", width=95)
        self.tree.column("review", width=95)
        self.tree.column("category", width=130)
        self.tree.column("contributor", width=90)
        self.tree.column("audio", width=50, anchor="center")
        self.tree.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)
        self.tree.bind("<<TreeviewSelect>>", self._on_browse_select)

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=2, column=1, sticky="ns", pady=4)
        horizontal = ttk.Scrollbar(parent, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=horizontal.set)
        horizontal.grid(row=3, column=0, sticky="ew", padx=4)

        # --- edit panel ---
        edit_scroll = ctk.CTkScrollableFrame(parent, height=290, fg_color="transparent")
        edit_scroll.grid(row=4, column=0, columnspan=2, sticky="ew", padx=0, pady=(8, 4))
        edit_scroll.grid_columnconfigure(0, weight=1)
        edit, er = section_frame(edit_scroll, "✏️  Selected entry", "")
        edit.grid(row=0, column=0, sticky="ew", padx=4)
        edit.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(edit, text="Text").grid(row=er, column=0, sticky="w", padx=14, pady=4)
        self.edit_text = ctk.CTkEntry(edit)
        self.edit_text.grid(row=er, column=1, columnspan=3, sticky="ew", padx=14, pady=4)
        er += 1

        ctk.CTkLabel(edit, text="Type").grid(row=er, column=0, sticky="w", padx=14, pady=4)
        self.edit_type = ctk.CTkOptionMenu(
            edit, values=dataset.ENTRY_TYPES, command=self._on_browse_type_change,
        )
        self.edit_type.grid(row=er, column=1, sticky="w", padx=14, pady=4)

        ctk.CTkLabel(edit, text="Topic").grid(row=er, column=2, sticky="w", padx=14, pady=4)
        self.edit_category = ctk.CTkOptionMenu(
            edit, values=dataset.CATEGORIES, command=self._on_browse_evidence_change,
        )
        self.edit_category.grid(row=er, column=3, sticky="w", padx=14, pady=4)
        er += 1

        ctk.CTkLabel(edit, text="Language").grid(row=er, column=0, sticky="w", padx=14, pady=4)
        self.edit_language = ctk.CTkOptionMenu(
            edit, values=dataset.DATASET_LANGUAGES, command=self._on_browse_evidence_change,
        )
        self.edit_language.set("unspecified")
        self.edit_language.grid(row=er, column=1, sticky="w", padx=14, pady=4)
        ctk.CTkLabel(edit, text="Review").grid(row=er, column=2, sticky="w", padx=14, pady=4)
        self.edit_review = ctk.CTkOptionMenu(
            edit, values=REVIEW_STATUSES, command=self._on_browse_review_change,
        )
        self.edit_review.grid(row=er, column=3, sticky="w", padx=14, pady=4)
        Tooltip(self.edit_review, "Any evidence change resets approval. Review the final edit, then explicitly approve.")
        er += 1

        ctk.CTkLabel(edit, text="Lexical category").grid(row=er, column=0, sticky="w", padx=14, pady=4)
        self.edit_lexical = ctk.CTkOptionMenu(
            edit, values=[NO_LEXICAL_CATEGORY, *dataset.LEXICAL_CATEGORIES],
            command=self._on_browse_evidence_change, width=220,
        )
        self.edit_lexical.grid(row=er, column=1, columnspan=3, sticky="w", padx=14, pady=4)
        er += 1

        ctk.CTkLabel(edit, text="French").grid(row=er, column=0, sticky="w", padx=14, pady=4)
        self.edit_fr = ctk.CTkEntry(edit)
        self.edit_fr.grid(row=er, column=1, sticky="ew", padx=14, pady=4)

        ctk.CTkLabel(edit, text="English").grid(row=er, column=2, sticky="w", padx=14, pady=4)
        self.edit_en = ctk.CTkEntry(edit)
        self.edit_en.grid(row=er, column=3, sticky="ew", padx=14, pady=4)
        er += 1

        ctk.CTkLabel(edit, text="Location").grid(row=er, column=0, sticky="w", padx=14, pady=4)
        self.edit_source_location = ctk.CTkEntry(edit)
        self.edit_source_location.grid(row=er, column=1, columnspan=3, sticky="ew", padx=14, pady=4)
        er += 1

        ctk.CTkLabel(edit, text="Notes").grid(row=er, column=0, sticky="w", padx=14, pady=4)
        self.edit_notes = ctk.CTkEntry(edit)
        self.edit_notes.grid(row=er, column=1, columnspan=3, sticky="ew", padx=14, pady=4)
        er += 1

        action_row = ctk.CTkFrame(edit, fg_color="transparent")
        action_row.grid(row=er, column=0, columnspan=4, sticky="ew", padx=14, pady=(8, 12))

        self.edit_play_btn = ctk.CTkButton(action_row, text="▶ Play audio", command=self._play_selected_audio,
                                            width=110, state="disabled")
        self.edit_play_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(action_row, text="Save changes", command=self._save_browse_edit,
                      fg_color=ACCENT_GREEN, hover_color=ACCENT_GREEN_HOVER,
                      width=130).pack(side="left", padx=(0, 8))

        ctk.CTkButton(action_row, text="Delete entry", command=self._delete_browse_entry,
                      fg_color=ACCENT_RED, hover_color=ACCENT_RED_HOVER, width=110).pack(side="left")

        self.browse_status_label = ctk.CTkLabel(edit, text="Select a row above to edit it.", text_color="gray60")
        self.browse_status_label.grid(row=er + 1, column=0, columnspan=4, sticky="w", padx=14, pady=(0, 10))

    def _refresh_browse_list(self, entries=None):
        entries = self._load_entries() if entries is None else entries
        if entries is None:
            return
        query = self.search_entry.get().strip().casefold()
        self.tree.delete(*self.tree.get_children())
        self._browse_entries_by_id = {entry["id"]: entry for entry in entries}
        for e in entries:
            haystack = " ".join(e.values()).casefold()
            if query and query not in haystack:
                continue
            self.tree.insert(
                "", "end", iid=e["id"],
                values=(
                    e.get("text", ""), e.get("entry_type", ""),
                    e.get("language", "unspecified"), e.get("review_status", "unreviewed"), e.get("category", ""),
                    e.get("contributor", ""), "🔊" if e.get("audio_filename") else "",
                ),
            )
        if self.selected_browse_id and self.selected_browse_id not in self._browse_entries_by_id:
            self.browse_status_label.configure(text="This entry no longer exists. Unsaved edits have been kept.")

    def _on_browse_select(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return
        entry_id = selection[0]
        entry = self._browse_entries_by_id.get(entry_id)
        if not entry:
            return
        self._populate_browse_entry(entry)

    def _populate_browse_entry(self, entry):
        entry = dataset.normalize_entry(entry)
        self.selected_browse_id = entry["id"]
        self.selected_browse_audio = entry.get("audio_filename") or None
        self._selected_browse_entry = dict(entry)
        self._browse_approval = None
        self._loading_forms = True
        try:
            for widget, field in (
                (self.edit_text, "text"), (self.edit_fr, "french_gloss"),
                (self.edit_en, "english_gloss"), (self.edit_source_location, "source_location"),
                (self.edit_notes, "notes"),
            ):
                widget.delete(0, "end")
                widget.insert(0, entry.get(field, ""))
            for menu, field, options in (
                (self.edit_type, "entry_type", dataset.ENTRY_TYPES),
                (self.edit_category, "category", dataset.CATEGORIES),
            ):
                value = entry.get(field, "")
                menu.configure(values=list(dict.fromkeys([*options, value])))
                menu.set(value)
            self.edit_language.set(entry["language"])
            self.edit_review.set(entry["review_status"])
            self.edit_lexical.set(entry["lexical_category"] or NO_LEXICAL_CATEGORY)
            self.edit_lexical.configure(state="normal" if entry.get("entry_type") == "Word" else "disabled")
        finally:
            self._loading_forms = False
        self._sync_audio_controls()
        self.browse_status_label.configure(text=f"Editing entry {entry['id']}")

    def _browse_values(self):
        original = self._selected_browse_entry or {}
        values = {}
        for widget, field in (
            (self.edit_text, "text"), (self.edit_fr, "french_gloss"),
            (self.edit_en, "english_gloss"), (self.edit_source_location, "source_location"),
            (self.edit_notes, "notes"),
        ):
            value = widget.get()
            values[field] = value if value == original.get(field, "") else value.strip()
        values.update(
            entry_type=self.edit_type.get(), category=self.edit_category.get(),
            language=self.edit_language.get(),
            lexical_category="" if self.edit_lexical.get() == NO_LEXICAL_CATEGORY else self.edit_lexical.get(),
        )
        return values

    def _on_browse_evidence_change(self, _value=None):
        if self._loading_forms or not self.selected_browse_id:
            return
        self.edit_review.set("unreviewed")
        self._browse_approval = None

    def _on_browse_type_change(self, value):
        if value != "Word":
            self.edit_lexical.set(NO_LEXICAL_CATEGORY)
        self.edit_lexical.configure(state="normal" if value == "Word" else "disabled")
        self._on_browse_evidence_change()

    def _on_browse_review_change(self, value):
        self._browse_approval = self._browse_values() if value == "approved" else None

    def _play_selected_audio(self):
        self._play_audio_filename(self.selected_browse_audio)

    def _save_browse_edit(self):
        if not self.selected_browse_id:
            messagebox.showinfo("No selection", "Select an entry from the table first.")
            return
        values = self._browse_values()
        if not values["text"].strip():
            messagebox.showwarning("Missing text", "Text cannot be empty.")
            return
        original = self._selected_browse_entry or {}
        updated = {key: value for key, value in values.items() if value != original.get(key, "")}
        review = self.edit_review.get()
        if review == "approved" and self._browse_approval == values:
            updated["review_status"] = "approved"
        elif updated or review != original.get("review_status", "unreviewed"):
            updated["review_status"] = "unreviewed"
        try:
            dataset.update_entry(self.selected_browse_id, updated)
        except dataset.EntryNotFoundError as error:
            self.browse_status_label.configure(text="Changes not saved: the entry no longer exists. Your edits are kept.")
            messagebox.showerror("Entry no longer exists", f"{error}\nYour edits have been kept; select an existing entry to continue.")
            return
        except DATASET_ERRORS as error:
            self.browse_status_label.configure(text="Changes not saved. Your edits are kept for retry.")
            messagebox.showerror("Save failed", f"Your edits are unchanged. Correct the storage problem and retry.\n\n{error}")
            return
        self._selected_browse_entry = dict(original)
        dataset.apply_entry_update(self._selected_browse_entry, updated)
        self.edit_review.set(self._selected_browse_entry.get("review_status", "unreviewed"))
        self._browse_approval = None
        refreshed = self._refresh_views()
        latest = self._browse_entries_by_id.get(self.selected_browse_id) if refreshed else None
        if latest is not None:
            self._populate_browse_entry(latest)
        status = "✓ Changes saved."
        if not refreshed:
            status += " Refresh unavailable; try Refresh."
        elif latest is None:
            status += " This entry has since been removed."
        self.browse_status_label.configure(text=status)

    def _clear_browse_selection(self):
        self.selected_browse_id = None
        self.selected_browse_audio = None
        self._selected_browse_entry = None
        self._browse_approval = None
        self._loading_forms = True
        try:
            for widget in (self.edit_text, self.edit_fr, self.edit_en, self.edit_source_location, self.edit_notes):
                widget.delete(0, "end")
            self.edit_type.set(dataset.ENTRY_TYPES[0])
            self.edit_category.set(dataset.CATEGORIES[0])
            self.edit_language.set("unspecified")
            self.edit_review.set("unreviewed")
            self.edit_lexical.set(NO_LEXICAL_CATEGORY)
            self.edit_lexical.configure(state="normal")
        finally:
            self._loading_forms = False
        self._sync_audio_controls()

    def _delete_browse_entry(self):
        if not self.selected_browse_id:
            messagebox.showinfo("No selection", "Select an entry from the table first.")
            return
        if not messagebox.askyesno("Delete entry", "Delete this entry permanently? This cannot be undone."):
            return
        try:
            dataset.delete_entry(self.selected_browse_id)
        except dataset.EntryNotFoundError as error:
            self.browse_status_label.configure(text="Entry already removed. Your unsaved edits are kept.")
            messagebox.showerror("Entry no longer exists", str(error))
            return
        except DATASET_ERRORS as error:
            self.browse_status_label.configure(text="Entry not deleted. Retry after correcting the storage problem.")
            messagebox.showerror("Delete failed", str(error))
            return
        self._clear_browse_selection()
        self.browse_status_label.configure(text="Entry deleted.")
        self._refresh_views()

    # ==================================================================
    # STATS TAB
    # ==================================================================
    def _build_stats_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            parent, text="A quick look at topics, types, languages, and human review status.",
            text_color="gray60", font=ctk.CTkFont(size=12),
        ).grid(row=0, column=0, sticky="w", padx=4, pady=(6, 8))

        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 8))
        self.stats_total_label = ctk.CTkLabel(top, text="", font=ctk.CTkFont(size=16, weight="bold"))
        self.stats_total_label.pack(side="left")
        ctk.CTkButton(top, text="Refresh", command=self._refresh_stats, width=90).pack(side="right")

        cols = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        cols.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)
        cols.grid_columnconfigure(0, weight=1)
        cols.grid_columnconfigure(1, weight=1)

        self.stats_type_frame = ctk.CTkFrame(cols, corner_radius=10, border_width=1, border_color="#3a3a3a")
        self.stats_type_frame.grid(row=0, column=0, sticky="new", padx=(0, 8))
        ctk.CTkLabel(self.stats_type_frame, text="By type", font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=14, pady=(12, 6))

        self.stats_category_frame = ctk.CTkFrame(cols, corner_radius=10, border_width=1, border_color="#3a3a3a")
        self.stats_category_frame.grid(row=0, column=1, sticky="new", padx=(8, 0))
        ctk.CTkLabel(self.stats_category_frame, text="By topic", font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=14, pady=(12, 6))

        self.stats_language_frame = ctk.CTkFrame(cols, corner_radius=10, border_width=1, border_color="#3a3a3a")
        self.stats_language_frame.grid(row=1, column=0, sticky="new", padx=(0, 8), pady=(12, 0))
        ctk.CTkLabel(self.stats_language_frame, text="By language", font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=14, pady=(12, 6))
        self.stats_review_frame = ctk.CTkFrame(cols, corner_radius=10, border_width=1, border_color="#3a3a3a")
        self.stats_review_frame.grid(row=1, column=1, sticky="new", padx=(8, 0), pady=(12, 0))
        ctk.CTkLabel(self.stats_review_frame, text="By review", font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=14, pady=(12, 6))

    def _on_tab_changed(self):
        if self._loading_forms:
            return
        current = self.tabs.get()
        if current == "📊  Stats":
            self._refresh_stats()
        elif current == "🔍  Browse & Edit":
            self._refresh_browse_list()

    def _refresh_stats(self, entries=None):
        entries = self._load_entries() if entries is None else entries
        if entries is None:
            return
        groups = (
            (self.stats_type_frame, "entry_type", ACCENT_GREEN),
            (self.stats_category_frame, "category", None),
            (self.stats_language_frame, "language", None),
            (self.stats_review_frame, "review_status", ACCENT_GREEN),
        )
        for frame, _field, _color in groups:
            for widget in list(frame.winfo_children())[1:]:  # keep the heading label
                widget.destroy()

        total = len(entries)
        self.stats_total_label.configure(text=f"📦  Total entries: {total}")
        for frame, field, color in groups:
            self._render_bar_group(frame, Counter(entry.get(field) or "(none)" for entry in entries), total, color)

    def _render_bar_group(self, frame, counts: dict, total: int, color):
        if not counts:
            ctk.CTkLabel(frame, text="No data yet — add entries in the Collect tab.", text_color="gray60").pack(
                anchor="w", padx=14, pady=(0, 12))
            return
        for key, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=3)
            ctk.CTkLabel(row, text=f"{key} ({count})", width=170, anchor="w").pack(side="left")
            bar_kwargs = {"progress_color": color} if color else {}
            bar = ctk.CTkProgressBar(row, **bar_kwargs)
            bar.pack(side="left", fill="x", expand=True, padx=(6, 0))
            bar.set(count / total if total else 0)
        ctk.CTkLabel(frame, text="").pack(pady=4)  # bottom spacing

    def _release_audio(self):
        self._cancel_recording_check()
        failures = []
        operations = [audio_utils.stop_playback]
        if self.recorder is not None:
            operations.insert(0, self.recorder.close)
        for operation in operations:
            try:
                operation()
            except AUDIO_ERRORS as error:
                failures.append(str(error))
        if failures:
            self._sync_audio_controls()
            messagebox.showerror("Audio cleanup failed", "Could not release audio resources. Retry Clear/close.\n\n" + "\n".join(failures))
            return False
        return True

    def _on_close(self):
        values = self._collect_values()
        collect_draft = any(values[field] for field in (
            "text", "french_gloss", "english_gloss", "source_location", "notes", "audio_filename",
        ))
        browse_draft = self._selected_browse_entry is not None and (
            any(value != self._selected_browse_entry.get(field, "") for field, value in self._browse_values().items())
            or self.edit_review.get() != self._selected_browse_entry.get("review_status", "unreviewed")
        )
        if collect_draft or browse_draft or self._audio_unfinished() or self._staged_audio_files:
            if not messagebox.askyesno("Close collector", "Discard unsaved text, edits, and audio and close?"):
                return
        self.destroy()

    def destroy(self):
        """Release devices, timers and draft-owned audio before destroying Tk."""
        if self._closed:
            return
        if not self._release_audio() or not self._discard_staged_audio():
            return
        self._cancel_duplicate_check()
        self._captured_audio = None
        self._closed = True
        super().destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()