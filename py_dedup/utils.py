import getpass
import os
import pathlib
import tempfile
import hashlib


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
