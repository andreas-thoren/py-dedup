import getpass
import os
import pathlib
import pickle
import tempfile
import hashlib
from datetime import datetime, timedelta
from typing import Iterable
from .core import DirectoryValidator, DupFinder


TMP_FILE_SUFFIX = ".pkl"


def get_temp_dir_path() -> pathlib.Path:
    parent_dir = pathlib.Path(tempfile.gettempdir())
    username = getpass.getuser() or "unknown_user"
    user_hash = hashlib.sha256(username.encode()).hexdigest()[:16]
    return parent_dir / f"py_dedup_{user_hash}"


def get_tempfile_prefix() -> str:
    session_id = str(os.getpid())
    return f"{session_id}_"


def create_tempfile() -> pathlib.Path:
    temp_dir = get_temp_dir_path()
    if not temp_dir.exists():
        temp_dir.mkdir(mode=0o700, exist_ok=False)

    prefix = get_tempfile_prefix()
    fd, file_path = tempfile.mkstemp(
        prefix=prefix, dir=temp_dir, suffix=TMP_FILE_SUFFIX
    )
    os.close(fd)
    return pathlib.Path(file_path)


def get_current_tempfile(threshold: timedelta | None = None) -> pathlib.Path | None:
    tmp_files_dir = get_temp_dir_path()

    if not tmp_files_dir.exists():
        return None

    pattern = f"{get_tempfile_prefix()}*{TMP_FILE_SUFFIX}"
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

    if tmp_file is None or len(tmp_files_list) > 1:
        print(
            f"There are old tempfiles in dir: {tmp_files_dir}"
            + "Please consider cleaning them up"  # TODO rephrase after creatinig cli purge-temfiles
        )

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


def read_cache(path: pathlib.Path, dirs: Iterable) -> DupFinder | None:
    dir_set = DirectoryValidator.get_dir_set(dirs)
    cache_dict = unpickle_object(path) or {}
    # If there is a cached dupfinder for the same operation return it otherwise None
    return cache_dict.get(frozenset(dir_set), None)


def update_cache(
    finder: DupFinder, path: pathlib.Path | None = None
) -> tuple[dict[frozenset[pathlib.Path], DupFinder], pathlib.Path]:

    if path is None:
        cache_dict = {}
    else:
        cache_dict = unpickle_object(path) or {}

    # finder.dirs is a property that returns frozenset of finder._dirs
    cache_dict[finder.dirs] = finder
    cache_path = pickle_object(cache_dict, path)
    return cache_dict, cache_path


def pickle_object(obj: object, path: pathlib.Path | None = None) -> pathlib.Path:
    if path is None:
        path = create_tempfile()

    with path.open("wb") as f:
        pickle.dump(obj, f)

    return path


def unpickle_object(
    path: pathlib.Path,
) -> dict[frozenset[pathlib.Path], DupFinder] | None:
    try:
        with path.open("rb") as f:
            obj = pickle.load(f)
    except (FileNotFoundError, EOFError):
        return None

    return obj
