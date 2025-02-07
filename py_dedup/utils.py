import getpass
import os
import platform
import pathlib
import tempfile
import hashlib


def get_user_machine_specific_prefix() -> str:
    machine_id = platform.node() or "unknown_machine"
    username = getpass.getuser() or "unknown_user"
    user_machine_hash = hashlib.sha256(f"{machine_id}{username}".encode()).hexdigest()[
        :16
    ]
    return user_machine_hash


def create_tempfile(
    dir_path: str | pathlib.Path = None, suffix: str = ""
) -> pathlib.Path:

    if dir_path is None:
        dir_path = pathlib.Path(tempfile.gettempdir())
    else:
        dir_path = pathlib.Path(dir_path)

    session_id = os.getpid()
    prefix = f"{get_user_machine_specific_prefix()}_{session_id}"
    fd, file_path = tempfile.mkstemp(prefix=prefix, dir=dir_path, suffix=suffix)
    os.close(fd)
    return pathlib.Path(file_path)


def cleanup_user_machine_specific_tempfiles(
    dir_path: str | pathlib.Path = None, dry_run: bool = False
) -> tuple[list[pathlib.Path], list[pathlib.Path]]:

    if dir_path is None:
        dir_path = pathlib.Path(tempfile.gettempdir())
    else:
        dir_path = pathlib.Path(dir_path)

    if not dir_path.exists():
        raise FileNotFoundError(f"Directory does not exist: {dir_path}")

    user_machine_prefix = get_user_machine_specific_prefix()
    temp_files = dir_path.glob(f"{user_machine_prefix}_*")
    deleted_paths, error_paths = [], []

    for temp_file in temp_files:
        try:
            if not dry_run:
                temp_file.unlink()
            deleted_paths.append(temp_file)
        except FileNotFoundError:
            error_paths.append(temp_file)
            print(f"File already deleted: {temp_file}")
        except PermissionError:
            error_paths.append(temp_file)
            print(f"Permission denied: {temp_file}")
        except OSError as e:
            error_paths.append(temp_file)
            print(f"Error deleting {temp_file}: {e}")

    return deleted_paths, error_paths
