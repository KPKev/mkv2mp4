import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import subprocess
import threading
import os
import sys
import re  # For parsing ffmpeg output
import time
import psutil  # For process pause/resume
import signal  # For POSIX signals (fallback or direct use)


class ConverterApp:
    def __init__(self, master):
        self.master = master
        master.title("MKV2MP4 Converter (Batch)")
        master.geometry(
            "600x750"
        )  # Adjusted window size for new buttons + individual progress

        self.file_queue = []
        self.failed_files_data = []  # Stores (file_path, error_reason_string)
        self.files_for_retry_level_1 = set()  # Renamed from files_for_recovery_mode
        self.files_for_retry_level_2 = set()  # For the second, more lax retry attempt
        self.output_format = tk.StringVar(value="MP4 (H.264 + AAC)")
        self.conversion_status = tk.StringVar(
            value="Status: Idle. Add files to the queue."
        )
        self.individual_progress_status = tk.StringVar(
            value="Individual File Progress: N/A"
        )  # For text next to bar
        self.ffmpeg_exec_path = None
        self.is_converting = False
        self.current_ffmpeg_process = None  # To store the Popen object of ffmpeg
        self.psutil_process = (
            None  # To store the psutil.Process object for suspend/resume
        )
        self.is_paused = False  # To track pause state
        self.cancel_requested = False  # To signal cancellation of the batch
        self.conversion_thread = None  # To store the conversion thread object

        # --- UI Elements ---
        current_row = 0
        # File Queue Management Frame
        queue_frame = tk.LabelFrame(master, text="Conversion Queue", padx=5, pady=5)
        queue_frame.grid(
            row=current_row, column=0, columnspan=4, padx=10, pady=10, sticky="ewns"
        )
        master.grid_rowconfigure(current_row, weight=1)
        master.grid_columnconfigure(0, weight=1)
        current_row += 1

        self.queue_listbox = tk.Listbox(
            queue_frame, width=80, height=7, selectmode=tk.SINGLE
        )  # Adjusted height
        self.queue_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        queue_scrollbar = tk.Scrollbar(
            queue_frame, orient="vertical", command=self.queue_listbox.yview
        )
        queue_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.queue_listbox.config(yscrollcommand=queue_scrollbar.set)

        # Buttons for Queue Management Frame
        button_frame = tk.Frame(master)
        button_frame.grid(
            row=current_row, column=0, columnspan=4, padx=10, pady=5, sticky="ew"
        )
        current_row += 1
        self.add_files_button = tk.Button(
            button_frame, text="Add MKV Files...", command=self.add_files_to_queue
        )
        self.add_files_button.pack(side=tk.LEFT, padx=5)
        self.remove_selected_button = tk.Button(
            button_frame,
            text="Remove Selected",
            command=self.remove_selected_from_queue,
        )
        self.remove_selected_button.pack(side=tk.LEFT, padx=5)
        self.clear_queue_button = tk.Button(
            button_frame, text="Clear Queue", command=self.clear_queue
        )
        self.clear_queue_button.pack(side=tk.LEFT, padx=5)

        # Failed Files Frame
        failed_frame = tk.LabelFrame(master, text="Failed Conversions", padx=5, pady=5)
        failed_frame.grid(
            row=current_row, column=0, columnspan=4, padx=10, pady=5, sticky="ewns"
        )
        master.grid_rowconfigure(current_row, weight=1)
        current_row += 1

        self.failed_listbox = tk.Listbox(
            failed_frame, width=80, height=4, selectmode=tk.SINGLE, bg="#ffe0e0"
        )  # Adjusted height
        self.failed_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        failed_scrollbar = tk.Scrollbar(
            failed_frame, orient="vertical", command=self.failed_listbox.yview
        )
        failed_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.failed_listbox.config(yscrollcommand=failed_scrollbar.set)

        # Buttons for Failed Files Frame
        failed_button_frame = tk.Frame(master)
        failed_button_frame.grid(
            row=current_row, column=0, columnspan=4, padx=10, pady=5, sticky="ew"
        )
        current_row += 1
        self.retry_failed_button = tk.Button(
            failed_button_frame,
            text="Retry Failed Files",
            command=self.retry_failed_files,
        )
        self.retry_failed_button.pack(side=tk.LEFT, padx=5)
        self.retry_level_1_button = tk.Button(
            failed_button_frame,
            text="Retry Failed (Level 1)",
            command=self.retry_failed_level_1,
        )
        self.retry_level_1_button.pack(side=tk.LEFT, padx=5)
        self.retry_level_2_button = tk.Button(
            failed_button_frame,
            text="Retry Failed (Level 2)",
            command=self.retry_failed_level_2,
        )
        self.retry_level_2_button.pack(side=tk.LEFT, padx=5)
        self.clear_failed_button = tk.Button(
            failed_button_frame,
            text="Clear Failed List",
            command=self.clear_failed_list,
        )
        self.clear_failed_button.pack(side=tk.LEFT, padx=5)

        # Output Format Selection
        format_frame = tk.Frame(master)
        format_frame.grid(
            row=current_row, column=0, columnspan=4, padx=10, pady=10, sticky="ew"
        )
        current_row += 1
        tk.Label(format_frame, text="Output Format:").pack(side=tk.LEFT, padx=5)
        self.format_options = ["MP4 (H.264 + AAC)"]  # Only MP4
        self.format_dropdown = ttk.Combobox(
            format_frame,
            textvariable=self.output_format,
            values=self.format_options,
            state="readonly",
            width=25,
        )
        self.format_dropdown.pack(side=tk.LEFT, padx=5)
        if len(self.format_options) == 1:  # If only one option, disable the dropdown
            self.output_format.set(self.format_options[0])
            self.format_dropdown.config(state=tk.DISABLED)

        # Action Buttons Frame (Start, Pause, Cancel)
        action_frame = tk.Frame(master)
        action_frame.grid(
            row=current_row, column=0, columnspan=4, padx=10, pady=10, sticky="ew"
        )

        self.convert_button = tk.Button(
            action_frame,
            text="Start Batch Convert",
            command=self.start_conversion_thread,
            height=2,
        )
        self.convert_button.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True)
        self.convert_button.config(state=tk.DISABLED)

        self.pause_resume_button = tk.Button(
            action_frame, text="Pause", command=self.toggle_pause_resume, height=2
        )
        self.pause_resume_button.pack(
            side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True
        )
        self.pause_resume_button.config(state=tk.DISABLED)

        self.cancel_button = tk.Button(
            action_frame,
            text="Cancel Batch",
            command=self.cancel_batch_conversion,
            height=2,
            bg="#ffdddd",
        )
        self.cancel_button.pack(side=tk.LEFT, padx=5, pady=5, fill=tk.X, expand=True)
        self.cancel_button.config(state=tk.DISABLED)
        current_row += 1

        # Overall Progress Bar
        overall_progress_frame = tk.Frame(master)
        overall_progress_frame.grid(
            row=current_row, column=0, columnspan=4, padx=10, pady=5, sticky="ew"
        )
        current_row += 1
        tk.Label(overall_progress_frame, text="Overall Batch Progress:").pack(
            side=tk.LEFT, padx=5
        )
        self.overall_progress_bar = ttk.Progressbar(
            overall_progress_frame, orient="horizontal", length=400, mode="determinate"
        )
        self.overall_progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Individual File Progress Bar
        individual_progress_frame = tk.Frame(master)
        individual_progress_frame.grid(
            row=current_row, column=0, columnspan=4, padx=10, pady=5, sticky="ew"
        )
        current_row += 1
        self.individual_progress_label = tk.Label(
            individual_progress_frame, textvariable=self.individual_progress_status
        )
        self.individual_progress_label.pack(side=tk.LEFT, padx=5)
        self.individual_progress_bar = ttk.Progressbar(
            individual_progress_frame,
            orient="horizontal",
            length=400,
            mode="determinate",
        )
        self.individual_progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Status Label
        self.status_label = tk.Label(
            master, textvariable=self.conversion_status, relief=tk.SUNKEN, anchor="w"
        )
        self.status_label.grid(
            row=current_row, column=0, columnspan=4, padx=10, pady=10, sticky="ew"
        )
        current_row += 1

        # Bind window close event
        master.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Initial FFmpeg check
        if not self.check_ffmpeg():
            self.master.after(
                100,
                lambda: messagebox.showwarning(
                    "FFmpeg Not Found",
                    "FFmpeg was not found in the local 'ffmpeg' subdirectory or in the system PATH. "
                    "Please place FFmpeg in the 'ffmpeg' folder next to the script, or ensure it's in your PATH.",
                ),
            )
            self.conversion_status.set(
                "Status: FFmpeg not found! Add FFmpeg to continue."
            )
        else:
            self.update_status_on_ffmpeg_ready()
        self.update_status_with_queue_count()  # Ensure buttons are correctly set initially

    def update_status_on_ffmpeg_ready(self):
        if self.ffmpeg_exec_path == "ffmpeg":
            self.conversion_status.set(
                "Status: Idle (FFmpeg in PATH). Add files to queue."
            )
        else:
            self.conversion_status.set(
                f"Status: Idle (FFmpeg at {os.path.basename(self.ffmpeg_exec_path)}). Add files to queue."
            )

    def add_files_to_queue(self):
        if self.is_converting:
            return
        file_paths = filedialog.askopenfilenames(
            title="Select MKV Files",
            filetypes=(("MKV files", "*.mkv"), ("All files", "*.*")),
        )
        added_count = 0
        if file_paths:
            for file_path in file_paths:
                if file_path not in self.file_queue and not any(
                    fp == file_path for fp, _ in self.failed_files_data
                ):
                    self.file_queue.append(file_path)
                    self.queue_listbox.insert(tk.END, os.path.basename(file_path))
                    added_count += 1
            if added_count > 0:
                self.update_status_with_queue_count()
            elif file_paths:  # Only show if files were selected but none were new
                messagebox.showinfo(
                    "No New Files",
                    "Selected file(s) are already in the queue or failed list.",
                )

    def remove_selected_from_queue(self):
        if self.is_converting:
            return
        selected_indices = self.queue_listbox.curselection()
        if selected_indices:
            selected_index = selected_indices[0]
            del self.file_queue[selected_index]
            self.queue_listbox.delete(selected_index)
            self.update_status_with_queue_count()
        else:
            messagebox.showinfo(
                "No Selection", "Please select a file from the main queue to remove."
            )

    def clear_queue(self):
        if self.is_converting:
            return
        self.file_queue.clear()
        self.queue_listbox.delete(0, tk.END)
        self.update_status_with_queue_count()

    def retry_failed_files(self):
        if self.is_converting:
            return
        if not self.failed_files_data:
            messagebox.showinfo(
                "No Failed Files", "There are no files in the failed list to retry."
            )
            return

        num_retried = 0
        for file_path, _ in list(
            self.failed_files_data
        ):  # Iterate a copy for safe modification
            if file_path not in self.file_queue:
                self.file_queue.append(file_path)
                self.queue_listbox.insert(tk.END, os.path.basename(file_path))
                # Remove from failed_files_data by finding its index or recreating the list
                self.failed_files_data = [
                    (fp, err) for fp, err in self.failed_files_data if fp != file_path
                ]
                num_retried += 1
            else:  # If somehow already back in queue, just remove from failed
                self.failed_files_data = [
                    (fp, err) for fp, err in self.failed_files_data if fp != file_path
                ]

        self.failed_listbox.delete(0, tk.END)  # Clear and re-populate is easier
        for (
            fp,
            _,
        ) in (
            self.failed_files_data
        ):  # Re-populate with any that weren't retried (e.g. duplicates)
            self.failed_listbox.insert(tk.END, os.path.basename(fp))

        if num_retried > 0:
            self.update_status_with_queue_count()
            self.conversion_status.set(
                f"Status: Moved {num_retried} file(s) from failed to queue. Ready to convert."
            )
        else:
            self.conversion_status.set(
                "Status: No files moved from failed to queue (possibly already present)."
            )
        self.update_status_with_queue_count()  # Update button states

    def retry_failed_level_1(self):
        if self.is_converting:
            return
        if not self.failed_files_data:
            messagebox.showinfo(
                "No Failed Files",
                "There are no files in the failed list to retry with level 1.",
            )
            return

        num_retried_level_1 = 0
        for file_path, _ in list(
            self.failed_files_data
        ):  # Iterate a copy for safe modification
            if file_path not in self.file_queue:
                self.file_queue.append(file_path)
                self.queue_listbox.insert(
                    tk.END, os.path.basename(file_path) + " (Level 1)"
                )  # Mark in listbox
                self.files_for_retry_level_1.add(file_path)  # Add to level 1 set
                # Remove from failed_files_data
                self.failed_files_data = [
                    (fp, err) for fp, err in self.failed_files_data if fp != file_path
                ]
                num_retried_level_1 += 1
            else:  # If somehow already back in queue, just remove from failed and mark for level 1
                self.files_for_retry_level_1.add(file_path)
                # Update listbox entry if possible to show (Level 1) - complex, skip for now or re-add
                self.failed_files_data = [
                    (fp, err) for fp, err in self.failed_files_data if fp != file_path
                ]

        self.failed_listbox.delete(0, tk.END)  # Clear and re-populate is easier
        for (
            fp,
            _,
        ) in self.failed_files_data:  # Re-populate with any that weren't retried
            self.failed_listbox.insert(tk.END, os.path.basename(fp))

        if num_retried_level_1 > 0:
            self.update_status_with_queue_count()
            self.conversion_status.set(
                f"Status: Moved {num_retried_level_1} file(s) to queue for level 1 retry. Ready to convert."
            )
        else:
            self.conversion_status.set(
                "Status: No files moved for level 1 retry (possibly already in queue)."
            )
        self.update_status_with_queue_count()  # Update button states

    def retry_failed_level_2(self):
        if self.is_converting:
            return
        if not self.failed_files_data:
            messagebox.showinfo(
                "No Failed Files",
                "There are no files in the failed list to retry with level 2.",
            )
            return

        num_retried_level_2 = 0
        for file_path, _ in list(
            self.failed_files_data
        ):  # Iterate a copy for safe modification
            if file_path not in self.file_queue:
                self.file_queue.append(file_path)
                self.queue_listbox.insert(
                    tk.END, os.path.basename(file_path) + " (Level 2)"
                )  # Mark in listbox
                self.files_for_retry_level_2.add(file_path)  # Add to level 2 set
                # Remove from failed_files_data
                self.failed_files_data = [
                    (fp, err) for fp, err in self.failed_files_data if fp != file_path
                ]
                num_retried_level_2 += 1
            else:  # If somehow already back in queue, just remove from failed and mark for level 2
                self.files_for_retry_level_2.add(file_path)
                # Update listbox entry if possible to show (Level 2) - complex, skip for now or re-add
                self.failed_files_data = [
                    (fp, err) for fp, err in self.failed_files_data if fp != file_path
                ]

        self.failed_listbox.delete(0, tk.END)  # Clear and re-populate is easier
        for (
            fp,
            _,
        ) in self.failed_files_data:  # Re-populate with any that weren't retried
            self.failed_listbox.insert(tk.END, os.path.basename(fp))

        if num_retried_level_2 > 0:
            self.update_status_with_queue_count()
            self.conversion_status.set(
                f"Status: Moved {num_retried_level_2} file(s) to queue for level 2 retry. Ready to convert."
            )
        else:
            self.conversion_status.set(
                "Status: No files moved for level 2 retry (possibly already in queue)."
            )
        self.update_status_with_queue_count()  # Update button states

    def clear_failed_list(self):
        if self.is_converting:
            return
        self.failed_files_data.clear()
        self.failed_listbox.delete(0, tk.END)
        self.conversion_status.set("Status: Failed conversion list cleared.")
        self.update_status_with_queue_count()

    def update_status_with_queue_count(self):
        queue_count = len(self.file_queue)
        base_status_parts = self.conversion_status.get().split(" | ")
        current_ffmpeg_status = base_status_parts[0]

        if self.is_converting:
            self.conversion_status.set(
                f"{current_ffmpeg_status} | Files remaining in queue: {queue_count}"
            )
            self.individual_progress_status.set(
                f"Individual File Progress: Processing..."
            )
            # UI state for buttons is handled by toggle_ui_state(False)
        else:
            self.conversion_status.set(
                f"{current_ffmpeg_status} | Queue: {queue_count} file(s)."
            )
            self.individual_progress_bar["value"] = 0
            self.individual_progress_status.set(f"Individual File Progress: N/A")
            # UI state for buttons is handled by toggle_ui_state(True)
            # Call toggle_ui_state to ensure buttons reflect current state (e.g. Convert button if queue populated)
            self.toggle_ui_state(True)

        # This part of toggle_ui_state might be redundant if called above, but good for clarity
        # if not self.is_converting and self.failed_files_data:
        #     self.retry_failed_button.config(state=tk.NORMAL)
        #     self.clear_failed_button.config(state=tk.NORMAL)
        # else:
        #     self.retry_failed_button.config(state=tk.DISABLED)
        #     self.clear_failed_button.config(state=tk.DISABLED)

    def get_ffmpeg_path(self):
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            application_path = sys._MEIPASS
        else:
            application_path = os.path.dirname(os.path.abspath(__file__))
        local_ffmpeg_dir = os.path.join(application_path, "ffmpeg")
        if os.name == "nt":
            ffmpeg_exe = os.path.join(local_ffmpeg_dir, "bin", "ffmpeg.exe")
            if not os.path.exists(ffmpeg_exe):
                ffmpeg_exe = os.path.join(local_ffmpeg_dir, "ffmpeg.exe")
        else:
            ffmpeg_exe = os.path.join(local_ffmpeg_dir, "ffmpeg")
            if not os.path.exists(ffmpeg_exe):
                ffmpeg_exe_alt = os.path.join(local_ffmpeg_dir, "bin", "ffmpeg")
                if os.path.exists(ffmpeg_exe_alt):
                    ffmpeg_exe = ffmpeg_exe_alt
        if os.path.exists(ffmpeg_exe) and os.access(ffmpeg_exe, os.X_OK):
            return ffmpeg_exe
        return "ffmpeg"

    def check_ffmpeg(self):
        self.ffmpeg_exec_path = self.get_ffmpeg_path()
        try:
            cmd_to_run = [self.ffmpeg_exec_path, "-version"]
            subprocess.run(
                cmd_to_run,
                check=True,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.ffmpeg_exec_path = None
            return False

    def start_conversion_thread(self):
        if self.is_converting:
            messagebox.showwarning("Busy", "A conversion process is already running.")
            return
        if not self.file_queue:
            messagebox.showerror(
                "Error", "The conversion queue is empty. Please add MKV files."
            )
            return
        if not self.ffmpeg_exec_path:
            messagebox.showerror(
                "FFmpeg Error", "FFmpeg not found. Please check setup."
            )
            self.conversion_status.set("Status: FFmpeg not found!")
            return

        self.is_converting = True
        self.cancel_requested = False  # Reset cancel flag
        self.is_paused = False  # Reset pause flag
        self.toggle_ui_state(False)
        self.overall_progress_bar["value"] = 0
        self.individual_progress_bar["value"] = 0
        self.conversion_status.set("Status: Starting batch conversion...")
        self.conversion_thread = threading.Thread(target=self.process_batch)
        self.conversion_thread.daemon = True
        self.conversion_thread.start()

    def toggle_ui_state(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.add_files_button.config(state=state)
        self.remove_selected_button.config(state=state)
        self.clear_queue_button.config(state=state)
        self.format_dropdown.config(state="readonly" if enabled else tk.DISABLED)
        # self.convert_button.config(state=state) # Handled separately based on queue and conversion state

        if enabled:  # Not converting
            self.convert_button.config(
                state=tk.NORMAL
                if self.file_queue and self.ffmpeg_exec_path
                else tk.DISABLED
            )
            self.pause_resume_button.config(state=tk.DISABLED, text="Pause")
            self.cancel_button.config(state=tk.DISABLED)
            if not self.failed_files_data:
                self.retry_failed_button.config(state=tk.DISABLED)
                self.retry_level_1_button.config(state=tk.DISABLED)
                self.retry_level_2_button.config(state=tk.DISABLED)
                self.clear_failed_button.config(state=tk.DISABLED)
            else:
                self.retry_failed_button.config(state=tk.NORMAL)
                self.retry_level_1_button.config(state=tk.NORMAL)
                self.retry_level_2_button.config(state=tk.NORMAL)
                self.clear_failed_button.config(state=tk.NORMAL)
            self.individual_progress_bar["value"] = 0
            self.individual_progress_status.set("Individual File Progress: N/A")
        else:  # Is converting
            self.convert_button.config(state=tk.DISABLED)
            self.pause_resume_button.config(
                state=tk.NORMAL, text="Pause" if not self.is_paused else "Resume"
            )
            self.cancel_button.config(state=tk.NORMAL)
            self.retry_failed_button.config(state=tk.DISABLED)
            self.retry_level_1_button.config(state=tk.DISABLED)
            self.retry_level_2_button.config(state=tk.DISABLED)
            self.clear_failed_button.config(state=tk.DISABLED)

    def process_batch(self):
        total_files_in_batch = len(self.file_queue)
        files_processed_in_batch = 0
        initial_failed_count = len(self.failed_files_data)
        current_batch_paths = list(self.file_queue)

        for file_index, current_file_path in enumerate(current_batch_paths):
            if (
                self.cancel_requested
            ):  # Check for cancellation at the start of each file
                self.master.after(
                    0,
                    lambda: self.conversion_status.set(
                        "Status: Batch cancelled by user."
                    ),
                )
                break
            if (
                not self.is_converting
            ):  # Should not happen if cancel_requested is used, but as a safeguard
                break
            if current_file_path not in self.file_queue:
                continue

            current_file_name = os.path.basename(current_file_path)
            self.master.after(0, self.individual_progress_bar.config, {"value": 0})
            self.master.after(
                0,
                self.individual_progress_status.set,
                f"Individual File Progress: Preparing {current_file_name}...",
            )

            retry_level_to_attempt = 0
            display_name_in_queue = current_file_name
            if current_file_path in self.files_for_retry_level_1:
                retry_level_to_attempt = 1
                display_name_in_queue += " (Level 1)"
            elif current_file_path in self.files_for_retry_level_2:
                retry_level_to_attempt = 2
                display_name_in_queue += " (Level 2)"

            try:
                listbox_idx_to_select = -1
                for i in range(self.queue_listbox.size()):
                    entry_text = self.queue_listbox.get(i)
                    matches_basename = os.path.basename(current_file_path) in entry_text
                    is_level_1_entry = "(Level 1)" in entry_text
                    is_level_2_entry = "(Level 2)" in entry_text

                    if matches_basename:
                        if retry_level_to_attempt == 1 and is_level_1_entry:
                            listbox_idx_to_select = i
                            break
                        elif retry_level_to_attempt == 2 and is_level_2_entry:
                            listbox_idx_to_select = i
                            break
                        elif (
                            retry_level_to_attempt == 0
                            and not is_level_1_entry
                            and not is_level_2_entry
                        ):
                            listbox_idx_to_select = i
                            break

                if listbox_idx_to_select != -1:
                    self.master.after(
                        0,
                        lambda i=listbox_idx_to_select: (
                            self.queue_listbox.selection_clear(0, tk.END),
                            self.queue_listbox.selection_set(i),
                            self.queue_listbox.see(i),
                        ),
                    )
            except Exception as e:
                print(f"Error selecting item in queue listbox: {e}")

            self.master.after(
                0,
                lambda cn=display_name_in_queue,
                fp=files_processed_in_batch,
                tb=total_files_in_batch: self.conversion_status.set(
                    f"Status: Converting {cn} ({fp + 1}/{tb})..."
                ),
            )

            conversion_result, error_msg = self.convert_file(
                current_file_path, retry_level=retry_level_to_attempt
            )

            # Clear from retry sets after attempt
            if retry_level_to_attempt == 1:
                self.files_for_retry_level_1.discard(current_file_path)
            elif retry_level_to_attempt == 2:
                self.files_for_retry_level_2.discard(current_file_path)

            if self.cancel_requested:
                self.master.after(
                    0,
                    lambda: self.conversion_status.set(
                        "Status: Batch cancelled during conversion."
                    ),
                )
                break  # Exit the loop immediately

            try:
                actual_index_in_live_queue = self.file_queue.index(current_file_path)
                self.master.after(
                    0,
                    lambda idx=actual_index_in_live_queue: self.queue_listbox.delete(
                        idx
                    ),
                )
                self.file_queue.pop(actual_index_in_live_queue)
            except ValueError:
                print(
                    f"Warning: {current_file_name} not found in live queue for removal after processing."
                )

            if not conversion_result:
                self.master.after(
                    0,
                    lambda path=current_file_path, err=error_msg: (
                        self.failed_files_data.append((path, err)),
                        self.failed_listbox.insert(tk.END, os.path.basename(path)),
                    ),
                )
                # Error message now shown by convert_file's return or here directly
                # self.master.after(0, lambda: messagebox.showerror("Conversion Failed", f"Failed to convert: {current_file_name}. Moved to Failed List. Error: {error_msg}"))

            files_processed_in_batch += 1
            self.master.after(
                0,
                lambda fp=files_processed_in_batch,
                tb=total_files_in_batch: self.overall_progress_bar.config(
                    value=(fp / tb) * 100 if tb > 0 else 0
                ),
            )
            self.master.after(0, self.update_status_with_queue_count)

        self.is_converting = False
        self.current_ffmpeg_process = None  # Clear process reference
        self.master.after(0, lambda: self.toggle_ui_state(True))
        final_failed_count = len(self.failed_files_data)
        newly_failed_count = final_failed_count - initial_failed_count

        if self.cancel_requested:
            summary_message = "Batch conversion cancelled."
            if self.file_queue:
                summary_message += (
                    f"\n{len(self.file_queue)} file(s) remaining in queue."
                )
        else:
            summary_message = f"Batch processing finished.\nSuccessfully converted: {files_processed_in_batch - newly_failed_count}/{total_files_in_batch}\nFailed this run: {newly_failed_count}"
            if self.file_queue:
                summary_message += f"\nRemaining in queue: {len(self.file_queue)}"
            if self.failed_files_data:
                summary_message += (
                    f"\nTotal in failed list: {len(self.failed_files_data)}"
                )

        self.master.after(
            0,
            lambda: self.conversion_status.set("Status: Batch finished. Check summary.")
            if not self.cancel_requested
            else None,
        )
        self.master.after(
            0, lambda: messagebox.showinfo("Batch Status", summary_message)
        )
        self.master.after(0, self.update_status_with_queue_count)
        self.master.after(
            0, self.individual_progress_bar.config, {"value": 0}
        )  # Final reset of individual bar
        self.master.after(
            0, self.individual_progress_status.set, "Individual File Progress: N/A"
        )

    def convert_file(self, input_mkv, retry_level=0):
        """Converts a single file. Returns (True, None) on success, (False, error_message) on failure."""
        if not self.ffmpeg_exec_path:
            return False, "FFmpeg path is not set."
        if self.cancel_requested:  # Check at the very start of conversion attempt
            return False, "Conversion cancelled by user."

        # Step 1: Get video duration using ffprobe (part of FFmpeg)
        duration_seconds = 0
        try:
            ffprobe_cmd = [
                self.ffmpeg_exec_path.replace(
                    "ffmpeg", "ffprobe"
                ),  # Basic replacement, might need smarter logic if paths are complex
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                input_mkv,
            ]
            if os.name == "nt" and not self.ffmpeg_exec_path.endswith(".exe"):
                # if ffmpeg_exec_path is just "ffmpeg" on windows, ffprobe_cmd should be "ffprobe"
                if self.ffmpeg_exec_path == "ffmpeg":
                    ffprobe_cmd[0] = "ffprobe"
                else:
                    ffprobe_cmd[0] = (
                        self.ffmpeg_exec_path.replace("ffmpeg", "ffprobe") + ".exe"
                    )
            elif self.ffmpeg_exec_path.endswith(".exe"):
                ffprobe_cmd[0] = self.ffmpeg_exec_path.replace(
                    "ffmpeg.exe", "ffprobe.exe"
                )

            self.master.after(
                0,
                self.individual_progress_status.set,
                f"Individual File Progress: Getting duration for {os.path.basename(input_mkv)}...",
            )
            duration_process = subprocess.run(
                ffprobe_cmd,
                capture_output=True,
                text=True,
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            duration_seconds = float(duration_process.stdout.strip())
            if duration_seconds <= 0:
                print(
                    f"Warning: Could not determine valid duration for {input_mkv}. Individual progress may be inaccurate."
                )
                duration_seconds = (
                    0  # Will make progress jump to 100 quickly or stay at 0
                )
        except Exception as e:
            print(
                f"Error getting duration for {input_mkv}: {e}. Individual progress may be inaccurate."
            )
            # Proceed without duration, progress will be indeterminate or jumpy for this file
            duration_seconds = 0

        try:
            output_format_selected = self.output_format.get()
            output_file_base = os.path.splitext(input_mkv)[0]
            output_file_path = ""
            ffmpeg_cmd = [self.ffmpeg_exec_path]

            # Input related flags that can help with problematic files (especially for retries)
            if retry_level > 0:
                ffmpeg_cmd.extend(
                    ["-analyzeduration", "20M", "-probesize", "20M"]
                )  # Increased values for retries
            ffmpeg_cmd.extend(["-i", input_mkv])

            file_suffix = "_converted"
            error_prefix = ""
            current_file_label_suffix = ""

            if retry_level == 1:
                file_suffix = "_retry1"
                error_prefix = "(Retry Level 1) "
                current_file_label_suffix = " (Level 1)"
            elif retry_level == 2:
                file_suffix = "_retry2"
                error_prefix = "(Retry Level 2) "
                current_file_label_suffix = " (Level 2)"

            if output_format_selected == "MP4 (H.264 + AAC)":
                output_file_path = f"{output_file_base}{file_suffix}.mp4"
                if retry_level == 1:  # Level 1 Recovery (Balanced)
                    ffmpeg_cmd.extend(
                        [
                            "-c:v",
                            "libx264",
                            "-profile:v",
                            "main",
                            "-preset",
                            "medium",
                            "-crf",
                            "23",
                            "-pix_fmt",
                            "yuv420p",
                            "-c:a",
                            "aac",
                            "-b:a",
                            "128k",
                            "-err_detect",
                            "ignore_err",
                            "-fflags",
                            "+genpts+discardcorrupt",
                            "-y",
                            output_file_path,
                        ]
                    )
                elif retry_level == 2:  # Level 2 Recovery (Lax)
                    ffmpeg_cmd.extend(
                        [
                            "-c:v",
                            "libx264",
                            "-profile:v",
                            "baseline",
                            "-preset",
                            "ultrafast",
                            "-crf",
                            "28",
                            "-pix_fmt",
                            "yuv420p",
                            "-c:a",
                            "aac",
                            "-b:a",
                            "96k",
                            "-err_detect",
                            "ignore_err",
                            "-fflags",
                            "+genpts+discardcorrupt",
                            "-y",
                            output_file_path,
                        ]
                    )
                else:  # Standard (Level 0) MP4 conversion - H.264 High Profile, but not PS5 specific level
                    ffmpeg_cmd.extend(
                        [
                            "-c:v",
                            "libx264",
                            "-profile:v",
                            "high",
                            "-c:a",
                            "aac",
                            "-b:a",
                            "192k",
                            "-y",
                            output_file_path,
                        ]
                    )
            else:
                return (
                    False,
                    f"{error_prefix}Invalid output format selected or no format handler for '{output_format_selected}'.",
                )

            current_file_display_name = (
                os.path.basename(input_mkv) + current_file_label_suffix
            )

            self.master.after(
                0,
                self.individual_progress_status.set,
                f"Individual File Progress: Converting {current_file_display_name}...",
            )
            self.current_ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,  # For sending pause/resume commands
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            time_regex = re.compile(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})")
            error_output_lines = []

            while True:
                if self.cancel_requested:
                    if self.current_ffmpeg_process:
                        try:
                            self.current_ffmpeg_process.terminate()  # Terminate FFmpeg if running
                        except OSError:
                            pass  # Process might have already exited
                        self.current_ffmpeg_process.wait()  # Ensure it's fully terminated
                    self.current_ffmpeg_process = None
                    return False, "Conversion cancelled."

                while self.is_paused:
                    if self.cancel_requested:  # Check cancel during pause
                        if self.current_ffmpeg_process:
                            try:
                                self.current_ffmpeg_process.terminate()
                            except OSError:
                                pass
                            self.current_ffmpeg_process.wait()
                        self.current_ffmpeg_process = None
                        return False, "Conversion cancelled during pause."
                    time.sleep(0.1)  # Sleep briefly while paused

                if self.current_ffmpeg_process and self.current_ffmpeg_process.stderr:
                    line = self.current_ffmpeg_process.stderr.readline()
                    if not line:
                        break
                    error_output_lines.append(line.strip())
                    if duration_seconds > 0:
                        match = time_regex.search(line)
                        if match:
                            hours, minutes, seconds, hundredths = map(
                                int, match.groups()
                            )
                            current_time_seconds = (
                                hours * 3600
                                + minutes * 60
                                + seconds
                                + hundredths / 100.0
                            )
                            progress_percent = (
                                current_time_seconds / duration_seconds
                            ) * 100
                            self.master.after(
                                0,
                                self.individual_progress_bar.config,
                                {"value": min(progress_percent, 100)},
                            )
                            self.master.after(
                                0,
                                self.individual_progress_status.set,
                                f"Individual File Progress: {current_file_display_name} ({min(progress_percent, 100):.1f}%)",
                            )
                else:
                    break
                if (
                    self.current_ffmpeg_process
                    and self.current_ffmpeg_process.poll() is not None
                ):
                    break

            if (
                self.current_ffmpeg_process
            ):  # Check if process exists before waiting/getting return code
                return_code = self.current_ffmpeg_process.wait()
                # Read any remaining stderr output
                if self.current_ffmpeg_process.stderr:
                    for line in self.current_ffmpeg_process.stderr.readlines():
                        error_output_lines.append(line.strip())
                self.current_ffmpeg_process = None  # Clear after it's done
            elif (
                self.cancel_requested
            ):  # If cancelled, it might have been set to None already
                return False, "Conversion cancelled."
            else:  # Process was never started or lost for other reasons
                return_code = (
                    -1
                )  # Indicate an abnormal termination if process is None without cancel

            if return_code == 0:
                self.master.after(
                    0, self.individual_progress_bar.config, {"value": 100}
                )
                self.master.after(
                    0,
                    self.individual_progress_status.set,
                    f"Individual File Progress: {current_file_display_name} (Completed)",
                )
                return True, None
            else:
                concise_error = (
                    "\n".join(error_output_lines[-5:])
                    if error_output_lines
                    else "Unknown FFmpeg error"
                )
                self.master.after(0, self.individual_progress_bar.config, {"value": 0})
                self.master.after(
                    0,
                    self.individual_progress_status.set,
                    f"Individual File Progress: {current_file_display_name} (Failed)",
                )
                return (
                    False,
                    f"{error_prefix}FFmpeg failed (code {return_code}). Error: ...{concise_error}",
                )

        except Exception as e:
            self.master.after(0, self.individual_progress_bar.config, {"value": 0})
            current_file_display_name = (
                os.path.basename(input_mkv) + current_file_label_suffix
            )  # Ensure suffix for error message
            self.master.after(
                0,
                self.individual_progress_status.set,
                f"Individual File Progress: {current_file_display_name} (Error)",
            )
            return False, f"{error_prefix}Exception during conversion: {str(e)}"
        finally:
            if self.current_ffmpeg_process:  # Ensure Popen process is cleaned up
                try:
                    if (
                        self.current_ffmpeg_process.poll() is None
                    ):  # Check if still running
                        self.current_ffmpeg_process.terminate()
                        self.current_ffmpeg_process.wait(timeout=2)  # Brief wait
                except OSError as e:
                    print(f"Error in finally terminating Popen: {e}")
                except subprocess.TimeoutExpired:
                    print("Timeout in finally terminating Popen, trying kill.")
                    try:
                        self.current_ffmpeg_process.kill()
                    except OSError as e:
                        print(f"Error in finally killing Popen: {e}")
                except Exception as e:  # Catch any other psutil/subprocess issues
                    print(f"Generic error in Popen cleanup: {e}")
            self.current_ffmpeg_process = None
            if self.psutil_process:  # Ensure psutil reference is also cleared
                try:
                    # Check if the process still exists and is suspended, try to resume it
                    # This is a best-effort cleanup, primarily for the *next* file if not batch cancelling
                    if (
                        self.psutil_process.is_running()
                        and self.psutil_process.status() == psutil.STATUS_STOPPED
                    ):
                        print(
                            f"Found suspended process {self.psutil_process.pid} in convert_file finally, attempting resume."
                        )
                        self.psutil_process.resume()
                except psutil.NoSuchProcess:
                    pass  # Process already gone
                except Exception as e:
                    print(f"Error handling psutil_process in convert_file finally: {e}")
            self.psutil_process = None

    def toggle_pause_resume(self):
        if not self.is_converting:
            messagebox.showinfo(
                "Not Converting",
                "No conversion is currently running to pause or resume.",
            )
            return

        if not self.is_paused:  # Attempting to PAUSE
            if self.current_ffmpeg_process and self.current_ffmpeg_process.pid:
                try:
                    if (
                        not self.psutil_process
                    ):  # Create if it doesn't exist or was cleared
                        self.psutil_process = psutil.Process(
                            self.current_ffmpeg_process.pid
                        )

                    if (
                        self.psutil_process.status() == psutil.STATUS_RUNNING
                        or self.psutil_process.status() == psutil.STATUS_SLEEPING
                    ):
                        self.psutil_process.suspend()
                        self.is_paused = True
                        self.pause_resume_button.config(text="Resume")
                        self.conversion_status.set(
                            f"Status: PAUSED (FFmpeg process suspended) | {self.conversion_status.get().split('|')[-1].strip() if '|' in self.conversion_status.get() else ''}"
                        )
                        current_individual_text = self.individual_progress_status.get()
                        if not any(
                            term in current_individual_text
                            for term in [
                                "N/A",
                                "Completed",
                                "Failed",
                                "Error",
                                "PAUSED",
                            ]
                        ):
                            self.master.after(
                                0,
                                self.individual_progress_status.set,
                                f"{current_individual_text.split(' (')[0].strip()} (Paused)",
                            )
                        elif "N/A" in current_individual_text:
                            self.master.after(
                                0,
                                self.individual_progress_status.set,
                                "Individual File Progress: PAUSED",
                            )
                        print(
                            f"FFmpeg process {self.current_ffmpeg_process.pid} suspended."
                        )
                    else:
                        messagebox.showwarning(
                            "Pause Info",
                            f"FFmpeg process is not in a running/suspendable state ({self.psutil_process.status()}).",
                        )
                except psutil.NoSuchProcess:
                    messagebox.showerror(
                        "Pause Error",
                        "FFmpeg process not found. It might have finished or crashed.",
                    )
                    self.current_ffmpeg_process = None
                    self.psutil_process = None
                    self.is_converting = (
                        False  # If process is gone, not converting anymore
                    )
                    self.toggle_ui_state(True)
                except Exception as e:
                    messagebox.showerror(
                        "Pause Error", f"Could not suspend FFmpeg process: {e}"
                    )
                    print(f"Error suspending process: {e}")
            else:
                messagebox.showwarning(
                    "Pause Info", "No active FFmpeg process to pause."
                )
        else:  # Attempting to RESUME
            if self.psutil_process:
                try:
                    if (
                        self.psutil_process.status() == psutil.STATUS_STOPPED
                    ):  # STATUS_STOPPED is what psutil uses for suspended
                        self.psutil_process.resume()
                        self.is_paused = False
                        self.pause_resume_button.config(text="Pause")
                        self.conversion_status.set(
                            f"Status: Resuming conversion... | {self.conversion_status.get().split('|')[-1].strip() if '|' in self.conversion_status.get() else ''}"
                        )
                        current_individual_text = self.individual_progress_status.get()
                        if "(Paused)" in current_individual_text:
                            self.master.after(
                                0,
                                self.individual_progress_status.set,
                                current_individual_text.replace("(Paused)", "").strip(),
                            )
                        elif (
                            "Individual File Progress: PAUSED"
                            == current_individual_text
                        ):
                            self.master.after(
                                0,
                                self.individual_progress_status.set,
                                "Individual File Progress: Resuming...",
                            )
                        print(f"FFmpeg process {self.psutil_process.pid} resumed.")
                    else:
                        messagebox.showwarning(
                            "Resume Info",
                            f"FFmpeg process is not in a suspended state ({self.psutil_process.status()}). Already resumed or finished?",
                        )
                        self.is_paused = False  # Assume it's not paused anymore
                        self.pause_resume_button.config(text="Pause")
                except psutil.NoSuchProcess:
                    messagebox.showerror(
                        "Resume Error",
                        "FFmpeg process not found. It might have finished or crashed.",
                    )
                    self.current_ffmpeg_process = None
                    self.psutil_process = None
                    self.is_converting = False
                    self.toggle_ui_state(True)
                except Exception as e:
                    messagebox.showerror(
                        "Resume Error", f"Could not resume FFmpeg process: {e}"
                    )
                    print(f"Error resuming process: {e}")
            else:
                # If psutil_process is None, but we thought we were paused.
                messagebox.showwarning(
                    "Resume Info",
                    "No FFmpeg process reference to resume. Forcing resume state.",
                )
                self.is_paused = False
                self.pause_resume_button.config(text="Pause")
                self.toggle_ui_state(False)  # Refresh UI based on is_converting

        # The GUI update pausing in convert_file (while self.is_paused) is still a good secondary measure.

    def cancel_batch_conversion(self):
        if self.is_converting:
            response = messagebox.askyesno(
                "Cancel Batch",
                "Are you sure you want to cancel the current batch conversion?",
            )
            if response:
                self.cancel_requested = True
                if (
                    self.is_paused and self.psutil_process
                ):  # If paused by psutil, resume first
                    try:
                        if self.psutil_process.status() == psutil.STATUS_STOPPED:
                            self.psutil_process.resume()
                        print("Resumed FFmpeg process before cancelling.")
                    except psutil.NoSuchProcess:
                        print("FFmpeg process for resume-before-cancel not found.")
                    except Exception as e:
                        print(f"Error resuming FFmpeg before cancel: {e}")
                self.is_paused = (
                    False  # Ensure not stuck in a paused state for UI logic
                )
                # The convert_file loop will check cancel_requested and terminate the Popen process.
                self.conversion_status.set("Status: Batch cancellation requested...")
                self.pause_resume_button.config(state=tk.DISABLED, text="Pause")
                self.cancel_button.config(state=tk.DISABLED)
                # UI will be fully re-enabled by process_batch when it exits.
                # self.psutil_process will be cleared when current_ffmpeg_process is cleared or in convert_file's finally block indirectly.
        else:
            messagebox.showinfo(
                "Not Converting", "No conversion is currently running to cancel."
            )

    def on_closing(self):
        if self.is_converting:
            if messagebox.askyesno(
                "Exit Confirmation",
                "A conversion is in progress. Are you sure you want to exit? This will cancel the current batch.",
            ):
                self.cancel_requested = True

                if (
                    self.is_paused and self.psutil_process
                ):  # If paused by psutil, resume first
                    try:
                        print("Attempting to resume FFmpeg process before closing...")
                        if self.psutil_process.status() == psutil.STATUS_STOPPED:
                            self.psutil_process.resume()
                        print("FFmpeg process resumed for closing.")
                    except psutil.NoSuchProcess:
                        print("FFmpeg process for resume-before-closing not found.")
                    except Exception as e:
                        print(f"Error resuming FFmpeg before closing: {e}")
                self.is_paused = False  # Ensure not stuck paused

                if self.current_ffmpeg_process:  # This is the subprocess.Popen object
                    try:
                        print("Attempting to terminate FFmpeg process on closing...")
                        self.current_ffmpeg_process.terminate()  # Send SIGTERM
                        self.current_ffmpeg_process.wait(
                            timeout=5
                        )  # Wait for it to die
                        print("FFmpeg process terminated or timed out.")
                    except subprocess.TimeoutExpired:
                        print(
                            "FFmpeg process did not terminate in time, attempting to kill..."
                        )
                        self.current_ffmpeg_process.kill()  # Force kill if terminate fails
                        self.current_ffmpeg_process.wait(timeout=2)
                        print("FFmpeg process kill attempt finished.")
                    except OSError as e:
                        print(f"Error terminating/killing FFmpeg process: {e}")
                    finally:
                        self.current_ffmpeg_process = None
                        self.psutil_process = (
                            None  # Clear psutil process reference as well
                        )
                else:  # If no Popen object, ensure psutil_process is also cleared
                    self.psutil_process = None

                if self.conversion_thread and self.conversion_thread.is_alive():
                    print("Waiting for conversion thread to join...")
                    self.conversion_thread.join(timeout=5)  # Wait for thread to finish
                    if self.conversion_thread.is_alive():
                        print("Conversion thread did not join in time.")

                self.master.destroy()
            else:
                return  # Do not close if user cancels exit during conversion
        else:
            if messagebox.askyesno(
                "Exit", "Are you sure you want to exit the application?"
            ):
                self.master.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ConverterApp(root)
    root.mainloop()
