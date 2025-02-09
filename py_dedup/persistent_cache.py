import getpass
import os
import pathlib
import pickle
import tempfile
import hashlib
from typing import Iterable
from .core import DirectoryValidator, DupFinder


def get_temp_dir_path() -> pathlib.Path:
    parent_dir = pathlib.Path(tempfile.gettempdir())
    username = getpass.getuser() or "unknown_user"
    user_hash = hashlib.sha256(username.encode()).hexdigest()[:16]
    return parent_dir / f"py_dedup_{user_hash}"


def create_tempfile() -> pathlib.Path:
    temp_dir = get_temp_dir_path()
    if not temp_dir.exists():
        temp_dir.mkdir(mode=0o700, exist_ok=False)

    session_id = str(os.getpid())
    fd, file_path = tempfile.mkstemp(
        prefix=f"{session_id}_", dir=temp_dir, suffix=".pkl"
    )
    os.close(fd)
    return pathlib.Path(file_path)


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
    frozen_dir_set = frozenset(finder.dirs)

    if path is None:
        cache_dict = {}
    else:
        cache_dict = unpickle_object(path) or {}

    cache_dict[frozen_dir_set] = finder
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
