import getpass
import os
import pathlib
import platform
import tempfile
import hashlib


def get_tmp_filepath(prefix: str = "", suffix: str = "") -> pathlib.Path:
    machine_id = platform.node()
    session_id = os.getpid()
    username = getpass.getuser()
    unique_id = f"{machine_id}{session_id}{username}"
    hashed_id = hashlib.sha256(unique_id.encode()).hexdigest()[:16]

    temp_dir = pathlib.Path(tempfile.gettempdir())
    temp_file_name = f"{prefix}{hashed_id}{suffix}"
    return temp_dir / temp_file_name
