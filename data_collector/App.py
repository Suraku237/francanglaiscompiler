"""
Francanglais Dataset Collector
--------------------------------
A desktop GUI (CustomTkinter) for collecting a Francanglais dataset:
words, phrases and sentences, each with French/English glosses,
a category, optional notes, and optional audio (recorded live or
attached from an existing file).

Three tabs:
  - Collect        : add new entries (with duplicate warning + recent list)
  - Browse & Edit   : search, edit, delete, and play back existing entries
  - Stats           : counts by category and by type

Run:
    pip install -r ../requirements.txt
    python app.py
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


def style_treeview_dark():
    """Make the ttk.Treeview (used in Browse & Edit) match the dark theme."""
    style = ttk.Style()
    style.theme_use("default")
    style.configure(
        "Treeview",
        background="#2b2b2b", foreground="white",
        fieldbackground="#2b2b2b", rowheight=26, borderwidth=0,
    )
    style.map("Treeview", background=[("selected", "#1f6aa5")])
    style.configure(
        "Treeview.Heading",
        background="#1f1f1f", foreground="white", borderwidth=0,
    )


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Francanglais Dataset Collector")
        self.geometry("880x720")
        self.minsize(760, 620)

        dataset.ensure_dataset_file()
        style_treeview_dark()

        self.pending_audio_path = None      # filename staged for the new entry (Collect tab)
        self.selected_browse_id = None       # id of the entry currently loaded in Browse & Edit
        self.selected_browse_audio = None    # audio filename of the selected browse entry
        self.recorder = audio_utils.Recorder() if audio_utils.AUDIO_RECORDING_AVAILABLE else None
        self._dup_check_job = None

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=12)
        self.tabs.add("Collect")
        self.tabs.add("Browse & Edit")
        self.tabs.add("Stats")

        self._build_collect_tab(self.tabs.tab("Collect"))
        self._build_browse_tab(self.tabs.tab("Browse & Edit"))
        self._build_stats_tab(self.tabs.tab("Stats"))

        # Keyboard shortcuts (active anywhere in the window)
        self.bind("<Control-Return>", lambda e: self.save_entry())
        self.bind("<Escape>", lambda e: self.clear_form(keep_contributor=True))

        self._refresh_recent()
        self._refresh_count()

    # ==================================================================
    # COLLECT TAB
    # ==================================================================
    def _build_collect_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        self.count_label = ctk.CTkLabel(parent, text="", text_color="gray70")
        self.count_label.grid(row=0, column=0, sticky="w", padx=4, pady=(4, 8))

        form = ctk.CTkFrame(parent)
        form.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        form.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(1, weight=0)

        row = 0
        ctk.CTkLabel(form, text="Francanglais text*").grid(
            row=row, column=0, sticky="w", padx=10, pady=(12, 4))
        self.text_entry = ctk.CTkTextbox(form, height=56)
        self.text_entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=10, pady=(12, 4))
        self.text_entry.bind("<KeyRelease>", self._on_text_change)
        row += 1

        self.dup_warning_label = ctk.CTkLabel(
            form, text="", text_color="#E0A93B", font=ctk.CTkFont(size=12))
        self.dup_warning_label.grid(row=row, column=1, columnspan=2, sticky="w", padx=10)
        row += 1

        ctk.CTkLabel(form, text="Type").grid(row=row, column=0, sticky="w", padx=10, pady=4)
        self.type_menu = ctk.CTkOptionMenu(form, values=dataset.ENTRY_TYPES)
        self.type_menu.grid(row=row, column=1, sticky="w", padx=10, pady=4)
        row += 1

        ctk.CTkLabel(form, text="French gloss").grid(row=row, column=0, sticky="w", padx=10, pady=4)
        self.fr_entry = ctk.CTkEntry(form, placeholder_text="Meaning in standard French")
        self.fr_entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=10, pady=4)
        row += 1

        ctk.CTkLabel(form, text="English gloss").grid(row=row, column=0, sticky="w", padx=10, pady=4)
        self.en_entry = ctk.CTkEntry(form, placeholder_text="Meaning in standard English")
        self.en_entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=10, pady=4)
        row += 1

        ctk.CTkLabel(form, text="Category").grid(row=row, column=0, sticky="w", padx=10, pady=4)
        self.category_menu = ctk.CTkOptionMenu(form, values=dataset.CATEGORIES)
        self.category_menu.grid(row=row, column=1, sticky="w", padx=10, pady=4)
        row += 1

        ctk.CTkLabel(form, text="Notes").grid(row=row, column=0, sticky="w", padx=10, pady=4)
        self.notes_entry = ctk.CTkEntry(form, placeholder_text="Optional: context, region, usage note")
        self.notes_entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=10, pady=4)
        row += 1

        ctk.CTkLabel(form, text="Contributor").grid(row=row, column=0, sticky="w", padx=10, pady=4)
        self.contributor_entry = ctk.CTkEntry(form, placeholder_text="Your name / initials")
        self.contributor_entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=10, pady=4)
        row += 1

        ctk.CTkLabel(form, text="Audio").grid(row=row, column=0, sticky="w", padx=10, pady=4)
        audio_frame = ctk.CTkFrame(form, fg_color="transparent")
        audio_frame.grid(row=row, column=1, columnspan=2, sticky="ew", padx=10, pady=4)

        self.record_btn = ctk.CTkButton(
            audio_frame, text="● Record", command=self.toggle_recording,
            fg_color="#8B2E2E" if audio_utils.AUDIO_RECORDING_AVAILABLE else "gray40",
            state="normal" if audio_utils.AUDIO_RECORDING_AVAILABLE else "disabled",
            width=110,
        )
        self.record_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(audio_frame, text="Attach file...", command=self.attach_audio_file,
                      width=120).pack(side="left", padx=(0, 8))

        self.play_pending_btn = ctk.CTkButton(
            audio_frame, text="▶ Play", command=self.play_pending_audio,
            width=80, state="disabled")
        self.play_pending_btn.pack(side="left", padx=(0, 8))

        self.audio_status_label = ctk.CTkLabel(audio_frame, text="No audio attached", text_color="gray70")
        self.audio_status_label.pack(side="left", padx=(8, 0))
        row += 1

        if not audio_utils.AUDIO_RECORDING_AVAILABLE:
            ctk.CTkLabel(
                form,
                text="(Live recording needs 'sounddevice' + a working mic backend — "
                     "install requirements.txt, or just attach an audio file instead.)",
                text_color="gray60", font=ctk.CTkFont(size=11),
            ).grid(row=row, column=1, columnspan=2, sticky="w", padx=10)
            row += 1

        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.grid(row=2, column=0, sticky="ew", padx=4, pady=(8, 4))
        btn_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            btn_frame, text="Save entry  (Ctrl+Enter)", command=self.save_entry,
            height=40, font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            btn_frame, text="Clear (Esc)", command=lambda: self.clear_form(),
            fg_color="gray30", hover_color="gray20", height=40, width=110,
        ).grid(row=0, column=1)

        self.status_label = ctk.CTkLabel(parent, text="", text_color="#4CAF50")
        self.status_label.grid(row=3, column=0, sticky="w", padx=4, pady=(4, 8))

        ctk.CTkLabel(parent, text="Recently added", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=4, column=0, sticky="w", padx=4, pady=(4, 0))
        self.recent_frame = ctk.CTkScrollableFrame(parent, height=140)
        self.recent_frame.grid(row=5, column=0, sticky="nsew", padx=4, pady=(4, 4))
        parent.grid_rowconfigure(5, weight=1)

    def _on_text_change(self, event=None):
        if self._dup_check_job is not None:
            self.after_cancel(self._dup_check_job)
        self._dup_check_job = self.after(400, self._check_duplicate)

    def _check_duplicate(self):
        text = self.text_entry.get("1.0", "end").strip()
        if text and dataset.text_exists(text):
            self.dup_warning_label.configure(text="⚠ This text already exists in the dataset")
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
            self.record_btn.configure(text="● Record", fg_color="#8B2E2E")
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
            "notes": self.notes_entry.get().strip(),
            "audio_filename": self.pending_audio_path or "",
            "contributor": self.contributor_entry.get().strip(),
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        dataset.append_entry(entry)

        self.status_label.configure(text=f'Saved: "{text[:40]}"')
        self._refresh_count()
        self._refresh_recent()
        self.clear_form(keep_contributor=True)

    def clear_form(self, keep_contributor=False):
        self.text_entry.delete("1.0", "end")
        self.fr_entry.delete(0, "end")
        self.en_entry.delete(0, "end")
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
        self.count_label.configure(text=f"{n} entries saved to dataset.csv")

    def _refresh_recent(self):
        for widget in self.recent_frame.winfo_children():
            widget.destroy()
        entries = dataset.load_all()[-6:]
        entries.reverse()
        if not entries:
            ctk.CTkLabel(self.recent_frame, text="No entries yet.", text_color="gray60").pack(
                anchor="w", padx=6, pady=4)
            return
        for e in entries:
            audio_tag = " 🔊" if e.get("audio_filename") else ""
            line = f'[{e.get("entry_type","")}] {e.get("text","")}{audio_tag}'
            ctk.CTkLabel(self.recent_frame, text=line, anchor="w").pack(fill="x", padx=6, pady=2)

    # ==================================================================
    # BROWSE & EDIT TAB
    # ==================================================================
    def _build_browse_tab(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 8))
        top.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(top, placeholder_text="Search by text, category, or contributor...")
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", lambda e: self._refresh_browse_list())

        ctk.CTkButton(top, text="Refresh", command=self._refresh_browse_list, width=90).grid(row=0, column=1)

        columns = ("text", "type", "category", "contributor", "audio")
        self.tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("text", text="Text")
        self.tree.heading("type", text="Type")
        self.tree.heading("category", text="Category")
        self.tree.heading("contributor", text="Contributor")
        self.tree.heading("audio", text="Audio")
        self.tree.column("text", width=260)
        self.tree.column("type", width=80, anchor="center")
        self.tree.column("category", width=120)
        self.tree.column("contributor", width=100)
        self.tree.column("audio", width=60, anchor="center")
        self.tree.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self.tree.bind("<<TreeviewSelect>>", self._on_browse_select)

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=4)

        # --- edit panel ---
        edit = ctk.CTkFrame(parent)
        edit.grid(row=2, column=0, columnspan=2, sticky="ew", padx=4, pady=(8, 4))
        edit.grid_columnconfigure(1, weight=1)
        edit.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(edit, text="Selected entry", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(10, 6))

        ctk.CTkLabel(edit, text="Text").grid(row=1, column=0, sticky="w", padx=10, pady=4)
        self.edit_text = ctk.CTkEntry(edit)
        self.edit_text.grid(row=1, column=1, columnspan=3, sticky="ew", padx=10, pady=4)

        ctk.CTkLabel(edit, text="Type").grid(row=2, column=0, sticky="w", padx=10, pady=4)
        self.edit_type = ctk.CTkOptionMenu(edit, values=dataset.ENTRY_TYPES)
        self.edit_type.grid(row=2, column=1, sticky="w", padx=10, pady=4)

        ctk.CTkLabel(edit, text="Category").grid(row=2, column=2, sticky="w", padx=10, pady=4)
        self.edit_category = ctk.CTkOptionMenu(edit, values=dataset.CATEGORIES)
        self.edit_category.grid(row=2, column=3, sticky="w", padx=10, pady=4)

        ctk.CTkLabel(edit, text="French gloss").grid(row=3, column=0, sticky="w", padx=10, pady=4)
        self.edit_fr = ctk.CTkEntry(edit)
        self.edit_fr.grid(row=3, column=1, sticky="ew", padx=10, pady=4)

        ctk.CTkLabel(edit, text="English gloss").grid(row=3, column=2, sticky="w", padx=10, pady=4)
        self.edit_en = ctk.CTkEntry(edit)
        self.edit_en.grid(row=3, column=3, sticky="ew", padx=10, pady=4)

        ctk.CTkLabel(edit, text="Notes").grid(row=4, column=0, sticky="w", padx=10, pady=4)
        self.edit_notes = ctk.CTkEntry(edit)
        self.edit_notes.grid(row=4, column=1, columnspan=3, sticky="ew", padx=10, pady=4)

        action_row = ctk.CTkFrame(edit, fg_color="transparent")
        action_row.grid(row=5, column=0, columnspan=4, sticky="ew", padx=10, pady=(8, 10))

        self.edit_play_btn = ctk.CTkButton(action_row, text="▶ Play audio", command=self._play_selected_audio,
                                            width=110, state="disabled")
        self.edit_play_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(action_row, text="Save changes", command=self._save_browse_edit,
                      width=130).pack(side="left", padx=(0, 8))

        ctk.CTkButton(action_row, text="Delete entry", command=self._delete_browse_entry,
                      fg_color="#8B2E2E", hover_color="#6E2424", width=110).pack(side="left")

        self.browse_status_label = ctk.CTkLabel(edit, text="Select a row above to edit it.", text_color="gray60")
        self.browse_status_label.grid(row=6, column=0, columnspan=4, sticky="w", padx=10, pady=(0, 8))

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
            "notes": self.edit_notes.get().strip(),
        }
        dataset.update_entry(self.selected_browse_id, updated)
        self.browse_status_label.configure(text="Changes saved.")
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

        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 8))
        self.stats_total_label = ctk.CTkLabel(top, text="", font=ctk.CTkFont(size=15, weight="bold"))
        self.stats_total_label.pack(side="left")
        ctk.CTkButton(top, text="Refresh", command=self._refresh_stats, width=90).pack(side="right")

        cols = ctk.CTkFrame(parent, fg_color="transparent")
        cols.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        cols.grid_columnconfigure(0, weight=1)
        cols.grid_columnconfigure(1, weight=1)

        self.stats_type_frame = ctk.CTkFrame(cols)
        self.stats_type_frame.grid(row=0, column=0, sticky="new", padx=(0, 8))
        ctk.CTkLabel(self.stats_type_frame, text="By type", font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 6))

        self.stats_category_frame = ctk.CTkFrame(cols)
        self.stats_category_frame.grid(row=0, column=1, sticky="new", padx=(8, 0))
        ctk.CTkLabel(self.stats_category_frame, text="By category", font=ctk.CTkFont(size=13, weight="bold")).pack(
            anchor="w", padx=10, pady=(10, 6))

        # Recompute stats every time this tab is shown.
        self.bind("<<TabChanged>>", lambda e: self._maybe_refresh_stats(), add="+")
        self._refresh_stats()

    def _maybe_refresh_stats(self):
        try:
            if self.tabs.get() == "Stats":
                self._refresh_stats()
        except Exception:
            pass

    def _refresh_stats(self):
        for frame in (self.stats_type_frame, self.stats_category_frame):
            for widget in list(frame.winfo_children())[1:]:  # keep the heading label
                widget.destroy()

        total = dataset.total_count()
        self.stats_total_label.configure(text=f"Total entries: {total}")

        self._render_bar_group(self.stats_type_frame, dataset.count_by("entry_type"), total)
        self._render_bar_group(self.stats_category_frame, dataset.count_by("category"), total)

    def _render_bar_group(self, frame, counts: dict, total: int):
        if not counts:
            ctk.CTkLabel(frame, text="No data yet.", text_color="gray60").pack(anchor="w", padx=10, pady=(0, 10))
            return
        for key, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=3)
            ctk.CTkLabel(row, text=f"{key} ({count})", width=150, anchor="w").pack(side="left")
            bar = ctk.CTkProgressBar(row)
            bar.pack(side="left", fill="x", expand=True, padx=(6, 0))
            bar.set(count / total if total else 0)
        ctk.CTkLabel(frame, text="").pack(pady=2)  # bottom spacing


if __name__ == "__main__":
    app = App()
    app.mainloop()