import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import subprocess
import threading
import os
import sys
import re  # For parsing ffmpeg output
import time
import psutil  # For process pause/resume
from datetime import datetime  # For log timestamps
import json  # For saving/loading application state


class ConverterApp:
    STATE_FILE = "mkv_converter_state.json"

    def __init__(self, master):
        self.master = master
        master.title("MKV2MP4 Converter (Batch)")
        # Initial geometry, might be adjusted by notebook packing
        master.geometry("620x950")

        # Set application icon
        try:
            icon_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "app_icon.png"
            )
            if getattr(sys, "frozen", False) and hasattr(
                sys, "_MEIPASS"
            ):  # PyInstaller temporary path
                icon_path = os.path.join(sys._MEIPASS, "app_icon.png")

            if os.path.exists(icon_path):
                img = tk.PhotoImage(file=icon_path)
                master.iconphoto(True, img)
            else:
                self.log_message(f"Icon file not found at {icon_path}", "WARN")
        except tk.TclError as e:
            self.log_message(
                f"Error setting icon: {e}. Ensure app_icon.png is a valid PNG file.",
                "ERROR",
            )
        except Exception as e:
            self.log_message(f"Unexpected error setting icon: {e}", "ERROR")

        # Create the Notebook (tabbed interface)
        self.notebook = ttk.Notebook(master)
        self.notebook.pack(expand=True, fill="both", padx=5, pady=5)

        # --- Create Frames for Tabs ---
        self.converter_tab_frame = ttk.Frame(self.notebook, padding=10)
        self.logs_tab_frame = ttk.Frame(self.notebook, padding=10)

        self.notebook.add(self.converter_tab_frame, text="Converter")
        self.notebook.add(self.logs_tab_frame, text="Logs")

        # --- Populate Logs Tab ---
        log_text_frame = tk.LabelFrame(
            self.logs_tab_frame, text="Application Logs", padx=5, pady=5
        )
        log_text_frame.pack(expand=True, fill="both", padx=5, pady=5)
        self.log_text_area = tk.Text(
            log_text_frame, wrap=tk.WORD, state=tk.DISABLED, height=10
        )  # Start disabled
        log_scrollbar_y = tk.Scrollbar(
            log_text_frame, orient="vertical", command=self.log_text_area.yview
        )
        self.log_text_area.config(yscrollcommand=log_scrollbar_y.set)
        log_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text_area.pack(side=tk.LEFT, expand=True, fill="both")
        # Make log_text_area temporarily normal to add initial message, then disable again
        self.log_message("Application initialized.", "INFO")

        # --- All other UI elements will now go into self.converter_tab_frame ---
        # Adjust references from 'master' to 'self.converter_tab_frame' for main UI elements
        main_ui_container = self.converter_tab_frame

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
        self.plex_media_directory = tk.StringVar(value="Not Set")  # For Plex media path
        self.auto_delete_verified_originals = tk.BooleanVar(
            value=False
        )  # For auto-deletion toggle
        self.plex_scan_interval_minutes_sv = tk.StringVar(value="10")  # UI for interval
        self.auto_start_plex_conversions = tk.BooleanVar(
            value=False
        )  # For auto-start toggle
        self.is_monitoring_plex = False  # True if Plex monitoring is active
        self.plex_monitoring_thread = None  # Thread for Plex monitoring
        self.plex_scan_interval_seconds = 600  # e.g., 10 minutes
        self.use_gpu_acceleration = tk.BooleanVar(value=False)  # For NVENC

        # --- UI Elements (now placed in main_ui_container which is converter_tab_frame) ---
        current_row = 0
        # File Queue Management Frame
        queue_frame = tk.LabelFrame(
            main_ui_container, text="Conversion Queue", padx=5, pady=5
        )
        queue_frame.grid(
            row=current_row, column=0, columnspan=4, padx=10, pady=10, sticky="ewns"
        )
        main_ui_container.grid_rowconfigure(current_row, weight=1)
        main_ui_container.grid_columnconfigure(0, weight=1)
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
        button_frame = tk.Frame(main_ui_container)
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
        failed_frame = tk.LabelFrame(
            main_ui_container, text="Failed Conversions", padx=5, pady=5
        )
        failed_frame.grid(
            row=current_row, column=0, columnspan=4, padx=10, pady=5, sticky="ewns"
        )
        main_ui_container.grid_rowconfigure(current_row, weight=1)
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
        failed_button_frame = tk.Frame(main_ui_container)
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
        format_frame = tk.Frame(main_ui_container)
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

        # GPU Acceleration Checkbox
        self.gpu_checkbox = tk.Checkbutton(
            main_ui_container,  # Or an appropriate sub-frame
            text="Use GPU Acceleration (NVIDIA NVENC)",
            variable=self.use_gpu_acceleration,
        )
        # Place it before the action_frame
        self.gpu_checkbox.grid(
            row=current_row, column=0, columnspan=4, padx=10, pady=(0, 5), sticky="w"
        )
        current_row += 1  # Increment row after adding the checkbox

        # Action Buttons Frame (Start, Pause, Cancel)
        action_frame = tk.Frame(main_ui_container)
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
        overall_progress_frame = tk.Frame(main_ui_container)
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
        individual_progress_frame = tk.Frame(main_ui_container)
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
            main_ui_container,
            textvariable=self.conversion_status,
            relief=tk.SUNKEN,
            anchor="w",
        )
        self.status_label.grid(
            row=current_row, column=0, columnspan=4, padx=10, pady=10, sticky="ew"
        )
        current_row += 1

        # --- Plex Mode / Automatic Conversion Frame ---
        plex_frame = tk.LabelFrame(
            main_ui_container, text="Automatic MKV Folder Conversion", padx=5, pady=5
        )
        plex_frame.grid(
            row=current_row, column=0, columnspan=4, padx=10, pady=10, sticky="ewns"
        )
        current_row += 1

        self.select_plex_dir_button = tk.Button(
            plex_frame,
            text="Select Media Folder...",
            command=self.select_plex_directory,
        )
        self.select_plex_dir_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.plex_dir_label = tk.Label(
            plex_frame,
            textvariable=self.plex_media_directory,
            relief=tk.SUNKEN,
            width=50,
            anchor="w",
        )
        self.plex_dir_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5, pady=5)

        plex_action_frame = tk.Frame(
            main_ui_container
        )  # New frame for scan button to be below directory selection
        plex_action_frame.grid(
            row=current_row, column=0, columnspan=4, padx=10, pady=0, sticky="ew"
        )  # pady=0 for closer spacing
        current_row += 1  # Keep current_row before this frame's content

        # Frame for interval Entry and Scan button to be on the same conceptual level
        plex_controls_subframe = tk.Frame(plex_action_frame)
        plex_controls_subframe.pack(pady=5)

        tk.Label(plex_controls_subframe, text="Scan Interval (min):").pack(
            side=tk.LEFT, padx=(0, 5)
        )
        self.plex_interval_entry = tk.Entry(
            plex_controls_subframe,
            textvariable=self.plex_scan_interval_minutes_sv,
            width=5,
        )
        self.plex_interval_entry.pack(side=tk.LEFT, padx=(0, 10))

        self.scan_plex_dir_button = tk.Button(
            plex_controls_subframe,  # Add to subframe
            text="Start Plex Monitoring",  # Changed text
            command=self.toggle_plex_monitoring,  # Changed command
            state=tk.DISABLED,
        )
        self.scan_plex_dir_button.pack(
            side=tk.LEFT
        )  # pady removed, handled by subframe pack

        self.auto_delete_checkbox = tk.Checkbutton(
            plex_action_frame,  # Remains in plex_action_frame, but below the subframe
            text="Automatically delete original after verified conversion (USE WITH CAUTION!)",
            variable=self.auto_delete_verified_originals,
        )
        self.auto_delete_checkbox.pack(pady=(5, 0))  # Add some padding below

        self.auto_start_conversion_checkbox = tk.Checkbutton(
            plex_action_frame,
            text="Automatically start conversion when scan adds files to queue",
            variable=self.auto_start_plex_conversions,
        )
        self.auto_start_conversion_checkbox.pack(pady=(0, 5))

        current_row += 1  # Increment after all content of plex_action_frame

        # Adjust master window geometry for new section
        # master.geometry("600x910") # Notebook handles overall geometry now

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
        self.load_state()  # Load previous state at the end of init

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
                "Individual File Progress: Processing..."
            )
            # UI state for buttons is handled by toggle_ui_state(False)
        else:
            self.conversion_status.set(
                f"{current_ffmpeg_status} | Queue: {queue_count} file(s)."
            )
            self.individual_progress_bar["value"] = 0
            self.individual_progress_status.set("Individual File Progress: N/A")
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

            conversion_result, result_payload = self.convert_file(
                current_file_path, retry_level=retry_level_to_attempt
            )

            # Clear from retry sets after attempt
            if retry_level_to_attempt == 1:
                self.files_for_retry_level_1.discard(current_file_path)
            elif retry_level_to_attempt == 2:
                self.files_for_retry_level_2.discard(current_file_path)

            if self.cancel_requested:
                self.log_message("Batch cancelled during conversion of a file.", "INFO")
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
                self.log_message(
                    f"Warning: {current_file_name} not found in live queue for removal after processing.",
                    "WARN",
                )
                # print(
                #     f"Warning: {current_file_name} not found in live queue for removal after processing."
                # )

            if not conversion_result:
                self.master.after(
                    0,
                    lambda path=current_file_path, err=result_payload: (
                        self.failed_files_data.append((path, err)),
                        self.failed_listbox.insert(tk.END, os.path.basename(path)),
                    ),
                )
                # Error message now shown by convert_file's return or here directly
                # self.master.after(0, lambda: messagebox.showerror("Conversion Failed", f"Failed to convert: {current_file_name}. Moved to Failed List. Error: {result_payload}"))

            files_processed_in_batch += 1
            self.master.after(
                0,
                lambda fp=files_processed_in_batch,
                tb=total_files_in_batch: self.overall_progress_bar.config(
                    value=(fp / tb) * 100 if tb > 0 else 0
                ),
            )
            self.master.after(0, self.update_status_with_queue_count)

            # Post-conversion processing (verification and potential deletion)
            if conversion_result:  # True if successful
                output_file_path = (
                    result_payload  # This is the output_file_path from convert_file
                )
                current_file_path_normalized = os.path.normpath(current_file_path)

                verified = False
                if os.path.exists(output_file_path):
                    try:
                        if (
                            os.path.getsize(output_file_path)
                            > 10 * 1024 * 1024  # Verify: size > 10MB
                        ):
                            verified = True
                            self.log_message(
                                f"Successfully converted and verified: {output_file_path}",
                                "INFO",
                            )
                            # print(
                            #     f"Successfully converted and verified: {output_file_path}"
                            # )
                        else:
                            self.log_message(
                                f"Verification FAILED for {output_file_path}: File size too small ({os.path.getsize(output_file_path)} bytes).",
                                "WARN",
                            )
                            # print(
                            #     f"Verification FAILED for {output_file_path}: File size too small ({os.path.getsize(output_file_path)} bytes)."
                            # )
                            self.master.after(
                                0,
                                lambda op=output_file_path: self.conversion_status.set(
                                    f"Status: Verified {os.path.basename(op)} - FAILED (size)."
                                ),
                            )
                    except OSError as e:
                        self.log_message(
                            f"Error getting size for {output_file_path}: {e}",
                            "ERROR",
                        )
                        # print(f"Error getting size for {output_file_path}: {e}")
                        self.master.after(
                            0,
                            lambda op=output_file_path: self.conversion_status.set(
                                f"Status: Error verifying {os.path.basename(op)}."
                            ),
                        )
                else:
                    self.log_message(
                        f"Verification FAILED for {output_file_path}: Output file does not exist.",
                        "WARN",
                    )
                    # print(
                    #     f"Verification FAILED for {output_file_path}: Output file does not exist."
                    # )
                    self.master.after(
                        0,
                        lambda op=output_file_path
                        if output_file_path
                        else "unknown output": self.conversion_status.set(
                            f"Status: Verified {os.path.basename(op) if output_file_path else 'unknown'} - FAILED (missing)."
                        ),
                    )

                if verified and self.auto_delete_verified_originals.get():
                    try:
                        self.log_message(
                            f"Attempting to delete original file: {current_file_path_normalized}",
                            "INFO",
                        )
                        os.remove(
                            current_file_path_normalized
                        )  # Use normalized path for consistency
                        self.log_message(
                            f"Successfully deleted original file: {current_file_path_normalized}",
                            "INFO",
                        )
                        self.master.after(
                            0,
                            lambda orig=current_file_path_normalized: self.conversion_status.set(
                                f"Status: Deleted original {os.path.basename(orig)}."
                            ),
                        )
                    except OSError as e:
                        self.log_message(
                            f"Error deleting original file {current_file_path_normalized}: {e}",
                            "ERROR",
                        )
                        # print(
                        #     f"Error deleting original file {current_file_path_normalized}: {e}"
                        # )
                        messagebox.showerror(
                            "Deletion Error",
                            f"Could not delete original file: {current_file_path_normalized}\nError: {e}",
                        )
                        self.master.after(
                            0,
                            lambda orig=current_file_path_normalized: self.conversion_status.set(
                                f"Status: Error deleting {os.path.basename(orig)}."
                            ),
                        )
                elif verified and not self.auto_delete_verified_originals.get():
                    self.log_message(
                        f"Original file not deleted (auto-delete is off): {current_file_path_normalized}",
                        "INFO",
                    )
                    self.master.after(
                        0,
                        lambda: self.conversion_status.set(
                            "Status: Original not deleted (auto-delete off)."
                        ),
                    )
                elif not verified:
                    self.log_message(
                        f"Original file not deleted (verification failed): {current_file_path_normalized}",
                        "WARN",
                    )

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
            0, self.individual_progress_status.set, "Individual File Progress: N/A"
        )
        self.log_message(
            summary_message.replace("\\n", " | "), "INFO"
        )  # Log the summary
        self.master.after(
            0, lambda: self.show_timed_messagebox("Batch Status", summary_message, 5000)
        )

    def show_timed_messagebox(self, title, message, duration_ms):
        timed_msg_window = tk.Toplevel(self.master)
        timed_msg_window.title(title)
        timed_msg_window.transient(
            self.master
        )  # Show above master, and minimize with master
        timed_msg_window.grab_set()  # Make modal

        msg_label = tk.Label(
            timed_msg_window, text=message, justify=tk.LEFT, padx=20, pady=20
        )
        msg_label.pack()

        ok_button = ttk.Button(
            timed_msg_window, text="OK", command=timed_msg_window.destroy, width=10
        )
        ok_button.pack(pady=10)
        ok_button.focus_set()  # Set focus to OK button

        # Center the window
        timed_msg_window.update_idletasks()  # Update geometry
        master_x = self.master.winfo_x()
        master_y = self.master.winfo_y()
        master_width = self.master.winfo_width()
        master_height = self.master.winfo_height()

        win_width = timed_msg_window.winfo_width()
        win_height = timed_msg_window.winfo_height()

        x = master_x + (master_width // 2) - (win_width // 2)
        y = master_y + (master_height // 2) - (win_height // 2)
        timed_msg_window.geometry(f"+{x}+{y}")

        # Store the window reference to prevent garbage collection if needed for the lambda
        # and to allow explicit destroy if OK is pressed before timeout.
        # However, lambda captures window directly.

        # Auto-close after duration_ms
        timed_msg_window.after(
            duration_ms,
            lambda: self._destroy_timed_messagebox_if_exists(timed_msg_window),
        )

    def _destroy_timed_messagebox_if_exists(self, window_instance):
        try:
            if window_instance.winfo_exists():
                window_instance.destroy()
        except tk.TclError:
            pass  # Window already destroyed

    def convert_file(self, input_mkv, retry_level=0):
        """Converts a single file. Returns (True, output_path) on success, (False, error_message) on failure."""
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
                self.log_message(
                    f"Warning: Could not determine valid duration for {input_mkv}. Individual progress may be inaccurate.",
                    "WARN",
                )
                # print(
                #     f"Warning: Could not determine valid duration for {input_mkv}. Individual progress may be inaccurate."
                # )
                duration_seconds = (
                    0  # Will make progress jump to 100 quickly or stay at 0
                )
        except Exception as e:
            self.log_message(
                f"Error getting duration for {input_mkv}: {e}. Individual progress may be inaccurate.",
                "ERROR",
            )
            # print(
            #     f"Error getting duration for {input_mkv}: {e}. Individual progress may be inaccurate."
            # )
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
            else:  # Standard (retry_level == 0)
                file_suffix = ""  # No suffix, just change extension

            if output_format_selected == "MP4 (H.264 + AAC)":
                output_file_path = f"{output_file_base}{file_suffix}.mp4"

                if self.use_gpu_acceleration.get():
                    self.log_message(
                        f"Using GPU acceleration (h264_nvenc) for {input_mkv}", "INFO"
                    )
                    # NVENC specific settings
                    common_nvenc_settings = [
                        "-c:v",
                        "h264_nvenc",
                        "-pix_fmt",
                        "yuv420p",
                    ]

                    if retry_level == 1:  # Level 1 Recovery (Balanced) with GPU
                        ffmpeg_cmd.extend(common_nvenc_settings)
                        ffmpeg_cmd.extend(
                            [
                                "-preset",
                                "p4",  # NVENC medium preset
                                "-cq",
                                "25",  # NVENC Constant Quality
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
                    elif retry_level == 2:  # Level 2 Recovery (Lax) with GPU
                        ffmpeg_cmd.extend(common_nvenc_settings)
                        ffmpeg_cmd.extend(
                            [
                                "-preset",
                                "p1",  # NVENC fastest preset
                                "-cq",
                                "28",
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
                    else:  # Standard (Level 0) MP4 conversion with GPU
                        ffmpeg_cmd.extend(common_nvenc_settings)
                        ffmpeg_cmd.extend(
                            [
                                "-preset",
                                "p5",  # NVENC good quality preset
                                "-cq",
                                "23",
                                "-c:a",
                                "aac",
                                "-b:a",
                                "192k",
                                "-y",
                                output_file_path,
                            ]
                        )
                else:  # CPU-based libx264 commands (existing logic)
                    self.log_message(f"Using CPU (libx264) for {input_mkv}", "INFO")
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
                    self.log_message(
                        f"Cancellation requested during active conversion of {input_mkv}.",
                        "INFO",
                    )
                    if self.current_ffmpeg_process:
                        try:
                            if (
                                self.current_ffmpeg_process.poll() is None
                            ):  # If still running
                                self.log_message(
                                    f"Terminating FFmpeg process {self.current_ffmpeg_process.pid} due to cancellation.",
                                    "INFO",
                                )
                                self.current_ffmpeg_process.terminate()
                                self.current_ffmpeg_process.wait(
                                    timeout=1
                                )  # Short wait for terminate
                                if (
                                    self.current_ffmpeg_process.poll() is None
                                ):  # Still running?
                                    self.log_message(
                                        f"FFmpeg process {self.current_ffmpeg_process.pid} did not terminate, killing.",
                                        "WARN",
                                    )
                                    self.current_ffmpeg_process.kill()
                                    self.current_ffmpeg_process.wait(
                                        timeout=1
                                    )  # Short wait for kill
                        except OSError as e:
                            self.log_message(
                                f"OSError while terminating/killing FFmpeg on cancel: {e}",
                                "ERROR",
                            )
                        except Exception as e:  # Catch any other potential errors
                            self.log_message(
                                f"Exception while terminating/killing FFmpeg on cancel: {e}",
                                "ERROR",
                            )
                    self.current_ffmpeg_process = None
                    if self.psutil_process:  # Clean up psutil process if it exists
                        self.psutil_process = None
                    # Clean up partially converted file if it exists
                    if output_file_path and os.path.exists(output_file_path):
                        try:
                            os.remove(output_file_path)
                            self.log_message(
                                f"Deleted partially converted file on cancel: {output_file_path}",
                                "INFO",
                            )
                        except OSError as e:
                            self.log_message(
                                f"Error deleting partial file {output_file_path} on cancel: {e}",
                                "ERROR",
                            )
                    return False, "Conversion cancelled by user."

                # This is the GUI-level pause check; psutil pause is handled by toggle_pause_resume
                # but self.is_paused is set by it.
                while self.is_paused:
                    if (
                        self.cancel_requested
                    ):  # Re-check cancel during this inner pause loop
                        self.log_message(
                            f"Cancellation requested during pause for {input_mkv}.",
                            "INFO",
                        )
                        if self.current_ffmpeg_process:
                            try:
                                if self.current_ffmpeg_process.poll() is None:
                                    self.current_ffmpeg_process.terminate()
                                    self.current_ffmpeg_process.wait(timeout=1)
                                if self.current_ffmpeg_process.poll() is None:
                                    self.current_ffmpeg_process.kill()
                                    self.current_ffmpeg_process.wait(timeout=1)
                            except Exception as e:
                                self.log_message(
                                    f"Exception during cancel-in-pause for FFmpeg: {e}",
                                    "ERROR",
                                )
                        self.current_ffmpeg_process = None
                        if self.psutil_process:
                            self.psutil_process = None
                        # Clean up partially converted file if it exists (also for cancel during pause)
                        if output_file_path and os.path.exists(output_file_path):
                            try:
                                os.remove(output_file_path)
                                self.log_message(
                                    f"Deleted partially converted file on cancel (during pause): {output_file_path}",
                                    "INFO",
                                )
                            except OSError as e:
                                self.log_message(
                                    f"Error deleting partial file {output_file_path} on cancel (during pause): {e}",
                                    "ERROR",
                                )
                        return False, "Conversion cancelled during pause."
                    time.sleep(0.1)

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
                time.sleep(0.01)  # Prevent tight loop if stderr is quiet

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
                return True, output_file_path
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
                        self.log_message(
                            f"Terminating Popen process {self.current_ffmpeg_process.pid} in finally block for {input_mkv}",
                            "DEBUG",
                        )
                        self.current_ffmpeg_process.terminate()
                        self.current_ffmpeg_process.wait(timeout=2)  # Brief wait
                except OSError as e:
                    self.log_message(
                        f"Error in finally terminating Popen for {input_mkv}: {e}",
                        "ERROR",
                    )
                    # print(f"Error in finally terminating Popen: {e}")
                except subprocess.TimeoutExpired:
                    self.log_message(
                        f"Timeout in finally terminating Popen for {input_mkv}, trying kill.",
                        "WARN",
                    )
                    # print("Timeout in finally terminating Popen, trying kill.")
                    try:
                        self.current_ffmpeg_process.kill()
                        self.log_message(
                            f"Killed Popen process {self.current_ffmpeg_process.pid} for {input_mkv}",
                            "DEBUG",
                        )
                    except OSError as e:
                        self.log_message(
                            f"Error in finally killing Popen for {input_mkv}: {e}",
                            "ERROR",
                        )
                        # print(f"Error in finally killing Popen: {e}")
                except Exception as e:  # Catch any other psutil/subprocess issues
                    self.log_message(
                        f"Generic error in Popen cleanup for {input_mkv}: {e}", "ERROR"
                    )
                    # print(f"Generic error in Popen cleanup: {e}")
                self.current_ffmpeg_process = None
                if self.psutil_process:  # Ensure psutil reference is also cleared
                    try:
                        # Check if the process still exists and is suspended, try to resume it
                        # This is a best-effort cleanup, primarily for the *next* file if not batch cancelling
                        if (
                            self.psutil_process.is_running()
                            and self.psutil_process.status() == psutil.STATUS_STOPPED
                        ):
                            self.log_message(
                                f"Found suspended psutil process {self.psutil_process.pid} in convert_file finally for {input_mkv}, attempting resume.",
                                "DEBUG",
                            )
                            # print(
                            #     f"Found suspended process {self.psutil_process.pid} in convert_file finally, attempting resume."
                            # )
                            self.psutil_process.resume()
                    except psutil.NoSuchProcess:
                        self.log_message(
                            f"psutil.NoSuchProcess for {self.psutil_process.pid if self.psutil_process else 'unknown'} in convert_file finally for {input_mkv}.",
                            "DEBUG",
                        )
                        pass  # Process already gone
                    except Exception as e:
                        self.log_message(
                            f"Error handling psutil_process in convert_file finally for {input_mkv}: {e}",
                            "ERROR",
                        )
                        # print(f"Error handling psutil_process in convert_file finally: {e}")
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
                        self.log_message(
                            f"FFmpeg process {self.current_ffmpeg_process.pid} suspended.",
                            "INFO",
                        )
                        # print(
                        #     f"FFmpeg process {self.current_ffmpeg_process.pid} suspended."
                        # )
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
                    self.log_message(f"Error suspending process: {e}", "ERROR")
                    # print(f"Error suspending process: {e}")
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
                        self.log_message(
                            f"FFmpeg process {self.psutil_process.pid} resumed.", "INFO"
                        )
                        # print(f"FFmpeg process {self.psutil_process.pid} resumed.")
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
                    self.log_message(f"Error resuming process: {e}", "ERROR")
                    # print(f"Error resuming process: {e}")
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
                        self.log_message(
                            "Resumed FFmpeg process before cancelling.", "INFO"
                        )
                        # print("Resumed FFmpeg process before cancelling.")
                    except psutil.NoSuchProcess:
                        self.log_message(
                            "FFmpeg process for resume-before-cancel (batch) not found.",
                            "WARN",
                        )
                        # print("FFmpeg process for resume-before-cancel not found.")
                    except Exception as e:
                        self.log_message(
                            f"Error resuming FFmpeg before batch cancel: {e}", "ERROR"
                        )
                        # print(f"Error resuming FFmpeg before cancel: {e}")
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
                self.is_monitoring_plex = False  # Stop monitoring thread as well

                if (
                    self.is_paused and self.psutil_process
                ):  # If paused by psutil, resume first
                    try:
                        self.log_message(
                            "Attempting to resume FFmpeg process before closing app.",
                            "INFO",
                        )
                        # print("Attempting to resume FFmpeg process before closing...")
                        if self.psutil_process.status() == psutil.STATUS_STOPPED:
                            self.psutil_process.resume()
                        self.log_message(
                            "FFmpeg process resumed for closing app.", "INFO"
                        )
                        # print("FFmpeg process resumed for closing.")
                    except psutil.NoSuchProcess:
                        self.log_message(
                            "FFmpeg process for resume-before-closing (app) not found.",
                            "WARN",
                        )
                        # print("FFmpeg process for resume-before-closing not found.")
                    except Exception as e:
                        self.log_message(
                            f"Error resuming FFmpeg before closing app: {e}", "ERROR"
                        )
                        # print(f"Error resuming FFmpeg before closing: {e}")
                self.is_paused = False  # Ensure not stuck paused

                if self.current_ffmpeg_process:  # This is the subprocess.Popen object
                    try:
                        self.log_message(
                            f"Attempting to terminate FFmpeg process {self.current_ffmpeg_process.pid} on closing app.",
                            "INFO",
                        )
                        # print("Attempting to terminate FFmpeg process on closing...")
                        self.current_ffmpeg_process.terminate()  # Send SIGTERM
                        self.current_ffmpeg_process.wait(
                            timeout=5
                        )  # Wait for it to die
                        self.log_message(
                            f"FFmpeg process {self.current_ffmpeg_process.pid} terminated or timed out on closing.",
                            "INFO",
                        )
                        # print("FFmpeg process terminated or timed out.")
                    except subprocess.TimeoutExpired:
                        self.log_message(
                            f"FFmpeg process {self.current_ffmpeg_process.pid} did not terminate in time, attempting to kill...",
                            "WARN",
                        )
                        # print(
                        #     "FFmpeg process did not terminate in time, attempting to kill..."
                        # )
                        self.current_ffmpeg_process.kill()  # Force kill if terminate fails
                        self.current_ffmpeg_process.wait(timeout=2)
                        self.log_message(
                            f"FFmpeg process {self.current_ffmpeg_process.pid} kill attempt finished on closing.",
                            "INFO",
                        )
                        # print("FFmpeg process kill attempt finished.")
                    except OSError as e:
                        self.log_message(
                            f"Error terminating/killing FFmpeg process {self.current_ffmpeg_process.pid} on closing: {e}",
                            "ERROR",
                        )
                        # print(f"Error terminating/killing FFmpeg process: {e}")
                    finally:
                        self.current_ffmpeg_process = None
                        self.psutil_process = (
                            None  # Clear psutil process reference as well
                        )
                else:  # If no Popen object, ensure psutil_process is also cleared
                    self.psutil_process = None

                if self.conversion_thread and self.conversion_thread.is_alive():
                    self.log_message(
                        "Waiting for conversion thread to join on closing app.", "INFO"
                    )
                    # print("Waiting for conversion thread to join...")
                    self.conversion_thread.join(timeout=5)  # Wait for thread to finish
                    if self.conversion_thread.is_alive():
                        self.log_message(
                            "Conversion thread did not join in time on closing app.",
                            "WARN",
                        )
                        # print("Conversion thread did not join in time.")

                if (
                    self.plex_monitoring_thread
                    and self.plex_monitoring_thread.is_alive()
                ):
                    self.log_message(
                        "Waiting for Plex monitoring thread to join on closing app.",
                        "INFO",
                    )
                    # print("Waiting for Plex monitoring thread to join...")
                    self.plex_monitoring_thread.join(
                        timeout=5
                    )  # Wait for thread to finish
                    if self.plex_monitoring_thread.is_alive():
                        self.log_message(
                            "Plex monitoring thread did not join in time on closing app.",
                            "WARN",
                        )
                        # print("Plex monitoring thread did not join in time.")

                self.master.destroy()
            else:
                return  # Do not close if user cancels exit during conversion
        else:
            if messagebox.askyesno(
                "Exit", "Are you sure you want to exit the application?"
            ):
                self.is_monitoring_plex = False  # Stop monitoring thread before exit
                if (
                    self.plex_monitoring_thread
                    and self.plex_monitoring_thread.is_alive()
                ):
                    self.log_message(
                        "Waiting for Plex monitoring thread to join on exit (no conversion).",
                        "INFO",
                    )
                    # print("Waiting for Plex monitoring thread to join on exit...")
                    self.plex_monitoring_thread.join(timeout=5)
                    if self.plex_monitoring_thread.is_alive():
                        self.log_message(
                            "Plex monitoring thread did not join in time on exit (no conversion).",
                            "WARN",
                        )
                        # print("Plex monitoring thread did not join in time on exit.")
                self.save_state()  # Save state before destroying
                self.master.destroy()

    def select_plex_directory(self):
        if self.is_converting:
            messagebox.showwarning(
                "Busy", "Cannot change directory while conversion is in progress."
            )
            return

        if self.is_monitoring_plex:
            messagebox.showinfo(
                "Plex Monitoring",
                "Plex monitoring will be stopped to change the directory.",
            )
            self.log_message("Plex monitoring stopped due to directory change.", "INFO")
            self.toggle_plex_monitoring()  # Stop monitoring

        directory_path = filedialog.askdirectory(title="Select Your Main Media Folder")
        if directory_path:
            self.plex_media_directory.set(directory_path)
            self.scan_plex_dir_button.config(
                state=tk.NORMAL
            )  # Enable monitoring button
            self.conversion_status.set(
                f"Status: Media folder set to: {directory_path}. Ready to scan or monitor."
            )
        else:
            # self.plex_media_directory.set("Not Set") # Keep old if cancelled, or clear
            if (
                self.plex_media_directory.get() == "Not Set"
                or not self.plex_media_directory.get()
            ):
                self.scan_plex_dir_button.config(state=tk.DISABLED)

    def scan_plex_directory_and_add(self, called_from_thread=False):
        if (
            self.is_converting and not called_from_thread
        ):  # Allow scan if called from thread even if converting other files
            messagebox.showwarning(
                "Busy", "Cannot start scan while conversion is in progress."
            )
            return

        target_dir_display = self.plex_media_directory.get()
        # Get the actual path for os functions by removing the display suffix
        actual_target_dir = target_dir_display.replace(
            " (Monitoring Active)", ""
        ).strip()

        if (
            not actual_target_dir
            or actual_target_dir == "Not Set"
            or not os.path.isdir(actual_target_dir)
        ):
            if not called_from_thread:
                messagebox.showerror(
                    "Error",
                    f"Please select a valid media folder first. Path checked: '{actual_target_dir}'",
                )
            else:
                self.log_message(
                    f"Scan Plex Dir Error: Invalid or inaccessible media folder. Path checked: '{actual_target_dir}'",
                    "ERROR",
                )
                # print(f"Scan Plex Dir Error: Invalid or inaccessible media folder. Path checked: '{actual_target_dir}'") # Log for thread
            return

        # Status update before scan is now handled by plex_monitoring_loop
        # self.master.after(0, lambda: self.conversion_status.set(
        # f"Status: Scanning {target_dir} for non-MP4 files..."
        # ))
        # if not called_from_thread:
        # self.master.update_idletasks()

        video_extensions_to_scan = (
            ".mkv",
            ".avi",
            ".mov",
            ".flv",
            ".wmv",
            ".mpeg",
            ".mpg",
            ".ts",
            ".m2ts",
        )
        files_found_to_convert = []

        for root, _, files in os.walk(
            actual_target_dir
        ):  # Use actual_target_dir for os.walk
            for file in files:
                file_path = os.path.join(root, file)
                if file_path.lower().endswith(video_extensions_to_scan):
                    # Check if an MP4 version already exists (same base name)
                    base_name, _ = os.path.splitext(file_path)
                    mp4_equivalent = base_name + ".mp4"
                    mp4_retry1_equivalent = base_name + "_retry1.mp4"
                    mp4_retry2_equivalent = base_name + "_retry2.mp4"

                    if not (
                        os.path.exists(mp4_equivalent)
                        or os.path.exists(mp4_retry1_equivalent)
                        or os.path.exists(mp4_retry2_equivalent)
                    ):
                        files_found_to_convert.append(file_path)
                    else:
                        self.log_message(
                            f"Plex Scan: Skipping '{file_path}', MP4 version already exists.",
                            "DEBUG",
                        )
                        # print(f"Skipping {file_path}, MP4 version already exists.")

        added_to_queue_count = 0
        if files_found_to_convert:
            for file_path in files_found_to_convert:
                if file_path not in self.file_queue and not any(
                    fp == file_path for fp, _ in self.failed_files_data
                ):
                    self.file_queue.append(file_path)
                    self.queue_listbox.insert(tk.END, os.path.basename(file_path))
                    added_to_queue_count += 1

            if added_to_queue_count > 0:
                final_message = f"Plex Scan: Added {added_to_queue_count} file(s) to queue from {os.path.basename(actual_target_dir)}."
                if not called_from_thread:
                    messagebox.showinfo("Scan Complete", final_message)
                    self.master.after(
                        0,
                        lambda: self.conversion_status.set(
                            f"Status: {final_message} | Queue: {len(self.file_queue)} file(s)."
                        ),
                    )
                else:
                    self.log_message(final_message, "INFO")
                    # print(final_message)  # Log for thread
                    # Status update for "Next scan in..." will be set by the loop after this returns
                self.master.after(0, self.update_status_with_queue_count)
            else:
                final_message = f"Plex Scan: No new files to add from {os.path.basename(actual_target_dir)}."
                if not called_from_thread:
                    messagebox.showinfo("Scan Complete", final_message)
                    self.master.after(
                        0,
                        lambda: self.conversion_status.set(
                            f"Status: {final_message} | Queue: {len(self.file_queue)} file(s)."
                        ),
                    )
                else:
                    self.log_message(final_message, "INFO")
                    # print(final_message)  # Log for thread
        else:  # files_found_to_convert was empty
            final_message = f"Plex Scan: No non-MP4 files found in {os.path.basename(actual_target_dir)}."
            if not called_from_thread:
                messagebox.showinfo("Scan Complete", final_message)
                self.master.after(
                    0,
                    lambda: self.conversion_status.set(
                        f"Status: {final_message} | Queue: {len(self.file_queue)} file(s)."
                    ),
                )
            else:
                self.log_message(final_message, "INFO")
                # print(final_message)  # Log for thread

        # Auto-start conversion if enabled and files were added
        if (
            called_from_thread
            and added_to_queue_count > 0
            and self.auto_start_plex_conversions.get()
        ):
            self.log_message(
                f"Plex Scan: {added_to_queue_count} file(s) added. Auto-starting conversion.",
                "INFO",
            )
            # Ensure this runs on the main thread and doesn't interfere if already converting
            self.master.after(0, self._check_and_start_conversion_after_scan)

    def _check_and_start_conversion_after_scan(self):
        if not self.is_converting and self.file_queue:
            self.log_message("Auto-starting batch conversion from Plex scan.", "INFO")
            self.start_conversion_thread()
        elif self.is_converting:
            self.log_message(
                "Auto-start skipped: Conversion already in progress.", "INFO"
            )
        elif not self.file_queue:
            self.log_message(
                "Auto-start skipped: Queue is empty after Plex scan (unexpected).",
                "WARN",
            )

    def save_state(self):
        state_data = {
            "file_queue": self.file_queue,
            "failed_files_data": self.failed_files_data,
            "files_for_retry_level_1": list(self.files_for_retry_level_1),
            "files_for_retry_level_2": list(self.files_for_retry_level_2),
            "plex_media_directory": self.plex_media_directory.get(),
            "auto_delete_verified_originals": self.auto_delete_verified_originals.get(),
            "plex_scan_interval_minutes": self.plex_scan_interval_minutes_sv.get(),
            "auto_start_plex_conversions": self.auto_start_plex_conversions.get(),
            "use_gpu_acceleration": self.use_gpu_acceleration.get(),  # Save GPU setting
        }
        try:
            with open(self.STATE_FILE, "w") as f:
                json.dump(state_data, f, indent=4)
            self.log_message(f"Application state saved to {self.STATE_FILE}", "INFO")
        except IOError as e:
            self.log_message(
                f"Error saving application state to {self.STATE_FILE}: {e}", "ERROR"
            )
        except Exception as e:
            self.log_message(
                f"An unexpected error occurred while saving state: {e}", "ERROR"
            )

    def load_state(self):
        try:
            if os.path.exists(self.STATE_FILE):
                with open(self.STATE_FILE, "r") as f:
                    state_data = json.load(f)

                self.file_queue = state_data.get("file_queue", [])
                self.failed_files_data = state_data.get("failed_files_data", [])
                self.files_for_retry_level_1 = set(
                    state_data.get("files_for_retry_level_1", [])
                )
                self.files_for_retry_level_2 = set(
                    state_data.get("files_for_retry_level_2", [])
                )

                plex_dir = state_data.get("plex_media_directory", "Not Set")
                # Ensure we don't load " (Monitoring Active)" into the actual variable if app was closed while monitoring
                self.plex_media_directory.set(
                    plex_dir.replace(" (Monitoring Active)", "").strip()
                )
                if (
                    self.plex_media_directory.get()
                    and self.plex_media_directory.get() != "Not Set"
                    and os.path.isdir(self.plex_media_directory.get())
                ):
                    self.scan_plex_dir_button.config(state=tk.NORMAL)
                else:
                    self.plex_media_directory.set(
                        "Not Set"
                    )  # Ensure it's clean if loaded path is invalid
                    self.scan_plex_dir_button.config(state=tk.DISABLED)

                self.auto_delete_verified_originals.set(
                    state_data.get("auto_delete_verified_originals", False)
                )
                self.plex_scan_interval_minutes_sv.set(
                    state_data.get("plex_scan_interval_minutes", "10")
                )
                self.auto_start_plex_conversions.set(
                    state_data.get("auto_start_plex_conversions", False)
                )
                self.use_gpu_acceleration.set(
                    state_data.get(
                        "use_gpu_acceleration", False
                    )  # Load GPU setting, default to False
                )

                # Repopulate listboxes
                self.queue_listbox.delete(0, tk.END)
                for item in self.file_queue:
                    # Determine if it's a retry item to display correctly
                    display_name = os.path.basename(item)
                    if item in self.files_for_retry_level_1:
                        display_name += " (Level 1)"
                    elif item in self.files_for_retry_level_2:
                        display_name += " (Level 2)"
                    self.queue_listbox.insert(tk.END, display_name)

                self.failed_listbox.delete(0, tk.END)
                for path, reason in self.failed_files_data:
                    self.failed_listbox.insert(tk.END, os.path.basename(path))

                self.update_status_with_queue_count()  # Update buttons and status
                self.log_message(
                    f"Application state loaded from {self.STATE_FILE}", "INFO"
                )
            else:
                self.log_message("No previous application state file found.", "INFO")
        except IOError as e:
            self.log_message(
                f"Error loading application state from {self.STATE_FILE}: {e}", "ERROR"
            )
            # Don't halt app, just start fresh
        except json.JSONDecodeError as e:
            self.log_message(
                f"Error decoding state file {self.STATE_FILE}: {e}. Starting fresh.",
                "ERROR",
            )
        except Exception as e:
            self.log_message(
                f"An unexpected error occurred while loading state: {e}. Starting fresh.",
                "ERROR",
            )

    def toggle_plex_monitoring(self):
        if (
            self.is_converting and not self.is_monitoring_plex
        ):  # Allow stopping monitoring even if converting
            messagebox.showwarning(
                "Busy",
                "Cannot start monitoring while a conversion is in progress. Please wait or cancel.",
            )
            return

        if self.is_monitoring_plex:
            # Stop monitoring
            self.is_monitoring_plex = False
            self.scan_plex_dir_button.config(text="Start Plex Monitoring")
            self.plex_interval_entry.config(
                state=tk.NORMAL
            )  # Re-enable entry when stopping

            current_plex_path = self.plex_media_directory.get()
            if current_plex_path.endswith(" (Monitoring Active)"):
                self.plex_media_directory.set(
                    current_plex_path.replace(" (Monitoring Active)", "")
                )

            # Enable the button if a directory is set
            if (
                self.plex_media_directory.get()
                and self.plex_media_directory.get() != "Not Set"
            ):
                self.scan_plex_dir_button.config(state=tk.NORMAL)
            else:
                self.scan_plex_dir_button.config(state=tk.DISABLED)

            status_parts = self.conversion_status.get().split("|")
            base_status = status_parts[0].strip()
            if (
                "Plex monitoring stopped." not in base_status
                and "Plex monitoring started." not in base_status
            ):
                self.master.after(
                    0,
                    self.conversion_status.set,
                    f"Status: Plex monitoring stopped. | {base_status}",
                )
            else:
                self.master.after(
                    0,
                    self.conversion_status.set,
                    f"Status: Plex monitoring stopped. {status_parts[-1].strip() if len(status_parts) > 1 else ''}",
                )

            self.log_message("Plex monitoring stopping...", "INFO")
            # print("Plex monitoring stopping...")
            if self.plex_monitoring_thread and self.plex_monitoring_thread.is_alive():
                pass
        else:
            # Start monitoring
            plex_dir = self.plex_media_directory.get()
            if not plex_dir or plex_dir == "Not Set" or not os.path.isdir(plex_dir):
                messagebox.showerror(
                    "Error",
                    "Please select a valid media folder before starting monitoring.",
                )
                return

            try:
                interval_minutes_val = int(self.plex_scan_interval_minutes_sv.get())
                if interval_minutes_val <= 0:
                    messagebox.showerror(
                        "Error", "Scan interval must be a positive number of minutes."
                    )
                    return
                self.plex_scan_interval_seconds = interval_minutes_val * 60
            except ValueError:
                messagebox.showerror(
                    "Error", "Invalid scan interval. Please enter a number."
                )
                return

            self.is_monitoring_plex = True
            self.scan_plex_dir_button.config(
                text="Stop Plex Monitoring", state=tk.NORMAL
            )
            self.plex_interval_entry.config(
                state=tk.DISABLED
            )  # Disable entry when monitoring starts

            current_plex_path = self.plex_media_directory.get()
            if current_plex_path != "Not Set" and not current_plex_path.endswith(
                " (Monitoring Active)"
            ):
                self.plex_media_directory.set(
                    f"{current_plex_path} (Monitoring Active)"
                )

            # Clear previous "Next scan in..." message when starting
            # Let the plex_monitoring_loop handle the new status
            base_status_parts = self.conversion_status.get().split("|")
            current_action_status = "Plex monitoring started."
            queue_info = (
                base_status_parts[-1].strip()
                if len(base_status_parts) > 1
                and (
                    "Queue:" in base_status_parts[-1]
                    or "Files remaining:" in base_status_parts[-1]
                )
                else f"Queue: {len(self.file_queue)} file(s)."
            )
            self.master.after(
                0,
                self.conversion_status.set,
                f"Status: {current_action_status} | {queue_info}",
            )

            if self.plex_monitoring_thread and self.plex_monitoring_thread.is_alive():
                self.log_message(
                    "Plex monitoring thread already active. Interval possibly updated.",
                    "INFO",
                )
                # print("Monitoring thread already active. Interval possibly updated.")
            else:
                self.plex_monitoring_thread = threading.Thread(
                    target=self.plex_monitoring_loop
                )
                self.plex_monitoring_thread.daemon = True
                self.plex_monitoring_thread.start()
                self.log_message("Plex monitoring thread started.", "INFO")
                # print("Plex monitoring thread started.")

    def plex_monitoring_loop(self):
        self.log_message(
            f"Plex monitoring loop started. Interval: {self.plex_scan_interval_seconds}s",
            "INFO",
        )
        # print(f"Plex monitoring loop started. Interval: {self.plex_scan_interval_seconds}s")
        # Initial short delay before first scan to allow UI to update
        time.sleep(2)

        while self.is_monitoring_plex:
            current_scan_interval = (
                self.plex_scan_interval_seconds
            )  # Use the potentially updated value
            if self.is_converting:
                status_msg = "Plex scan paused (conversion active)."
                self.log_message(status_msg, "DEBUG")
                # print(status_msg)
                self.master.after(
                    0, lambda sm=status_msg: self.update_plex_monitoring_status(sm)
                )
                # Wait a shorter time if converting, then re-check
                wait_interval = min(60, current_scan_interval)
            elif (
                not self.plex_media_directory.get()
                or self.plex_media_directory.get() == "Not Set"
            ):
                status_msg = "Plex scan paused (directory not set)."
                self.log_message(status_msg, "DEBUG")
                # print(status_msg)
                self.master.after(
                    0, lambda sm=status_msg: self.update_plex_monitoring_status(sm)
                )
                wait_interval = min(60, current_scan_interval)
            else:
                scan_status_msg = f"Plex: Scanning {os.path.basename(self.plex_media_directory.get().replace(' (Monitoring Active)', ''))}..."  # Clean name for log
                self.log_message(scan_status_msg, "INFO")
                # print(scan_status_msg)
                self.master.after(
                    0, lambda sm=scan_status_msg: self.update_plex_monitoring_status(sm)
                )
                self.scan_plex_directory_and_add(called_from_thread=True)
                # After scan, immediately start countdown for next scan
                wait_interval = current_scan_interval

            # Countdown loop for the wait_interval or until monitoring is stopped
            for i in range(wait_interval):
                if not self.is_monitoring_plex:
                    break
                remaining_time = wait_interval - i
                minutes, seconds = divmod(remaining_time, 60)
                countdown_msg = f"Plex: Next scan in {minutes}m {seconds}s."
                # Log less frequently for countdown to avoid spamming logs
                if (
                    i % 30 == 0 or i == wait_interval - 1
                ):  # Log every 30s or last second before new state
                    self.log_message(
                        f"Plex monitoring countdown: {remaining_time}s remaining.",
                        "DEBUG",
                    )

                if self.is_converting:
                    countdown_msg = f"Plex: Monitoring paused (conversion active). Next check in {minutes}m {seconds}s."
                elif (
                    not self.plex_media_directory.get()
                    or self.plex_media_directory.get() == "Not Set"
                ):
                    countdown_msg = f"Plex: Monitoring paused (directory not set). Next check in {minutes}m {seconds}s."

                self.master.after(
                    0, lambda cm=countdown_msg: self.update_plex_monitoring_status(cm)
                )
                time.sleep(1)

        self.log_message("Plex monitoring loop finished.", "INFO")
        # print("Plex monitoring loop finished.")
        self.master.after(
            0, lambda: self.update_plex_monitoring_status("Plex monitoring stopped.")
        )

    def update_plex_monitoring_status(self, plex_status_text):
        current_status = self.conversion_status.get()
        parts = current_status.split("|")
        main_action_status = parts[0].strip()

        # Preserve main action status (Idle, Converting, Batch Finished, etc.)
        # unless the plex_status_text itself is a primary status like "Plex monitoring stopped."
        if (
            plex_status_text == "Plex monitoring stopped."
            or plex_status_text == "Plex monitoring started."
        ):
            new_main_status = plex_status_text
            queue_info = (
                parts[-1].strip()
                if len(parts) > 1
                and ("Queue:" in parts[-1] or "Files remaining:" in parts[-1])
                else f"Queue: {len(self.file_queue)} file(s)."
            )
            self.conversion_status.set(f"Status: {new_main_status} | {queue_info}")
        elif (
            "Plex:" in plex_status_text or "Plex scan paused" in plex_status_text
        ):  # Plex specific sub-status
            # Try to find existing queue info or general status
            # If main_action_status is already a plex status, replace it.
            if (
                "Plex:" in main_action_status
                or "Plex scan paused" in main_action_status
                or "Plex monitoring stopped." in main_action_status
                or "Plex monitoring started." in main_action_status
            ):
                core_status = "Idle"  # Default if we are overwriting a plex status
                # Attempt to find a non-Plex part of the status if it exists
                # This logic could be more robust if needed.
                if len(parts) > 1 and not (
                    "Plex:" in parts[0] or "Plex scan paused" in parts[0]
                ):
                    core_status = parts[0].replace("Status:", "").strip()
                elif len(parts) == 1 and not (
                    "Plex:" in current_status or "Plex scan paused" in current_status
                ):
                    core_status = current_status.replace("Status:", "").strip()
                self.conversion_status.set(
                    f"Status: {core_status} | {plex_status_text}"
                )
            else:
                # Append Plex status as a secondary part if there's other primary info
                queue_info = (
                    parts[-1].strip()
                    if len(parts) > 1
                    and ("Queue:" in parts[-1] or "Files remaining:" in parts[-1])
                    else f"Queue: {len(self.file_queue)} file(s)."
                )
                if main_action_status.startswith("Status:"):
                    main_action_status = main_action_status.replace(
                        "Status:", ""
                    ).strip()
                self.conversion_status.set(
                    f"Status: {main_action_status} | {plex_status_text} | {queue_info}"
                )
        else:  # General status update not specifically from Plex monitoring loop countdown
            # This case might not be hit often if plex_status_text is always specific
            self.conversion_status.set(
                f"Status: {plex_status_text} | Queue: {len(self.file_queue)} file(s)."
            )

    def log_message(self, message, level="INFO"):
        # Ensure UI updates happen on the main thread
        self.master.after(0, self._do_log_message, message, level)

    def _do_log_message(self, message, level):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{timestamp}] [{level.upper()}] {message}\n"

        current_state = self.log_text_area.cget("state")
        self.log_text_area.config(state=tk.NORMAL)
        self.log_text_area.insert(tk.END, formatted_message)
        self.log_text_area.see(tk.END)  # Scroll to the end
        self.log_text_area.config(
            state=current_state
        )  # Restore original state (usually DISABLED)
        # If starting disabled, we should enable, write, then disable.
        if current_state == tk.DISABLED:
            self.log_text_area.config(state=tk.DISABLED)


if __name__ == "__main__":
    root = tk.Tk()
    app = ConverterApp(root)
    root.mainloop()
