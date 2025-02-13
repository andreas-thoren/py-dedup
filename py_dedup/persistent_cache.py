"""
Persistent Cache Module

This module implements persistent caching functionality for py-dedup.
It provides functions to manage temporary files for storing the state of
duplicate file scanning (i.e. instances of DupFinder),
including creating and cleaning up cache files,
generating consistent prefixes for temporary files based on directories
being scanned, and serializing/deserializing DupFinder instances.

Functions:
    - get_temp_dir_path: Returns the path to the cache directory for the current user.
    - get_tempfile_prefix: Generates a unique prefix for temporary files
        based on provided directories.
    - create_tempfile: Creates a new temporary cache file in the cache directory.
    - get_current_tempfile: Retrieves the most recent temporary cache file that is still valid.
    - cleanup_user_tempfiles: Deletes temporary cache files.
    - pickle_dupfinder: Serializes (pickles) a DupFinder instance to a temporary file.
    - unpickle_dupfinder: Deserializes (unpickles) a DupFinder instance from a temporary file.
"""

import getpass
import os
import pathlib
import pickle
import tempfile
import hashlib
from datetime import datetime, timedelta
from typing import Iterable
from .core import DupFinder, DirectoryValidator

TMP_FILE_SUFFIX = ".pkl"


def get_temp_dir_path() -> pathlib.Path:
    """
    Returns the temporary directory path for py-dedup cache files.

    The directory is a subdirectory of the system's temporary directory
    and is named using the current user's hashed username.

    Returns:
        pathlib.Path: The path to the cache directory.
    """
    parent_dir = pathlib.Path(tempfile.gettempdir())
    username = getpass.getuser() or "unknown_user"
    user_hash = hashlib.sha256(username.encode()).hexdigest()[:16]
    return parent_dir / f"py_dedup_{user_hash}"


def get_tempfile_prefix(dirs: Iterable[pathlib.Path | str]) -> str:
    """
    Generates a unique prefix for temporary cache files based on the provided directories.

    The function resolves the directories, sorts them, and creates a hash
    from their concatenated string representation.

    Args:
        dirs (Iterable[pathlib.Path | str]): An iterable of directory paths.

    Returns:
        str: A unique prefix string for temporary files.
    """
    resolved_dirs = DirectoryValidator.get_dir_set(dirs)
    sorted_dirs = sorted(str(path) for path in resolved_dirs)
    dirs_string = "\n".join(sorted_dirs)
    prefix_hash = hashlib.sha256(dirs_string.encode()).hexdigest()[:16]
    return prefix_hash


def create_tempfile(dirs: Iterable[pathlib.Path | str]) -> pathlib.Path:
    """
    Creates a new temporary file for caching duplicate scan results.

    The temporary file is created in the user-specific cache directory.
    If the directory does not exist, it is created with permissions set to 0o700.

    Args:
        dirs (Iterable[pathlib.Path | str]): An iterable of directory paths
            associated with the cache file.

    Returns:
        pathlib.Path: The path to the newly created temporary file.
    """
    temp_dir = get_temp_dir_path()
    if not temp_dir.exists():
        temp_dir.mkdir(mode=0o700, exist_ok=False)

    prefix = get_tempfile_prefix(dirs)
    fd, file_path = tempfile.mkstemp(
        prefix=prefix, dir=temp_dir, suffix=TMP_FILE_SUFFIX
    )
    os.close(fd)
    return pathlib.Path(file_path)


