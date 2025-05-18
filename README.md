# MKV2MP4 Converter (Batch)

**User-friendly GUI to batch convert video files (MKV, etc.) to MP4 (H.264/AAC). Power up your media management with NVIDIA GPU acceleration, automated recursive folder scanning (ideal for Plex/media libraries) to find & convert non-MP4 files, configurable auto-deletion, multi-level retries, and detailed logging. Perfect for standardizing large video collections.**

## Description

This is a Python-based GUI application using Tkinter to batch convert video files (primarily MKV, but scans for others like AVI, MOV) to MP4 format (H.264 video + AAC audio). It provides a user-friendly interface to manage a queue of files, monitor conversion progress, handle failed conversions with multi-level retry options, and optionally use GPU acceleration for faster conversions. It also includes a feature to monitor a specified media folder (and its subdirectories) for common video files that are not already in MP4 format, automatically adding them to the conversion queue. The application features a tabbed interface for separating conversion controls and logs, and persists queue and settings data between sessions. It also includes a custom application icon.

## Features

- **Batch Conversion**: Add multiple MKV files to a queue for conversion.
- **MP4 Output**: Converts to MP4 (H.264 video + AAC audio).
- **GPU Acceleration (Optional)**: Utilizes NVIDIA NVENC for H.264 encoding if a compatible GPU and FFmpeg build are detected, significantly speeding up conversions.
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
- **Robust Cancel Batch**: Stop the ongoing batch conversion; the currently processing file will be terminated, and any partially converted output for that file will be cleaned up.
- **Graceful Exit**: Ensures FFmpeg processes are terminated when the application is closed.
- **FFmpeg Detection**: Checks for FFmpeg in a local `ffmpeg` subdirectory or in the system PATH.
- **Automatic MKV Folder Conversion / Monitoring**:
  - Select a root media folder to monitor.
  - Periodically scans the folder (and its subdirectories) for common video files (MKV, AVI, MOV, etc.) that are not already in MP4 format.
  - Automatically adds found non-MP4 files to the conversion queue if an MP4 version (or retry version) of the same name doesn't already exist in the same directory.
  - Scan interval is configurable via the UI (default: 10 minutes).
  - **Auto-Delete Originals (Caution!)**: If checked, the original source file will be deleted after a successful and verified conversion (output file exists and its size > 10MB), regardless of how the file was added to the queue (manually or via scan). Use with caution.
  - Option to automatically start conversions when the scan adds new files to the queue.
  - Monitoring status (next scan countdown, scanning, paused) is displayed in the status bar.
  - The selected media folder label indicates when monitoring is active.
- **Tabbed Interface**: Main converter functions and application logs are organized into separate tabs ('Converter' and 'Logs').
- **State Persistence**: Remembers the file queue, failed files, retry lists, Plex monitoring settings (directory, interval, auto-delete, auto-start), and GPU acceleration preference between application sessions via a local `mkv_converter_state.json` file.
- **Custom Application Icon**: Displays a custom icon in the window title bar and taskbar.

## Prerequisites

1.  **Python 3**: Ensure you have Python 3 installed (preferably 3.7+).
2.  **FFmpeg**: FFmpeg is required for the actual video conversion. It must be accessible by the application:
    - **Recommended**: Create an `ffmpeg` folder in the same directory as the `mkv_converter_gui.py` script. Inside this `ffmpeg` folder, place the FFmpeg executable (e.g., `ffmpeg.exe`, `ffprobe.exe` on Windows) within a `bin` subfolder (e.g., `ffmpeg/bin/ffmpeg.exe`) or directly in the `ffmpeg` folder (e.g. `ffmpeg/ffmpeg.exe`). The script checks both locations.
    - **Alternative**: Ensure FFmpeg is installed and added to your system's PATH environment variable.
    - **Note for GPU Acceleration**: For GPU acceleration, an NVIDIA GPU supporting NVENC is required, and your FFmpeg build must include NVENC support (most modern official builds do).
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
4.  **Application Icon (Optional but included)**:
    - An `app_icon.png` is included for the application icon. Ensure it's in the same directory as the script.

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
5.  **GPU Acceleration (Optional)**: Before starting, you can check the "Use GPU Acceleration (NVIDIA NVENC)" checkbox if you have a compatible NVIDIA GPU and FFmpeg build. This can significantly speed up conversions.
6.  **Start Conversion**: Click "Start Batch Convert". The application will process files one by one from the main queue.
7.  **Pause/Resume**:
    - During conversion, click "Pause" to suspend the current FFmpeg process.
    - Click "Resume" to continue.
