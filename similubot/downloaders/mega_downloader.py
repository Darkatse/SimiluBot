"""MEGA downloader module for SimiluBot using MegaCMD."""
import json
import logging
import os
import re
import subprocess
import uuid
from datetime import datetime
from typing import Optional, Tuple, Dict, List, Any, Callable

from similubot.progress.base import ProgressCallback

class MegaDownloader:
    """
    Downloader for MEGA links using MegaCMD.

    Handles downloading files from MEGA links to a local directory using
    the official MEGA command-line tool (MegaCMD) for better reliability.
    """

    # Regular expression to match MEGA links
    # This pattern handles various MEGA link formats:
    # - https://mega.nz/file/ABCDEF#GHIJKLMNO (new format)
    # - https://mega.nz/#!ABCDEF!GHIJKLMNO (old format)
    # - https://mega.nz/folder/ABCDEF#GHIJKLMNO (folder links)
    MEGA_LINK_PATTERN = r'https?://mega\.nz/(?:file/[^/\s#]+(?:#[^/\s]+)?|folder/[^/\s#]+(?:#[^/\s]+)?|#!?[^/\s!]+(?:![^/\s]+)?)'

    def __init__(self, temp_dir: str = "./temp", max_files: int = 50, check_availability: bool = True):
        """
        Initialize the MEGA downloader.

        Args:
            temp_dir: Directory to store downloaded files
            max_files: Maximum number of files to keep in temp directory
            check_availability: Whether to check MegaCMD availability during initialization
        """
        self.logger = logging.getLogger("similubot.downloader.mega")
        self.temp_dir = temp_dir
        self.max_files = max_files
        self.tracker_file = os.path.join(self.temp_dir, "download_tracker.json")
        self._available = False

        # Ensure temp directory exists
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
            self.logger.debug(f"Created temporary directory: {self.temp_dir}")

        # Initialize tracking system
        self._init_tracking_system()

        # Check if MegaCMD is available (if requested)
        if check_availability:
            try:
                self._check_megacmd_availability()
                self._available = True
                self.logger.debug("Initialized MegaCMD downloader")
            except RuntimeError as e:
                self.logger.error(f"MegaCMD not available: {e}")
                self._available = False
        else:
            self.logger.info("MegaCMD availability check skipped (MEGA functionality disabled)")
            self._available = False

    def is_available(self) -> bool:
        """
        Check if MEGA downloader is available and ready to use.

        Returns:
            True if MegaCMD is available and functional, False otherwise
        """
        return self._available

    def _check_megacmd_availability(self) -> None:
        """
        Check if MegaCMD is available on the system.

        Raises:
            RuntimeError: If MegaCMD is not found or not working
        """
        try:
            # Try to run mega-version to check if MegaCMD is available
            result = subprocess.run(
                ["mega-version"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                version_info = result.stdout.strip()
                self.logger.info(f"MegaCMD found: {version_info}")
            else:
                raise RuntimeError(f"MegaCMD check failed: {result.stderr}")

        except subprocess.TimeoutExpired:
            raise RuntimeError("MegaCMD check timed out - command may be hanging")
        except FileNotFoundError:
            raise RuntimeError(
                "MegaCMD not found. Please install MegaCMD from https://mega.nz/cmd"
            )
        except Exception as e:
            raise RuntimeError(f"Error checking MegaCMD availability: {str(e)}")

    def _escape_mega_url(self, url: str) -> str:
        """
        Escape special characters in MEGA URLs for shell execution.

        Args:
            url: MEGA URL to escape

        Returns:
            Escaped URL safe for shell execution
        """
        # Escape exclamation marks for shell compatibility
        return url.replace('!', r'\!')

    def _run_megacmd_command(self, command: list, timeout: int = 300) -> Tuple[bool, str, str]:
        """
        Run a MegaCMD command and return the result.

        Args:
            command: List of command arguments
            timeout: Command timeout in seconds

        Returns:
            Tuple of (success, stdout, stderr)
        """
        try:
            self.logger.debug(f"Running MegaCMD command: {' '.join(command)}")

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.temp_dir
            )

            success = result.returncode == 0
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            if success:
                self.logger.debug(f"Command succeeded: {stdout}")
            else:
                self.logger.error(f"Command failed (code {result.returncode}): {stderr}")

            return success, stdout, stderr

        except subprocess.TimeoutExpired:
            error_msg = f"Command timed out after {timeout} seconds"
            self.logger.error(error_msg)
            return False, "", error_msg
        except Exception as e:
            error_msg = f"Error running command: {str(e)}"
            self.logger.error(error_msg)
            return False, "", error_msg

    def _run_megacmd_command_with_progress(
        self,
        command: list,
        progress_tracker,
        timeout: int = 300
    ) -> Tuple[bool, str, str]:
        """
        Run a MegaCMD command with real-time progress tracking.

        Args:
            command: List of command arguments
            progress_tracker: Progress tracker to update with output
            timeout: Command timeout in seconds

        Returns:
            Tuple of (success, stdout, stderr)
        """
        import threading
        import queue
        import time

        process = None
        stdout_thread = None
        stderr_thread = None

        try:
            self.logger.debug(f"Running MegaCMD command with progress: {' '.join(command)}")
            self.logger.debug(f"Working directory: {self.temp_dir}")

            # Start the process with improved settings
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=self.temp_dir,
                bufsize=0,  # Unbuffered for real-time output
                universal_newlines=True,
                # Ensure process doesn't inherit file descriptors
                close_fds=True
            )

            self.logger.debug(f"Started MegaCMD process with PID: {process.pid}")

            stdout_lines = []
            stderr_lines = []
            stdout_queue = queue.Queue()
            stderr_queue = queue.Queue()

            # Thread completion flags
            stdout_done = threading.Event()
            stderr_done = threading.Event()

            def read_stdout():
                """Read stdout with proper error handling and progress tracking."""
                try:
                    self.logger.debug("Starting stdout reader thread")
                    while True:
                        line = process.stdout.readline()
                        if not line:  # EOF
                            break
                        stdout_queue.put(line)
                        # Parse progress and log the line for debugging
                        self.logger.debug(f"STDOUT: {line.strip()}")
                        progress_tracker.parse_output(line)
                except Exception as e:
                    self.logger.error(f"Error in stdout reader: {e}")
                finally:
                    try:
                        process.stdout.close()
                    except:
                        pass
                    stdout_done.set()
                    self.logger.debug("Stdout reader thread finished")

            def read_stderr():
                """Read stderr with proper error handling and progress tracking."""
                try:
                    self.logger.debug("Starting stderr reader thread")
                    while True:
                        line = process.stderr.readline()
                        if not line:  # EOF
                            break
                        stderr_queue.put(line)
                        # Parse progress and log the line for debugging
                        self.logger.debug(f"STDERR: {line.strip()}")
                        progress_tracker.parse_output(line)
                except Exception as e:
                    self.logger.error(f"Error in stderr reader: {e}")
                finally:
                    try:
                        process.stderr.close()
                    except:
                        pass
                    stderr_done.set()
                    self.logger.debug("Stderr reader thread finished")

            # Start reader threads
            stdout_thread = threading.Thread(target=read_stdout, name="MegaCMD-stdout")
            stderr_thread = threading.Thread(target=read_stderr, name="MegaCMD-stderr")

            stdout_thread.daemon = True  # Ensure threads don't prevent process exit
            stderr_thread.daemon = True

            stdout_thread.start()
            stderr_thread.start()

            self.logger.debug("Started reader threads, waiting for process completion")

            # Wait for process to complete with periodic checks
            start_time = time.time()
            while process.poll() is None:
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    self.logger.warning(f"Process timeout after {elapsed:.1f} seconds, terminating")
                    process.terminate()
                    time.sleep(2)  # Give it a chance to terminate gracefully
                    if process.poll() is None:
                        self.logger.warning("Process didn't terminate, killing")
                        process.kill()
                    raise subprocess.TimeoutExpired(command, timeout)

                # Check if we're getting any output (sign of life)
                if elapsed > 30 and elapsed % 30 == 0:  # Log every 30 seconds after first 30 seconds
                    self.logger.info(f"Download still in progress... ({elapsed:.0f}s elapsed)")

                time.sleep(1)  # Check every second

            return_code = process.returncode
            self.logger.debug(f"Process completed with return code: {return_code}")

            # Wait for reader threads to finish with longer timeout
            self.logger.debug("Waiting for reader threads to finish")
            stdout_done.wait(timeout=10)
            stderr_done.wait(timeout=10)

            if stdout_thread.is_alive():
                self.logger.warning("Stdout thread still alive after timeout")
            if stderr_thread.is_alive():
                self.logger.warning("Stderr thread still alive after timeout")

            # Collect all output
            while not stdout_queue.empty():
                try:
                    stdout_lines.append(stdout_queue.get_nowait())
                except queue.Empty:
                    break

            while not stderr_queue.empty():
                try:
                    stderr_lines.append(stderr_queue.get_nowait())
                except queue.Empty:
                    break

            stdout = ''.join(stdout_lines)
            stderr = ''.join(stderr_lines)

            self.logger.debug(f"Collected {len(stdout_lines)} stdout lines, {len(stderr_lines)} stderr lines")

            success = return_code == 0

            if success:
                self.logger.info(f"MegaCMD command succeeded")
                self.logger.debug(f"Command output: {stdout}")
            else:
                self.logger.error(f"MegaCMD command failed (code {return_code})")
                self.logger.debug(f"Command stderr: {stderr}")

            return success, stdout, stderr

        except subprocess.TimeoutExpired:
            error_msg = f"Command timed out after {timeout} seconds"
            self.logger.error(error_msg)
            progress_tracker.fail(error_msg)
            return False, "", error_msg
        except Exception as e:
            error_msg = f"Error running command: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            progress_tracker.fail(error_msg)
            return False, "", error_msg
        finally:
            # Cleanup: ensure process and threads are properly terminated
            if process:
                try:
                    if process.poll() is None:
                        self.logger.debug("Terminating process in cleanup")
                        process.terminate()
                        time.sleep(1)
                        if process.poll() is None:
                            process.kill()
                except:
                    pass

            # Note: We don't forcefully join daemon threads as they'll exit with the process

    def _init_tracking_system(self) -> None:
        """
        Initialize the download tracking system.

        Creates the tracking JSON file if it doesn't exist and performs cleanup.
        """
        try:
            if not os.path.exists(self.tracker_file):
                # Create new tracking file
                initial_data = {
                    "downloads": {},
                    "metadata": {
                        "created": datetime.now().isoformat(),
                        "version": "1.0"
                    }
                }
                self._save_tracking_data(initial_data)
                self.logger.debug("Created new download tracking file")
            else:
                # Validate and clean existing tracking file
                self._cleanup_old_downloads()
                self.logger.debug("Initialized existing download tracking file")

        except Exception as e:
            self.logger.error(f"Failed to initialize tracking system: {str(e)}")
            # Create a fresh tracking file if initialization fails
            try:
                initial_data = {
                    "downloads": {},
                    "metadata": {
                        "created": datetime.now().isoformat(),
                        "version": "1.0",
                        "recovery": True
                    }
                }
                self._save_tracking_data(initial_data)
                self.logger.info("Created recovery tracking file")
            except Exception as recovery_error:
                self.logger.error(f"Failed to create recovery tracking file: {str(recovery_error)}")

    def _load_tracking_data(self) -> Dict[str, Any]:
        """
        Load tracking data from JSON file.

        Returns:
            Dictionary containing tracking data, or empty structure if file is corrupted
        """
        try:
            with open(self.tracker_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Validate structure
            if not isinstance(data, dict) or "downloads" not in data:
                raise ValueError("Invalid tracking file structure")

            return data

        except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
            self.logger.warning(f"Failed to load tracking data: {str(e)}")
            return {
                "downloads": {},
                "metadata": {
                    "created": datetime.now().isoformat(),
                    "version": "1.0",
                    "recovered": True
                }
            }

    def _save_tracking_data(self, data: Dict[str, Any]) -> None:
        """
        Save tracking data to JSON file.

        Args:
            data: Dictionary containing tracking data to save
        """
        temp_file = self.tracker_file + ".tmp"
        try:
            # Update metadata
            if "metadata" not in data:
                data["metadata"] = {}
            data["metadata"]["last_updated"] = datetime.now().isoformat()

            # Write to temporary file first, then rename for atomic operation
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Atomic rename
            os.replace(temp_file, self.tracker_file)

        except Exception as e:
            self.logger.error(f"Failed to save tracking data: {str(e)}")
            # Clean up temp file if it exists
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass

    def _cleanup_old_downloads(self) -> None:
        """
        Clean up old downloaded files and tracking entries.

        Keeps only the most recent max_files downloads and removes orphaned files.
        """
        try:
            tracking_data = self._load_tracking_data()
            downloads = tracking_data.get("downloads", {})

            if not downloads:
                return

            # Sort downloads by completion time (most recent first)
            completed_downloads = []
            for download_id, info in downloads.items():
                if info.get("status") == "completed" and info.get("completed_at"):
                    completed_downloads.append((download_id, info))

            completed_downloads.sort(key=lambda x: x[1]["completed_at"], reverse=True)

            # Keep only the most recent max_files downloads
            downloads_to_remove = completed_downloads[self.max_files:]

            # Remove old files and tracking entries
            files_removed = 0
            for download_id, info in downloads_to_remove:
                file_path = info.get("file_path")
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        files_removed += 1
                        self.logger.debug(f"Removed old download file: {os.path.basename(file_path)}")
                    except Exception as e:
                        self.logger.warning(f"Failed to remove old file {file_path}: {str(e)}")

                # Keep tracking entry for URL reference but mark as cleaned
                downloads[download_id]["status"] = "cleaned"
                downloads[download_id]["cleaned_at"] = datetime.now().isoformat()
                if "file_path" in downloads[download_id]:
                    del downloads[download_id]["file_path"]

            # Remove failed/incomplete downloads older than 24 hours
            current_time = datetime.now()
            old_entries_removed = 0
            for download_id in list(downloads.keys()):
                info = downloads[download_id]
                if info.get("status") in ["failed", "in_progress"]:
                    try:
                        started_at = datetime.fromisoformat(info["started_at"])
                        if (current_time - started_at).total_seconds() > 86400:  # 24 hours
                            file_path = info.get("file_path")
                            if file_path and os.path.exists(file_path):
                                try:
                                    os.remove(file_path)
                                except:
                                    pass
                            del downloads[download_id]
                            old_entries_removed += 1
                    except (ValueError, KeyError):
                        # Invalid timestamp, remove entry
                        del downloads[download_id]
                        old_entries_removed += 1

            # Save updated tracking data
            self._save_tracking_data(tracking_data)

            if files_removed > 0 or old_entries_removed > 0:
                self.logger.info(f"Cleanup completed: removed {files_removed} old files, {old_entries_removed} old entries")

        except Exception as e:
            self.logger.error(f"Failed to cleanup old downloads: {str(e)}")

    def is_mega_link(self, url: str) -> bool:
        """
        Check if a URL is a valid MEGA link.

        Args:
            url: URL to check

        Returns:
            True if the URL is a valid MEGA link, False otherwise
        """
        is_valid = bool(re.match(self.MEGA_LINK_PATTERN, url))
        self.logger.debug(f"MEGA link validation: {url} -> {'Valid' if is_valid else 'Invalid'}")
        return is_valid

    def extract_mega_links(self, text: str) -> list:
        """
        Extract MEGA links from text.

        Args:
            text: Text to extract links from

        Returns:
            List of MEGA links found in the text
        """
        return re.findall(self.MEGA_LINK_PATTERN, text)

    def download(self, url: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Download a file from a MEGA link using MegaCMD with robust tracking.

        This method uses a JSON-based tracking system to reliably identify
        downloaded files, handle multiple files, and manage cleanup.

        Args:
            url: MEGA link to download

        Returns:
            Tuple containing:
                - Success status (True/False)
                - Path to downloaded file if successful, None otherwise
                - Error message if failed, None otherwise
        """
        if not self.is_mega_link(url):
            error_msg = f"Invalid MEGA link: {url}"
            self.logger.error(error_msg)
            return False, None, error_msg

        # Generate unique download ID
        download_id = str(uuid.uuid4())

        # Load tracking data
        tracking_data = self._load_tracking_data()
        downloads = tracking_data.get("downloads", {})

        # Record download start
        download_info = {
            "url": url,
            "download_id": download_id,
            "started_at": datetime.now().isoformat(),
            "status": "in_progress"
        }
        downloads[download_id] = download_info
        self._save_tracking_data(tracking_data)

        try:
            self.logger.info(f"Downloading file from MEGA: {url} (ID: {download_id})")
            self.logger.debug(f"Download destination: {self.temp_dir}")

            # Get list of files before download
            files_before = set()
            try:
                files_before = {f for f in os.listdir(self.temp_dir)
                              if os.path.isfile(os.path.join(self.temp_dir, f)) and f != "download_tracker.json"}
            except OSError:
                pass

            # Escape the URL for shell execution
            escaped_url = self._escape_mega_url(url)

            # Use mega-get to download the file
            # Specify destination directory to ensure file goes to the right place
            command = ["mega-get", escaped_url]
            success, stdout, stderr = self._run_megacmd_command(command, timeout=1200)

            if not success:
                error_msg = f"MegaCMD download failed: {stderr}"
                self.logger.error(error_msg)

                # Update tracking data with failure
                downloads[download_id]["status"] = "failed"
                downloads[download_id]["error"] = error_msg
                downloads[download_id]["failed_at"] = datetime.now().isoformat()
                self._save_tracking_data(tracking_data)

                return False, None, error_msg

            # Find newly downloaded files
            files_after = set()
            try:
                files_after = {f for f in os.listdir(self.temp_dir)
                             if os.path.isfile(os.path.join(self.temp_dir, f)) and f != "download_tracker.json"}
            except OSError:
                files_after = set()

            new_files = files_after - files_before

            if not new_files:
                error_msg = "Download completed but no new files found in temp directory"
                self.logger.error(error_msg)

                # Update tracking data with failure
                downloads[download_id]["status"] = "failed"
                downloads[download_id]["error"] = error_msg
                downloads[download_id]["failed_at"] = datetime.now().isoformat()
                self._save_tracking_data(tracking_data)

                return False, None, error_msg

            # Handle multiple files (take the largest one, likely the main file)
            if len(new_files) > 1:
                self.logger.warning(f"Multiple files downloaded: {list(new_files)}")

            # Select the downloaded file (largest if multiple)
            file_sizes = {}
            for filename in new_files:
                file_path = os.path.join(self.temp_dir, filename)
                try:
                    file_sizes[filename] = os.path.getsize(file_path)
                except OSError:
                    file_sizes[filename] = 0

            selected_filename = max(file_sizes.keys(), key=lambda f: file_sizes[f])
            file_path = os.path.join(self.temp_dir, selected_filename)

            if not os.path.exists(file_path):
                error_msg = "Download failed: Selected file not found after download"
                self.logger.error(error_msg)

                # Update tracking data with failure
                downloads[download_id]["status"] = "failed"
                downloads[download_id]["error"] = error_msg
                downloads[download_id]["failed_at"] = datetime.now().isoformat()
                self._save_tracking_data(tracking_data)

                return False, None, error_msg

            file_size = os.path.getsize(file_path)
            self.logger.info(f"Download successful: {os.path.basename(file_path)} ({file_size} bytes)")

            # Update tracking data with success
            downloads[download_id]["status"] = "completed"
            downloads[download_id]["filename"] = selected_filename
            downloads[download_id]["file_path"] = file_path
            downloads[download_id]["file_size"] = file_size
            downloads[download_id]["completed_at"] = datetime.now().isoformat()

            # Record all downloaded files if multiple
            if len(new_files) > 1:
                downloads[download_id]["all_files"] = list(new_files)

            self._save_tracking_data(tracking_data)

            return True, file_path, None

        except Exception as e:
            error_msg = f"Download failed: {str(e)}"
            self.logger.error(error_msg, exc_info=True)

            # Update tracking data with failure
            try:
                downloads[download_id]["status"] = "failed"
                downloads[download_id]["error"] = error_msg
                downloads[download_id]["failed_at"] = datetime.now().isoformat()
                self._save_tracking_data(tracking_data)
            except:
                pass  # Don't let tracking errors mask the original error

            return False, None, error_msg

    def download_with_progress(
        self,
        url: str,
        progress_callback: Optional[ProgressCallback] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Download a file from a MEGA link with real-time progress tracking.

        Args:
            url: MEGA link to download
            progress_callback: Optional callback function for progress updates

        Returns:
            Tuple containing:
                - Success status (True/False)
                - Path to downloaded file if successful, None otherwise
                - Error message if failed, None otherwise
        """
        if not self.is_mega_link(url):
            error_msg = f"Invalid MEGA link: {url}"
            self.logger.error(error_msg)
            return False, None, error_msg

        # Import here to avoid circular imports
        from similubot.progress.mega_tracker import MegaProgressTracker

        # Create progress tracker
        progress_tracker = MegaProgressTracker()
        if progress_callback:
            progress_tracker.add_callback(progress_callback)

        # Generate unique download ID
        download_id = str(uuid.uuid4())

        # Load tracking data
        tracking_data = self._load_tracking_data()
        downloads = tracking_data.get("downloads", {})

        # Record download start
        download_info = {
            "url": url,
            "download_id": download_id,
            "started_at": datetime.now().isoformat(),
            "status": "in_progress"
        }
        downloads[download_id] = download_info
        self._save_tracking_data(tracking_data)

        # Start progress tracking
        progress_tracker.start()

        try:
            self.logger.info(f"Downloading file from MEGA: {url} (ID: {download_id})")
            self.logger.debug(f"Download destination: {self.temp_dir}")

            # Get list of files before download
            files_before = set()
            try:
                files_before = {f for f in os.listdir(self.temp_dir)
                              if os.path.isfile(os.path.join(self.temp_dir, f)) and f != "download_tracker.json"}
            except OSError:
                pass

            # Escape the URL for shell execution
            escaped_url = self._escape_mega_url(url)

            # Use mega-get to download the file with progress tracking
            # Specify destination directory to ensure file goes to the right place
            command = ["mega-get", escaped_url]
            success, stdout, stderr = self._run_megacmd_command_with_progress(
                command, progress_tracker, timeout=1200
            )

            if not success:
                error_msg = f"MegaCMD download failed: {stderr}"
                self.logger.error(error_msg)

                # Update tracking data with failure
                downloads[download_id]["status"] = "failed"
                downloads[download_id]["error"] = error_msg
                downloads[download_id]["failed_at"] = datetime.now().isoformat()
                self._save_tracking_data(tracking_data)

                progress_tracker.fail(error_msg)
                return False, None, error_msg

            # Find newly downloaded files
            files_after = set()
            try:
                files_after = {f for f in os.listdir(self.temp_dir)
                             if os.path.isfile(os.path.join(self.temp_dir, f)) and f != "download_tracker.json"}
            except OSError:
                files_after = set()

            new_files = files_after - files_before

            if not new_files:
                error_msg = "Download completed but no new files found in temp directory"
                self.logger.error(error_msg)

                # Update tracking data with failure
                downloads[download_id]["status"] = "failed"
                downloads[download_id]["error"] = error_msg
                downloads[download_id]["failed_at"] = datetime.now().isoformat()
                self._save_tracking_data(tracking_data)

                progress_tracker.fail(error_msg)
                return False, None, error_msg

            # Handle multiple files (take the largest one, likely the main file)
            if len(new_files) > 1:
                self.logger.warning(f"Multiple files downloaded: {list(new_files)}")

            # Select the downloaded file (largest if multiple)
            file_sizes = {}
            for filename in new_files:
                file_path = os.path.join(self.temp_dir, filename)
                try:
                    file_sizes[filename] = os.path.getsize(file_path)
                except OSError:
                    file_sizes[filename] = 0

            selected_filename = max(file_sizes.keys(), key=lambda f: file_sizes[f])
            file_path = os.path.join(self.temp_dir, selected_filename)

            if not os.path.exists(file_path):
                error_msg = "Download failed: Selected file not found after download"
                self.logger.error(error_msg)

                # Update tracking data with failure
                downloads[download_id]["status"] = "failed"
                downloads[download_id]["error"] = error_msg
                downloads[download_id]["failed_at"] = datetime.now().isoformat()
                self._save_tracking_data(tracking_data)

                progress_tracker.fail(error_msg)
                return False, None, error_msg

            file_size = os.path.getsize(file_path)
            self.logger.info(f"Download successful: {os.path.basename(file_path)} ({file_size} bytes)")

            # Update tracking data with success
            downloads[download_id]["status"] = "completed"
            downloads[download_id]["filename"] = selected_filename
            downloads[download_id]["file_path"] = file_path
            downloads[download_id]["file_size"] = file_size
            downloads[download_id]["completed_at"] = datetime.now().isoformat()

            # Record all downloaded files if multiple
            if len(new_files) > 1:
                downloads[download_id]["all_files"] = list(new_files)

            self._save_tracking_data(tracking_data)

            # Complete progress tracking
            progress_tracker.complete(f"Downloaded {os.path.basename(file_path)} ({file_size} bytes)")
            return True, file_path, None

        except Exception as e:
            error_msg = f"Download failed: {str(e)}"
            self.logger.error(error_msg, exc_info=True)

            # Update tracking data with failure
            try:
                downloads[download_id]["status"] = "failed"
                downloads[download_id]["error"] = error_msg
                downloads[download_id]["failed_at"] = datetime.now().isoformat()
                self._save_tracking_data(tracking_data)
            except:
                pass  # Don't let tracking errors mask the original error

            progress_tracker.fail(error_msg)
            return False, None, error_msg

    def get_file_info(self, url: str) -> Tuple[bool, Optional[dict], Optional[str]]:
        """
        Get information about a file from a MEGA link without downloading it.

        Args:
            url: MEGA link to get information for

        Returns:
            Tuple containing:
                - Success status (True/False)
                - File info dictionary if successful, None otherwise
                - Error message if failed, None otherwise
        """
        if not self.is_mega_link(url):
            error_msg = f"Invalid MEGA link: {url}"
            self.logger.error(error_msg)
            return False, None, error_msg

        try:
            self.logger.info(f"Getting file info from MEGA: {url}")

            # Escape the URL for shell execution
            escaped_url = self._escape_mega_url(url)

            # Use mega-ls to get file information
            # Note: mega-ls on a public link shows basic file info
            command = ["mega-ls", escaped_url]
            success, stdout, stderr = self._run_megacmd_command(command, timeout=30)

            if not success:
                error_msg = f"Failed to get file info: {stderr}"
                self.logger.error(error_msg)
                return False, None, error_msg

            if not stdout:
                error_msg = "No file information returned"
                self.logger.error(error_msg)
                return False, None, error_msg

            # Parse the output to extract file information
            # MegaCMD ls output format varies, but typically shows filename and size
            lines = stdout.strip().split('\n')
            file_info = {}

            for line in lines:
                line = line.strip()
                if line and not line.startswith('FILENAME') and not line.startswith('---'):
                    # Try to extract filename and size from the line
                    # Format is typically: filename    size    date
                    parts = line.split()
                    if len(parts) >= 2:
                        # First part is usually filename, second part might be size
                        file_info['name'] = parts[0]
                        # Try to parse size if it looks like a number or has size units
                        for part in parts[1:]:
                            if any(unit in part.upper() for unit in ['B', 'KB', 'MB', 'GB', 'TB']):
                                file_info['size_str'] = part
                                break
                            elif part.replace(',', '').replace('.', '').isdigit():
                                try:
                                    # Try to parse as integer (remove commas but keep decimal point for float)
                                    if '.' in part:
                                        file_info['size_bytes'] = int(float(part.replace(',', '')))
                                    else:
                                        file_info['size_bytes'] = int(part.replace(',', ''))
                                except ValueError:
                                    # If parsing fails, just store as string
                                    file_info['size_str'] = part
                                break
                    break

            if not file_info:
                # If parsing failed, just return the raw output
                file_info = {'raw_output': stdout}

            self.logger.info(f"File info retrieved successfully")
            self.logger.debug(f"File info: {file_info}")

            return True, file_info, None

        except Exception as e:
            error_msg = f"Failed to get file info: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return False, None, error_msg

    def get_download_history(self, limit: int = 10) -> Dict[str, Any]:
        """
        Get recent download history from tracking data.

        Args:
            limit: Maximum number of downloads to return

        Returns:
            Dictionary containing download history and statistics
        """
        try:
            tracking_data = self._load_tracking_data()
            downloads = tracking_data.get("downloads", {})

            # Sort downloads by start time (most recent first)
            sorted_downloads = []
            for download_id, info in downloads.items():
                if "started_at" in info:
                    sorted_downloads.append((download_id, info))

            sorted_downloads.sort(key=lambda x: x[1]["started_at"], reverse=True)

            # Get recent downloads
            recent_downloads = sorted_downloads[:limit]

            # Calculate statistics
            total_downloads = len(downloads)
            completed_count = sum(1 for _, info in downloads.items() if info.get("status") == "completed")
            failed_count = sum(1 for _, info in downloads.items() if info.get("status") == "failed")
            in_progress_count = sum(1 for _, info in downloads.items() if info.get("status") == "in_progress")

            # Calculate total size of completed downloads
            total_size = sum(info.get("file_size", 0) for _, info in downloads.items()
                           if info.get("status") == "completed")

            return {
                "recent_downloads": [
                    {
                        "download_id": download_id,
                        "url": info.get("url", ""),
                        "filename": info.get("filename", ""),
                        "status": info.get("status", "unknown"),
                        "started_at": info.get("started_at", ""),
                        "completed_at": info.get("completed_at", ""),
                        "file_size": info.get("file_size", 0),
                        "error": info.get("error", "")
                    }
                    for download_id, info in recent_downloads
                ],
                "statistics": {
                    "total_downloads": total_downloads,
                    "completed": completed_count,
                    "failed": failed_count,
                    "in_progress": in_progress_count,
                    "total_size_bytes": total_size
                },
                "metadata": tracking_data.get("metadata", {})
            }

        except Exception as e:
            self.logger.error(f"Failed to get download history: {str(e)}")
            return {
                "recent_downloads": [],
                "statistics": {
                    "total_downloads": 0,
                    "completed": 0,
                    "failed": 0,
                    "in_progress": 0,
                    "total_size_bytes": 0
                },
                "metadata": {},
                "error": str(e)
            }
