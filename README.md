# MKV2MP4 Converter (Batch)

## Description

This is a Python-based GUI application using Tkinter to batch convert MKV video files to MP4 format (H.264 video + AAC audio). It provides a user-friendly interface to manage a queue of files, monitor conversion progress, and handle failed conversions with multi-level retry options.

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

2.  **Add Files**: Click "Add MKV Files..." to select one or more `.mkv` files.
3.  **Manage Queue**:
    - Select a file in the main queue and click "Remove Selected" to remove it.
    - Click "Clear Queue" to remove all files from the main queue.
4.  **Start Conversion**: Click "Start Batch Convert". The application will process files one by one.
5.  **Pause/Resume**:
    - During conversion, click "Pause" to suspend the current FFmpeg process.
    - Click "Resume" to continue.
6.  **Cancel Batch**: Click "Cancel Batch" to stop all further conversions in the current batch. The currently processing file will be terminated.
7.  **Handle Failed Files**:
    - Files that fail conversion appear in the "Failed Conversions" list.
    - **Retry Failed Files**: Tries to convert failed files again using the original settings.
    - **Retry Failed (Level 1)**: Tries failed files with more error-tolerant settings.
    - **Retry Failed (Level 2)**: Tries failed files with very lax (highly compatible, lower quality) settings.
    - **Clear Failed List**: Removes all files from the failed list.
8.  **Status Updates**: Monitor the status bar at the bottom for overall status, queue count, and individual file progress.

## Output Files

Converted files will be saved in the same directory as their original MKV files with a suffix:

- Standard conversion: `_converted.mp4`
- Level 1 Retry: `_retry1.mp4`
- Level 2 Retry: `_retry2.mp4`

## License

(Consider adding a license, e.g., MIT, Apache 2.0. If you don't have one yet, you can add it later.)
For now, this is unlicensed or specify your desired license.
