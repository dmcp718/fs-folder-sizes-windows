#!/usr/bin/env python3

"""
Folder Size Scanner - A high-performance directory size analyzer for Windows

Usage:
    folder_sizes.py --mount-point C:/path/to/scan [options]

Options:
    --mount-point PATH    Root directory path to scan (required)
    --output FILE        Output CSV file path (default: folder_sizes.csv)
    --include-hidden     Include hidden files and folders
    --workers N          Number of scanner threads (default: 8)
    --top-level         Only report sizes for top-level directories

Examples:
    # Basic scan of a directory
    folder_sizes.py --mount-point C:/Users/username/Documents

    # Scan with custom output file
    folder_sizes.py --mount-point D:/Data --output sizes.csv

    # Include hidden files and use 16 worker threads
    folder_sizes.py --mount-point E:/Backups --include-hidden --workers 16

    # Only show top-level directory sizes
    folder_sizes.py --mount-point C:/Data --top-level
"""

import os
import time
import argparse
from pathlib import Path
import csv
from dataclasses import dataclass
from typing import Dict, List, Set
import concurrent.futures
import threading
from queue import Queue, Empty
from collections import defaultdict
import stat
import ctypes
import sys

@dataclass
class ScanStats:
    total_files: int = 0
    total_dirs: int = 0
    total_size: int = 0
    start_time: float = 0
    end_time: float = 0

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def scan_rate(self) -> float:
        total_entries = self.total_files + self.total_dirs
        return total_entries / self.duration if self.duration > 0 else 0

def human_readable_size(size_bytes: int) -> str:
    """Convert bytes to human readable string."""
    if size_bytes == 0:
        return "0.00 B"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"

class BatchCounter:
    def __init__(self):
        self.files = 0
        self.dirs = 0
        self.size = 0

    def update(self, files=0, dirs=0, size=0):
        self.files += files
        self.dirs += dirs
        self.size += size

def safe_print(message: str, end='\n', file=None, flush=False):
    """Print text safely handling Unicode characters."""
    try:
        print(message, end=end, file=file, flush=flush)
    except UnicodeEncodeError:
        if file is None:
            file = sys.stdout
        buffer = file.buffer if hasattr(file, 'buffer') else file
        buffer.write(message.encode('utf-8', errors='replace'))
        if end:
            buffer.write(end.encode('utf-8'))
        if flush:
            buffer.flush()

