import getpass
import os
import pathlib
import platform
import tempfile
import hashlib


def get_tmp_filepath() -> pathlib.Path:
    machine_id = platform.node()
    session_id = os.getpid()
    username = getpass.getuser()
    unique_id = f"{machine_id}{session_id}{username}"
    hashed_id = hashlib.sha256(unique_id.encode()).hexdigest()[:16]

    temp_dir = pathlib.Path(tempfile.gettempdir())
    temp_file_name = f"{hashed_id}_dupfinder.pkl"
    return temp_dir / temp_file_name
