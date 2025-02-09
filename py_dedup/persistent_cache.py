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
    parent_dir = pathlib.Path(tempfile.gettempdir())
    username = getpass.getuser() or "unknown_user"
    user_hash = hashlib.sha256(username.encode()).hexdigest()[:16]
    return parent_dir / f"py_dedup_{user_hash}"


def get_tempfile_prefix(dirs: Iterable[pathlib.Path]) -> str:
    resolved_dirs = DirectoryValidator.get_dir_set(dirs)
    sorted_dirs = sorted(str(path) for path in resolved_dirs)
    dirs_string = "\n".join(sorted_dirs)
    prefix_hash = hashlib.sha256(dirs_string.encode()).hexdigest()[:16]
    return prefix_hash


def create_tempfile(dirs: Iterable[pathlib.Path]) -> pathlib.Path:
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
    dirs: Iterable[pathlib.Path], threshold: timedelta | None = None
) -> pathlib.Path | None:
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

    # Check if modification time is more than 1 hour ago
    threshold = threshold or timedelta(hours=1)
    if (datetime.now() - mod_time) > threshold:
        tmp_file = None  # Return None if the file is older than 1 hour
    else:
        tmp_file = tmp_files_list[0][0]

    # Return current tempfile
    return tmp_file


def cleanup_user_tempfiles(
    dry_run: bool = False,
) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
    temp_dir = get_temp_dir_path()
    if not temp_dir.exists():
        return [], []

    deleted_paths, error_paths = [], []

    for path in temp_dir.iterdir():

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
    if path is None:
        path = create_tempfile(finder.dirs)

    with path.open("wb") as f:
        pickle.dump(finder, f)

    return path


def unpickle_dupfinder(
    path: pathlib.Path,
) -> DupFinder | None:
    try:
        with path.open("rb") as f:
            finder = pickle.load(f)
    except (FileNotFoundError, EOFError):
        return None

    return finder