class FolderScanner:
    def __init__(self, mount_point: str, include_hidden: bool = False, max_workers: int = None, top_level: bool = False):
        self.root = Path(mount_point).resolve()  # Use resolved path for Windows
        self.include_hidden = include_hidden
        self.max_workers = max_workers if max_workers is not None else min(32, (os.cpu_count() or 8) * 2)
        self.top_level = top_level
        self.stats = ScanStats()
        self.folder_sizes: Dict[str, int] = defaultdict(int)
        self._stats_lock = threading.Lock()
        self.work_queue = Queue()
        self.processed_dirs: Set[str] = set()
        self._running = threading.Event()

    def _should_skip(self, name: str) -> bool:
        """Check if file/directory should be skipped."""
        if not self.include_hidden:
            # Windows hidden file check
            try:
                return bool(os.stat(name).st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN)
            except:
                return name.startswith('.')
        return False

    def _process_directory(self) -> None:
        """Worker function to process directories from the queue."""
        local_counter = BatchCounter()
        local_sizes = defaultdict(int)

        while self._running.is_set():
            try:
                directory = self.work_queue.get_nowait()
            except Empty:
                if self.work_queue.empty():
                    time.sleep(0.1)
                    if self.work_queue.empty():
                        break
                continue

            try:
                # Use raw string for Windows path
                raw_dir = str(directory)
                try:
                    entries = os.scandir(raw_dir)
                except OSError as e:
                    safe_print(f"Error accessing directory {raw_dir}: {e}")
                    self.work_queue.task_done()
                    continue

                with entries:
                    dir_size = 0
                    subdirs = []

                    for entry in entries:
                        try:
                            # Get the raw entry path
                            entry_path = entry.path
                            
                            if self._should_skip(entry.name):
                                continue
                            
                            try:
                                if entry.is_file(follow_symlinks=False):
                                    try:
                                        size = entry.stat().st_size
                                        dir_size += size
                                        local_counter.update(files=1, size=size)
                                    except OSError as e:
                                        safe_print(f"Error getting size for {entry_path}: {e}")
                                elif entry.is_dir(follow_symlinks=False):
                                    subdirs.append(entry_path)
                            except OSError as e:
                                safe_print(f"Error accessing {entry_path}: {e}")
                                continue
                        except Exception as e:
                            safe_print(f"Unexpected error processing {entry.path}: {e}")
                            continue

                    # Process directories
                    for subdir in subdirs:
                        with self._stats_lock:
                            if subdir not in self.processed_dirs:
                                self.work_queue.put(subdir)
                                self.processed_dirs.add(subdir)
                                local_counter.update(dirs=1)

                    # Store directory size using raw path
                    local_sizes[raw_dir] = dir_size

                    # Update global stats periodically
                    if local_counter.files >= 1000:
                        with self._stats_lock:
                            self.stats.total_files += local_counter.files
                            self.stats.total_dirs += local_counter.dirs
                            self.stats.total_size += local_counter.size
                            for path, size in local_sizes.items():
                                self.folder_sizes[path] += size
                        local_counter = BatchCounter()
                        local_sizes.clear()

            except Exception as e:
                safe_print(f"Error processing directory {directory}: {e}")
            finally:
                self.work_queue.task_done()

        # Final update of global stats
        if local_counter.files > 0 or local_counter.dirs > 0:
            with self._stats_lock:
                self.stats.total_files += local_counter.files
                self.stats.total_dirs += local_counter.dirs
                self.stats.total_size += local_counter.size
                for path, size in local_sizes.items():
                    self.folder_sizes[path] += size

    def scan(self) -> None:
        """Perform parallel directory scanning."""
        self.stats.start_time = time.time()
        self._running.set()
        
        # Initialize queue with root directory
        root_str = str(self.root)
        self.work_queue.put(root_str)
        self.processed_dirs.add(root_str)
        
        # Start worker threads
        workers = []
        for _ in range(self.max_workers):
            worker = threading.Thread(target=self._process_directory)
            worker.daemon = True
            worker.start()
            workers.append(worker)

        # Monitor progress in main thread
        try:
            last_files = 0
            while any(w.is_alive() for w in workers):
                current_files = self.stats.total_files
                if current_files != last_files:
                    safe_print(f"Processed {current_files:,} files...", end='\r', flush=True)
                    last_files = current_files
                time.sleep(0.5)

        except KeyboardInterrupt:
            safe_print("\nStopping scan gracefully (this may take a moment)...")
            self._running.clear()
            
            # Clear the queue to prevent workers from processing more items
            while True:
                try:
                    self.work_queue.get_nowait()
                    self.work_queue.task_done()
                except Empty:
                    break

            # Wait for workers to finish their current tasks
            for w in workers:
                w.join(timeout=1.0)
            
            safe_print("Scan stopped.")
            self.stats.end_time = time.time()
            return

        finally:
            self._running.clear()
            
            # Give workers a chance to finish current tasks
            cleanup_timeout = time.time() + 2.0
            while time.time() < cleanup_timeout:
                if self.work_queue.empty() and not any(w.is_alive() for w in workers):
                    break
                time.sleep(0.1)
            
            # Clean up any remaining workers
            for w in workers:
                w.join(timeout=0.5)

        safe_print("\nCalculating directory sizes...")
        # Calculate cumulative directory sizes
        for path in sorted(self.folder_sizes.keys(), key=len, reverse=True):
            parent = str(Path(path).parent)
            if parent in self.folder_sizes:
                self.folder_sizes[parent] += self.folder_sizes[path]

        self.stats.end_time = time.time()

    def write_folder_sizes_report(self, output_file: str) -> None:
        """Write folder sizes to CSV file."""
        try:
            # Open file with UTF-8 encoding and BOM for Windows compatibility
            with open(output_file, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['Folder Path', 'Size'])
                
                # Get sorted items
                items = sorted(self.folder_sizes.items())
                
                # Filter for top-level if requested
                if self.top_level:
                    root_str = str(self.root)
                    items = [(p, s) for p, s in items if 
                            p == root_str or  # Include root
                            Path(p).parent == self.root]  # Include direct children
                
                # Write to CSV, handling potential encoding errors
                for path, size in items:
                    try:
                        if path == str(self.root):
                            rel_path = '\\'
                        else:
                            rel_path = str(Path(path).relative_to(self.root)).replace('/', '\\')
                        writer.writerow([rel_path, human_readable_size(size)])
                    except UnicodeEncodeError:
                        # Replace problematic characters
                        sanitized_path = rel_path.encode('ascii', 'replace').decode('ascii')
                        writer.writerow([sanitized_path, human_readable_size(size)])
                        # Use sys.stderr.buffer to write bytes directly
                        warning = f"Warning: Path contains unsupported characters, sanitized: {sanitized_path}\n"
                        sys.stderr.buffer.write(warning.encode('utf-8'))
                        sys.stderr.buffer.flush()
        except Exception as e:
            # Fallback to ASCII-only output if all else fails
            with open(output_file, 'w', newline='', encoding='ascii', errors='replace') as f:
                writer = csv.writer(f)
                writer.writerow(['Folder Path', 'Size'])
                for path, size in items:
                    if path == str(self.root):
                        rel_path = '\\'
                    else:
                        rel_path = str(Path(path).relative_to(self.root)).replace('/', '\\')
                    # Force ASCII encoding with replacement characters
                    safe_path = rel_path.encode('ascii', 'replace').decode('ascii')
                    writer.writerow([safe_path, human_readable_size(size)])
            print("Warning: Some characters were replaced due to encoding issues", file=sys.stderr)

    def print_summary(self) -> None:
        """Print scan summary to console."""
        safe_print("\nScan Summary:")
        safe_print(f"Total Files: {self.stats.total_files:,}")
        safe_print(f"Total Directories: {self.stats.total_dirs:,}")
        safe_print(f"Total Size: {human_readable_size(self.stats.total_size)}")
        safe_print(f"Scan Time: {self.stats.duration:.2f} seconds")
        safe_print(f"Scan Rate: {self.stats.scan_rate:.2f} entries/sec")