8.  **Cancel Batch**: Click "Cancel Batch" to stop all further conversions in the current batch. The currently processing file will be terminated and its partial output deleted.
9.  **Handle Failed Files**:
    - Files that fail conversion appear in the "Failed Conversions" list.
    - **Retry Failed Files**: Tries to convert failed files again using the original settings.
    - **Retry Failed (Level 1)**: Tries failed files with more error-tolerant settings.
    - **Retry Failed (Level 2)**: Tries failed files with very lax (highly compatible, lower quality) settings.
    - **Clear Failed List**: Removes all files from the failed list.
10. **Automatic MKV Folder Conversion / Monitoring (Optional)**:
    - **Select Media Folder**: Click "Select Media Folder..." in the "Automatic MKV Folder Conversion" section to choose a root directory containing your video files.
    - **Configure Interval**: Optionally, change the "Scan Interval (min)" from the default (10 minutes).
    - **Start Monitoring**: Click "Start Plex Monitoring". The application will then periodically scan the selected folder and its subfolders.
      - Non-MP4 video files (for which an MP4 version doesn't already exist) will be added to the main conversion queue.
      - The button will change to "Stop Plex Monitoring". Click it again to stop the monitoring.
      - The folder label will indicate "(Monitoring Active)".
      - The status bar will show countdowns for the next scan or current scan status.
    - **Auto-Delete Originals (Caution!)**: If you check "Automatically delete original after verified conversion", the original source file will be deleted if the conversion is successful and the output MP4 is verified (exists and is >10MB in size). This applies to files added manually or by the scanner. Use with extreme caution.
    - **Auto-Start Conversion**: Check "Automatically start conversion when scan adds files to queue" if you want the application to begin processing the queue automatically after the folder scan finds and adds new files.
11. **Status Updates**: Monitor the status bar at the bottom for overall status, queue count, individual file progress, and Plex monitoring updates. Upon batch completion, a summary message will briefly appear and its details are also recorded in the 'Logs' tab.
12. **View Logs**: Switch to the 'Logs' tab at any time to see a detailed, timestamped record of application actions, FFmpeg process details, errors, and background activities like Plex scanning.

## Output Files

Converted files will be saved in the same directory as their original MKV files:

- Standard conversion: `[original_filename_without_ext].mp4` (e.g., `MyVideo.mkv` becomes `MyVideo.mp4`)
- Level 1 Retry: `[original_filename_without_ext]_retry1.mp4`
- Level 2 Retry: `[original_filename_without_ext]_retry2.mp4`

## Building from Source (Creating an Executable)

You can create a standalone executable for Windows using PyInstaller.

1.  **Install PyInstaller and Pillow**:
    If you haven't already, install PyInstaller and Pillow (Pillow is used by PyInstaller to handle the `.png` icon conversion to `.ico` during the build). You can install them using the `requirements.txt` or manually:

    ```bash
    pip install pyinstaller Pillow
    # Or update existing requirements.txt and run:
    # pip install -r requirements.txt
    ```

2.  **Ensure FFmpeg and Icon are Present**:

    - The build process expects the `ffmpeg` directory (containing `ffmpeg.exe`, etc.) and `app_icon.png` to be in the root of the project directory (same level as `mkv_converter_gui.py`).

3.  **Generate the Spec File (One-time)**:
    Navigate to the project's root directory in your terminal and run:

    ```bash
    pyi-makespec --name MKV2MP4Converter --windowed --icon=app_icon.png --add-data "ffmpeg;ffmpeg" --add-data "app_icon.png;." mkv_converter_gui.py
    ```

    This creates `MKV2MP4Converter.spec`.

4.  **Modify the Spec File (One-time, if needed)**:
    Open `MKV2MP4Converter.spec` and ensure `psutil` is listed in `hiddenimports`:

    ```python
    # ...
    a = Analysis(
        # ...
        hiddenimports=['psutil'], # Ensure 'psutil' is here
        # ...
    )
    # ...
    ```

    The provided spec file in the repository should already have this.

5.  **Build the Executable**:
    Run PyInstaller with the spec file:

    ```bash
    pyinstaller MKV2MP4Converter.spec
    ```

6.  **Find the Executable**:
    - After a successful build, the standalone executable (`MKV2MP4Converter.exe`) and all its necessary files will be located in the `dist/MKV2MP4Converter` directory.
    - You can copy the entire `MKV2MP4Converter` folder from `dist` to another location and run the application from there.

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
