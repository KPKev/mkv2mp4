# MKV2MP4 Converter (Batch)

## Description

This is a Python-based GUI application using Tkinter to batch convert MKV video files to MP4 format (H.264 video + AAC audio). It provides a user-friendly interface to manage a queue of files, monitor conversion progress, and handle failed conversions with multi-level retry options. It also includes a feature to monitor a specified media folder for non-MP4 files and automatically add them to the conversion queue. The application features a tabbed interface for separating conversion controls and logs, and persists queue and settings data between sessions.

## Features

- **Batch Conversion**: Add multiple MKV files to a queue for conversion.
- **MP4 Output**: Converts to MP4 (H.264 video + AAC audio).
- **Progress Monitoring**:
  - Overall batch progress bar.
  - Individual file progress bar with percentage.
- **Queue Management**: Add files, remove selected files, clear the entire queue.
- **Failed Conversion Handling**:
  - Failed files are moved to a separate list with error information.
  - Option to retry all failed files with standard settings.
  - **Two-Tiered Recovery Mode**:
    - **Level 1 Retry**: Uses more balanced and error-tolerant FFmpeg settings.
    - **Level 2 Retry**: Uses very lax and highly compatible FFmpeg settings as a last-ditch effort.
- **Pause/Resume Functionality**: Pause the current FFmpeg conversion process and resume it.
- **Cancel Batch**: Stop the ongoing batch conversion.
- **Graceful Exit**: Ensures FFmpeg processes are terminated when the application is closed.
- **FFmpeg Detection**: Checks for FFmpeg in a local `ffmpeg` subdirectory or in the system PATH.
- **Automatic MKV Folder Conversion / Monitoring**:
  - Select a root media folder to monitor.
  - Periodically scans the folder (and its subdirectories) for common video files (MKV, AVI, MOV, etc.) that are not already in MP4 format.
  - Automatically adds found non-MP4 files to the conversion queue if an MP4 version (or retry version) of the same name doesn't already exist in the same directory.
  - Scan interval is configurable via the UI (default: 10 minutes).
  - Option to automatically delete the original source file after a successful and verified conversion (file exists and size > 1KB). Use with caution.
  - Option to automatically start conversions when the scan adds new files to the queue.
  - Monitoring status (next scan countdown, scanning, paused) is displayed in the status bar.
  - The selected media folder label indicates when monitoring is active.
- **Tabbed Interface**: Main converter functions and application logs are organized into separate tabs ('Converter' and 'Logs').
- **State Persistence**: Remembers the file queue, failed files, retry lists, and Plex monitoring settings (directory, interval, auto-delete, auto-start) between application sessions via a local `mkv_converter_state.json` file.

## Prerequisites

1.  **Python 3**: Ensure you have Python 3 installed (preferably 3.7+).
2.  **FFmpeg**: FFmpeg is required for the actual video conversion. It must be accessible by the application:
    - **Recommended**: Create an `ffmpeg` folder in the same directory as the `mkv_converter_gui.py` script. Inside this `ffmpeg` folder, place the FFmpeg executable (e.g., `ffmpeg.exe`, `ffprobe.exe` on Windows) within a `bin` subfolder (e.g., `ffmpeg/bin/ffmpeg.exe`) or directly in the `ffmpeg` folder (e.g. `ffmpeg/ffmpeg.exe`). The script checks both locations.
    - **Alternative**: Ensure FFmpeg is installed and added to your system's PATH environment variable.
3.  **`psutil` library**: Used for robust pausing and resuming of the FFmpeg process.

## Setup

1.  **Clone the Repository (if applicable)**:

    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```

2.  **Install Dependencies**:
    The primary Python dependency is `psutil`. Install it using pip:

    ```bash
    pip install -r requirements.txt
    ```

    (Or `pip install psutil` if you don't have `requirements.txt` yet or prefer manual installation).

3.  **Set up FFmpeg**:
    - Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html).
    - Follow the recommended placement method described in "Prerequisites" above (local `ffmpeg` folder).

## Usage

1.  Run the script:

    ```bash
    python mkv_converter_gui.py
    ```

2.  **Navigate Tabs**: Use the 'Converter' tab for all conversion operations and the 'Logs' tab to view detailed application activity.
3.  **Add Files**: Click "Add MKV Files..." to select one or more `.mkv` files for manual batch conversion.
4.  **Manage Queue**:
    - Select a file in the main queue and click "Remove Selected" to remove it.
    - Click "Clear Queue" to remove all files from the main queue.
5.  **Start Conversion**: Click "Start Batch Convert". The application will process files one by one from the main queue.
6.  **Pause/Resume**:
    - During conversion, click "Pause" to suspend the current FFmpeg process.
    - Click "Resume" to continue.
7.  **Cancel Batch**: Click "Cancel Batch" to stop all further conversions in the current batch. The currently processing file will be terminated.
8.  **Handle Failed Files**:
    - Files that fail conversion appear in the "Failed Conversions" list.
    - **Retry Failed Files**: Tries to convert failed files again using the original settings.
    - **Retry Failed (Level 1)**: Tries failed files with more error-tolerant settings.
    - **Retry Failed (Level 2)**: Tries failed files with very lax (highly compatible, lower quality) settings.
    - **Clear Failed List**: Removes all files from the failed list.
9.  **Automatic MKV Folder Conversion / Monitoring (Optional)**:
    - **Select Media Folder**: Click "Select Media Folder..." in the "Automatic MKV Folder Conversion" section to choose a root directory containing your video files.
    - **Configure Interval**: Optionally, change the "Scan Interval (min)" from the default (10 minutes).
    - **Start Monitoring**: Click "Start Plex Monitoring". The application will then periodically scan the selected folder and its subfolders.
      - Non-MP4 video files (for which an MP4 version doesn't already exist) will be added to the main conversion queue.
      - The button will change to "Stop Plex Monitoring". Click it again to stop the monitoring.
      - The folder label will indicate "(Monitoring Active)".
      - The status bar will show countdowns for the next scan or current scan status.
    - **Auto-Delete Originals (Caution!)**: If you check "Automatically delete original after verified conversion", the original non-MP4 file will be deleted if the conversion is successful and the output MP4 is verified (exists and is >1KB in size). This only applies to files processed from the monitored folder _while this option is active_.
    - **Auto-Start Conversion**: Check "Automatically start conversion when scan adds files to queue" if you want the application to begin processing the queue automatically after the folder scan finds and adds new files.
10. **Status Updates**: Monitor the status bar at the bottom for overall status, queue count, individual file progress, and Plex monitoring updates. Upon batch completion, a summary message will briefly appear and its details are also recorded in the 'Logs' tab.
11. **View Logs**: Switch to the 'Logs' tab at any time to see a detailed, timestamped record of application actions, FFmpeg process details, errors, and background activities like Plex scanning.

## Output Files

Converted files will be saved in the same directory as their original MKV files:

- Standard conversion: `[original_filename_without_ext].mp4` (e.g., `MyVideo.mkv` becomes `MyVideo.mp4`)
- Level 1 Retry: `[original_filename_without_ext]_retry1.mp4`
- Level 2 Retry: `[original_filename_without_ext]_retry2.mp4`

## License

Copyright (c) [2025] [KPKev]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