def main():
    parser = argparse.ArgumentParser(
        description='High-performance directory size scanner for Windows',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic scan
    folder_sizes.py --mount-point C:\\Users\\username\\Documents

    # Include hidden files with 16 workers
    folder_sizes.py --mount-point D:\\Data --include-hidden --workers 16
        """)
    
    # Get the executable's directory
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        app_dir = os.path.dirname(sys.executable)
    else:
        # Running as script
        app_dir = os.path.dirname(os.path.abspath(__file__))
    
    default_output = os.path.join(app_dir, 'folder_sizes.csv')
    
    parser.add_argument('--mount-point', required=True, 
                       help='Root path to scan')
    parser.add_argument('--output', default=default_output,
                       help=f'Output CSV file path (default: {os.path.basename(default_output)})')
    parser.add_argument('--include-hidden', action='store_true',
                       help='Include hidden files and folders')
    parser.add_argument('--workers', type=int, default=16,
                       help='Number of worker threads (default: 16)')
    parser.add_argument('--top-level', action='store_true',
                       help='Only report sizes for top-level directories')
    args = parser.parse_args()

    scanner = FolderScanner(
        args.mount_point,
        include_hidden=args.include_hidden,
        max_workers=args.workers,
        top_level=args.top_level
    )

    safe_print("\n")
    safe_print(f"Starting scan of {args.mount_point}")
    
    try:
        scanner.scan()
        scanner.print_summary()
        scanner.write_folder_sizes_report(args.output)
        safe_print(f"\nFolder sizes report written to: {args.output}")
    except KeyboardInterrupt:
        safe_print("\nScan interrupted. Writing partial results...", file=sys.stderr)
        try:
            scanner.print_summary()
            scanner.write_folder_sizes_report(args.output)
            safe_print(f"\nPartial results written to: {args.output}")
        except Exception as e:
            safe_print(f"Error writing results: {str(e)}", file=sys.stderr)
    finally:
        safe_print("")

if __name__ == '__main__':
    main()
