# Folder Size Scanner (Windows)

A high-performance directory size analyzer for Windows. This tool scans a specified directory, calculates the size of each folder, and generates a CSV report. It uses multithreading to speed up the scanning process, making it suitable for large directories.

## Features

-   **Fast Scanning:** Utilizes multithreading to scan directories quickly.
-   **Detailed Output:** Generates a CSV report with folder paths and their sizes.
-   **Human-Readable Sizes:** Displays sizes in a human-friendly format (e.g., KB, MB, GB, TB).
-   **Progress Tracking:** Shows the number of files processed during the scan.
-   **Handles Errors:** Gracefully handles permission errors and other issues during scanning.
-   **Customizable:** Allows specifying the number of worker threads and whether to include hidden files.
-   **Interruptible:** Supports graceful interruption via Ctrl+C, saving partial results.

## Usage

```batch
folder_sizes.py --mount-point C:\path\to\scan [options]
```

### Options

-   `--mount-point PATH`: Root directory path to scan (required).
-   `--output FILE`: Output CSV file path (default: `folder_sizes.csv`).
-   `--include-hidden`: Include hidden files and folders.
-   `--workers N`: Number of scanner threads (default: 8).

### Examples

```batch
# Basic scan of a directory
folder_sizes.py --mount-point C:\Users\username\Documents

# Scan with custom output file
folder_sizes.py --mount-point D:\Data --output sizes.csv

# Include hidden files and use 16 worker threads
folder_sizes.py --mount-point E:\Backups --include-hidden --workers 16
```

## Build from Source (Windows)

You can build a standalone executable using PyInstaller:

```batch
# Install PyInstaller
pip install pyinstaller

# Build executable
build.bat

# The executable will be in dist\folder-sizes.exe
```

Note: This version is specifically optimized for Windows. For macOS, see the [macOS version](https://github.com/dmcp718/fs-folder-sizes).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
