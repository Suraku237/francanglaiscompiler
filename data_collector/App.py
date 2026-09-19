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
  - Stats            : counts by category and by type

Run:
    pip install -r ../requirements-desktop.txt
    python App.py
"""

import os
import uuid
import datetime
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
import tkinter.ttk as ttk

import customtkinter as ctk

import dataset
import audio_utils


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT_GREEN = "#2FA572"
ACCENT_GREEN_HOVER = "#248858"
ACCENT_RED = "#8B2E2E"
ACCENT_RED_HOVER = "#6E2424"

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
• Duplicate warning: if the exact text is already saved, you'll see a
  small orange note — that's just a heads-up, not an error.
• Audio is entirely optional. The assignment only requires you to
  write down what you heard.
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

        dataset.ensure_dataset_file()
        style_treeview_dark()

        self.pending_audio_path = None      # filename staged for the new entry (Collect tab)
        self.selected_browse_id = None       # id of the entry currently loaded in Browse & Edit
        self.selected_browse_audio = None    # audio filename of the selected browse entry
        self.recorder = audio_utils.Recorder() if audio_utils.AUDIO_RECORDING_AVAILABLE else None
        self._dup_check_job = None

        self._build_header()

        self.tabs = ctk.CTkTabview(self, command=self._on_tab_changed)
        self.tabs.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.tabs.add("📝  Collect")
        self.tabs.add("🔍  Browse & Edit")
        self.tabs.add("📊  Stats")

        self._build_collect_tab(self.tabs.tab("📝  Collect"))
        self._build_browse_tab(self.tabs.tab("🔍  Browse & Edit"))
        self._build_stats_tab(self.tabs.tab("📊  Stats"))

        # Keyboard shortcuts (active anywhere in the window)
        self.bind("<Control-Return>", lambda e: self.save_entry())
        self.bind("<Escape>", lambda e: self.clear_form(keep_contributor=True))

        self._refresh_recent()
        self._refresh_count()

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
        self.text_entry.bind("<KeyRelease>", self._on_text_change)
        Tooltip(self.text_entry, 'e.g. "Le taxi don refuse for carry me go quartier"')
        r += 1

        self.dup_warning_label = ctk.CTkLabel(
            sec1, text="", text_color="#E0A93B", font=ctk.CTkFont(size=12))
        self.dup_warning_label.grid(row=r, column=1, columnspan=2, sticky="w", padx=14)
        r += 1

        ctk.CTkLabel(sec1, text="Is it a...").grid(row=r, column=0, sticky="w", padx=14, pady=(6, 12))
        self.type_menu = ctk.CTkOptionMenu(sec1, values=dataset.ENTRY_TYPES)
        self.type_menu.grid(row=r, column=1, sticky="w", padx=14, pady=(6, 12))
        r += 1

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
        self.category_menu = ctk.CTkOptionMenu(sec3, values=dataset.CATEGORIES)
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

        ctk.CTkButton(audio_row, text="Attach file...", command=self.attach_audio_file,
                      width=120).pack(side="left", padx=(0, 8))

        self.play_pending_btn = ctk.CTkButton(
            audio_row, text="▶ Play", command=self.play_pending_audio,
            width=80, state="disabled")
        self.play_pending_btn.pack(side="left", padx=(0, 8))

        self.audio_status_label = ctk.CTkLabel(audio_row, text="No audio attached", text_color="gray70")
        self.audio_status_label.pack(side="left", padx=(8, 0))

        if not audio_utils.AUDIO_RECORDING_AVAILABLE:
            ctk.CTkLabel(
                sec4,
                text="(Live recording needs the 'sounddevice' package + a working microphone. "
                     "You can still attach an existing audio file instead.)",
                text_color="gray60", font=ctk.CTkFont(size=11), wraplength=760, justify="left",
            ).grid(row=r4 + 1, column=0, columnspan=3, sticky="w", padx=14, pady=(0, 12))

        # --- Save / clear buttons ---
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.grid(row=4, column=0, sticky="ew", padx=4, pady=(4, 4))
        btn_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            btn_frame, text="✓  Save entry   (Ctrl+Enter)", command=self.save_entry,
            height=44, font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=ACCENT_GREEN, hover_color=ACCENT_GREEN_HOVER,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="Clear (Esc)", command=lambda: self.clear_form(),
            fg_color="gray30", hover_color="gray20", height=44, width=120,
        ).grid(row=0, column=1)

        self.status_label = ctk.CTkLabel(scroll, text="", text_color=ACCENT_GREEN, font=ctk.CTkFont(size=13))
        self.status_label.grid(row=5, column=0, sticky="w", padx=4, pady=(8, 4))

        ctk.CTkLabel(scroll, text="🕓  Recently added", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=6, column=0, sticky="w", padx=4, pady=(6, 4))
        self.recent_frame = ctk.CTkFrame(scroll, corner_radius=10, border_width=1, border_color="#3a3a3a")
        self.recent_frame.grid(row=7, column=0, sticky="ew", padx=4, pady=(0, 12))

    def _on_text_change(self, event=None):
        if self._dup_check_job is not None:
            self.after_cancel(self._dup_check_job)
        self._dup_check_job = self.after(400, self._check_duplicate)

    def _check_duplicate(self):
        text = self.text_entry.get("1.0", "end").strip()
        if text and dataset.text_exists(text):
            self.dup_warning_label.configure(text="⚠ This exact text is already in the dataset")
        else:
            self.dup_warning_label.configure(text="")

    def toggle_recording(self):
        if not audio_utils.AUDIO_RECORDING_AVAILABLE or not self.recorder:
            return
        if not self.recorder.recording:
            self.recorder.start()
            self.record_btn.configure(text="■ Stop", fg_color="#B23B3B")
            self.audio_status_label.configure(text="Recording...")
            self.play_pending_btn.configure(state="disabled")
        else:
            audio = self.recorder.stop()
            self.record_btn.configure(text="● Record", fg_color=ACCENT_RED)
            if audio is None or len(audio) == 0:
                self.audio_status_label.configure(text="No audio captured")
                return
            filename = audio_utils.save_recording(audio, dataset.AUDIO_DIR)
            self.pending_audio_path = filename
            self.audio_status_label.configure(text=f"Recorded: {filename}")
            self.play_pending_btn.configure(state="normal")

    def attach_audio_file(self):
        path = filedialog.askopenfilename(
            title="Select audio file",
            filetypes=[("Audio files", "*.wav *.mp3 *.m4a *.ogg *.flac"), ("All files", "*.*")],
        )
        if not path:
            return
        filename = audio_utils.attach_file(path, dataset.AUDIO_DIR)
        self.pending_audio_path = filename
        self.audio_status_label.configure(text=f"Attached: {os.path.basename(path)}")
        self.play_pending_btn.configure(state="normal")

    def play_pending_audio(self):
        if not self.pending_audio_path:
            return
        full_path = os.path.join(dataset.AUDIO_DIR, self.pending_audio_path)
        if not audio_utils.play_audio(full_path):
            messagebox.showerror("Playback failed", "Could not play this audio file.")

    def save_entry(self):
        text = self.text_entry.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Missing text", "Please enter the Francanglais word/phrase/sentence.")
            return

        entry = {
            "id": uuid.uuid4().hex[:10],
            "text": text,
            "entry_type": self.type_menu.get(),
            "french_gloss": self.fr_entry.get().strip(),
            "english_gloss": self.en_entry.get().strip(),
            "category": self.category_menu.get(),
            "source_location": self.source_location_entry.get().strip(),
            "notes": self.notes_entry.get().strip(),
            "audio_filename": self.pending_audio_path or "",
            "contributor": self.contributor_entry.get().strip(),
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        dataset.append_entry(entry)

        self.status_label.configure(text=f'✓ Saved: "{text[:40]}"')
        self._refresh_count()
        self._refresh_recent()
        self.clear_form(keep_contributor=True)

    def clear_form(self, keep_contributor=False):
        self.text_entry.delete("1.0", "end")
        self.fr_entry.delete(0, "end")
        self.en_entry.delete(0, "end")
        self.source_location_entry.delete(0, "end")
        self.notes_entry.delete(0, "end")
        if not keep_contributor:
            self.contributor_entry.delete(0, "end")
        self.type_menu.set(dataset.ENTRY_TYPES[0])
        self.category_menu.set(dataset.CATEGORIES[0])
        self.pending_audio_path = None
        self.audio_status_label.configure(text="No audio attached")
        self.play_pending_btn.configure(state="disabled")
        self.dup_warning_label.configure(text="")
        self.text_entry.focus_set()

    def _refresh_count(self):
        n = dataset.total_count()
        self.count_label.configure(text=f"📦  {n} entries saved so far")

    def _refresh_recent(self):
        for widget in self.recent_frame.winfo_children():
            widget.destroy()
        entries = dataset.load_all()[-6:]
        entries.reverse()
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

        self.search_entry = ctk.CTkEntry(top, placeholder_text="🔎 Search by text, topic, or group name...")
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", lambda e: self._refresh_browse_list())

        ctk.CTkButton(top, text="Refresh", command=self._refresh_browse_list, width=90).grid(row=0, column=1)

        columns = ("text", "type", "category", "contributor", "audio")
        self.tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("text", text="Text")
        self.tree.heading("type", text="Type")
        self.tree.heading("category", text="Topic")
        self.tree.heading("contributor", text="Group")
        self.tree.heading("audio", text="Audio")
        self.tree.column("text", width=280)
        self.tree.column("type", width=80, anchor="center")
        self.tree.column("category", width=140)
        self.tree.column("contributor", width=100)
        self.tree.column("audio", width=60, anchor="center")
        self.tree.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)
        self.tree.bind("<<TreeviewSelect>>", self._on_browse_select)

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=2, column=1, sticky="ns", pady=4)

        # --- edit panel ---
        edit, er = section_frame(parent, "✏️  Selected entry", "")
        edit.grid(row=3, column=0, columnspan=2, sticky="ew", padx=4, pady=(8, 4))
        edit.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(edit, text="Text").grid(row=er, column=0, sticky="w", padx=14, pady=4)
        self.edit_text = ctk.CTkEntry(edit)
        self.edit_text.grid(row=er, column=1, columnspan=3, sticky="ew", padx=14, pady=4)
        er += 1

        ctk.CTkLabel(edit, text="Type").grid(row=er, column=0, sticky="w", padx=14, pady=4)
        self.edit_type = ctk.CTkOptionMenu(edit, values=dataset.ENTRY_TYPES)
        self.edit_type.grid(row=er, column=1, sticky="w", padx=14, pady=4)

        ctk.CTkLabel(edit, text="Topic").grid(row=er, column=2, sticky="w", padx=14, pady=4)
        self.edit_category = ctk.CTkOptionMenu(edit, values=dataset.CATEGORIES)
        self.edit_category.grid(row=er, column=3, sticky="w", padx=14, pady=4)
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

        self._refresh_browse_list()

    def _refresh_browse_list(self):
        query = self.search_entry.get().strip().lower() if hasattr(self, "search_entry") else ""
        self.tree.delete(*self.tree.get_children())
        self._browse_entries_by_id = {}
        for e in dataset.load_all():
            haystack = f'{e.get("text","")} {e.get("category","")} {e.get("contributor","")}'.lower()
            if query and query not in haystack:
                continue
            self._browse_entries_by_id[e["id"]] = e
            self.tree.insert(
                "", "end", iid=e["id"],
                values=(
                    e.get("text", ""), e.get("entry_type", ""), e.get("category", ""),
                    e.get("contributor", ""), "🔊" if e.get("audio_filename") else "",
                ),
            )

    def _on_browse_select(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return
        entry_id = selection[0]
        entry = self._browse_entries_by_id.get(entry_id)
        if not entry:
            return

        self.selected_browse_id = entry_id
        self.selected_browse_audio = entry.get("audio_filename") or None

        self.edit_text.delete(0, "end")
        self.edit_text.insert(0, entry.get("text", ""))
        self.edit_type.set(entry.get("entry_type") or dataset.ENTRY_TYPES[0])
        self.edit_category.set(entry.get("category") or dataset.CATEGORIES[0])
        self.edit_fr.delete(0, "end")
        self.edit_fr.insert(0, entry.get("french_gloss", ""))
        self.edit_en.delete(0, "end")
        self.edit_en.insert(0, entry.get("english_gloss", ""))
        self.edit_source_location.delete(0, "end")
        self.edit_source_location.insert(0, entry.get("source_location", ""))
        self.edit_notes.delete(0, "end")
        self.edit_notes.insert(0, entry.get("notes", ""))

        self.edit_play_btn.configure(state="normal" if self.selected_browse_audio else "disabled")
        self.browse_status_label.configure(text=f"Editing entry {entry_id}")

    def _play_selected_audio(self):
        if not self.selected_browse_audio:
            return
        full_path = os.path.join(dataset.AUDIO_DIR, self.selected_browse_audio)
        if not audio_utils.play_audio(full_path):
            messagebox.showerror("Playback failed", "Could not play this audio file.")

    def _save_browse_edit(self):
        if not self.selected_browse_id:
            messagebox.showinfo("No selection", "Select an entry from the table first.")
            return
        text = self.edit_text.get().strip()
        if not text:
            messagebox.showwarning("Missing text", "Text cannot be empty.")
            return
        updated = {
            "text": text,
            "entry_type": self.edit_type.get(),
            "category": self.edit_category.get(),
            "french_gloss": self.edit_fr.get().strip(),
            "english_gloss": self.edit_en.get().strip(),
            "source_location": self.edit_source_location.get().strip(),
            "notes": self.edit_notes.get().strip(),
        }
        dataset.update_entry(self.selected_browse_id, updated)
        self.browse_status_label.configure(text="✓ Changes saved.")
        self._refresh_browse_list()
        self._refresh_count()
        self._refresh_recent()

    def _delete_browse_entry(self):
        if not self.selected_browse_id:
            messagebox.showinfo("No selection", "Select an entry from the table first.")
            return
        if not messagebox.askyesno("Delete entry", "Delete this entry permanently? This cannot be undone."):
            return
        dataset.delete_entry(self.selected_browse_id)
        self.selected_browse_id = None
        self.selected_browse_audio = None
        self.browse_status_label.configure(text="Entry deleted.")
        self._refresh_browse_list()
        self._refresh_count()
        self._refresh_recent()

    # ==================================================================
    # STATS TAB
    # ==================================================================
    def _build_stats_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            parent, text="A quick look at how balanced the collection is across topics and types.",
            text_color="gray60", font=ctk.CTkFont(size=12),
        ).grid(row=0, column=0, sticky="w", padx=4, pady=(6, 8))

        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 8))
        self.stats_total_label = ctk.CTkLabel(top, text="", font=ctk.CTkFont(size=16, weight="bold"))
        self.stats_total_label.pack(side="left")
        ctk.CTkButton(top, text="Refresh", command=self._refresh_stats, width=90).pack(side="right")

        cols = ctk.CTkFrame(parent, fg_color="transparent")
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

        self._refresh_stats()

    def _on_tab_changed(self):
        try:
            current = self.tabs.get()
        except Exception:
            return
        if current == "📊  Stats":
            self._refresh_stats()
        elif current == "🔍  Browse & Edit":
            self._refresh_browse_list()

    def _refresh_stats(self):
        for frame in (self.stats_type_frame, self.stats_category_frame):
            for widget in list(frame.winfo_children())[1:]:  # keep the heading label
                widget.destroy()

        total = dataset.total_count()
        self.stats_total_label.configure(text=f"📦  Total entries: {total}")

        self._render_bar_group(self.stats_type_frame, dataset.count_by("entry_type"), total, ACCENT_GREEN)
        self._render_bar_group(self.stats_category_frame, dataset.count_by("category"), total, None)

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


if __name__ == "__main__":
    app = App()
    app.mainloop()