def get_current_tempfile(
    dirs: Iterable[pathlib.Path | str], threshold: timedelta | None = None
) -> pathlib.Path | None:
    """
    Retrieves the most recent temporary cache file for the given directories,
    if it is still valid.

    The function searches the user-specific cache directory for files matching
    the prefix generated from the provided directories.
    If the most recent file's modification time exceeds the provided threshold
    (defaulting to 1 hour if not specified), None is returned.

    Args:
        dirs (Iterable[pathlib.Path | str]): An iterable of directory paths
            associated with the cache.
        threshold (timedelta | None): The maximum allowed age for the cache file.
            Defaults to 1 hour if None.

    Returns:
        pathlib.Path | None: The path to the valid temporary file,
            or None if no valid file exists.
    """
    tmp_files_dir = get_temp_dir_path()

    if not tmp_files_dir.exists():
        return None

    pattern = f"{get_tempfile_prefix(dirs)}*{TMP_FILE_SUFFIX}"
    tmp_files_list = [
        (tmp_file, tmp_file.stat().st_mtime) for tmp_file in tmp_files_dir.glob(pattern)
    ]

    if not tmp_files_list:
        return None

    tmp_files_list.sort(key=lambda x: x[1], reverse=True)
    mod_time = datetime.fromtimestamp(tmp_files_list[0][1])

    # Use the provided threshold, defaulting to 1 hour if None
    threshold = threshold or timedelta(hours=1)
    if (datetime.now() - mod_time) > threshold:
        tmp_file = None
    else:
        tmp_file = tmp_files_list[0][0]

    return tmp_file


def cleanup_user_tempfiles(
    dry_run: bool = False, pattern: str | None = None
) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    """
    Cleans up (deletes) temporary cache files from the user-specific cache directory.

    Optionally, a pattern can be provided to target specific files. If dry_run is True,
    the files are not actually deleted, but are reported as if they were.

    Args:
        dry_run (bool, optional): If True, simulate deletions without actually
            removing files. Defaults to False.
        pattern (str | None, optional): A glob pattern to filter which files to delete.
            Defaults to None (all files).

    Returns:
        tuple[list[pathlib.Path], list[pathlib.Path]]:
            A tuple containing two lists:
                - The first list contains paths of files that were successfully
                    (or would be) deleted.
                - The second list contains paths of files that encountered errors
                    during deletion.
    """
    temp_dir = get_temp_dir_path()
    if not temp_dir.exists():
        return [], []

    deleted_paths, error_paths = [], []
    dir_iterator = temp_dir.iterdir() if pattern is None else temp_dir.glob(pattern)

    for path in dir_iterator:
        if not path.is_file() or path.is_symlink():
            continue

        try:
            if not dry_run:
                path.unlink()
            deleted_paths.append(path)
        except FileNotFoundError:
            error_paths.append(path)
            print(f"File already deleted: {path}")
        except PermissionError:
            error_paths.append(path)
            print(f"Permission denied: {path}")
        except OSError as e:
            error_paths.append(path)
            print(f"Error deleting {path}: {e}")

    return deleted_paths, error_paths


def pickle_dupfinder(
    finder: DupFinder, path: pathlib.Path | None = None
) -> pathlib.Path:
    """
    Serializes (pickles) a DupFinder instance and writes it to a temporary cache file.

    If no path is provided, a new temporary file is created using the
        directories associated with the finder.

    Args:
        finder (DupFinder): The DupFinder instance to serialize.
        path (pathlib.Path | None, optional): The path to save the pickled object.
            If None, a new temporary file is created.

    Returns:
        pathlib.Path: The path to the file where the DupFinder instance was pickled.
    """
    if path is None:
        path = create_tempfile(finder.dirs)

    with path.open("wb") as f:
        pickle.dump(finder, f)

    return path


def unpickle_dupfinder(
    path: pathlib.Path,
) -> DupFinder | None:
    """
    Deserializes (unpickles) a DupFinder instance from the specified cache file.

    Args:
        path (pathlib.Path): The path to the cache file containing the pickled DupFinder instance.

    Returns:
        DupFinder | None: The unpickled DupFinder instance if successful; otherwise, None.
    """
    try:
        with path.open("rb") as f:
            finder = pickle.load(f)
    except (FileNotFoundError, EOFError):
        return None

    return finder
