import io
import pathlib
import time
from contextlib import contextmanager
from py_dedup.core import DupFinder


@contextmanager
def timer(name):
    start = time.time()
    yield
    end = time.time()
    print(f"{name} took {end - start:.2f} seconds")


def dupfinders_are_equal(finder1: DupFinder, finder2: DupFinder) -> bool:
    if finder1.chunk_size != finder2.chunk_size:
        return False
    if finder1._dirs != finder2._dirs:
        return False
    if finder1._empty_files != finder2._empty_files:
        return False
    if finder1._duplicates != finder2._duplicates:
        return False
    return True


def get_dry_run_deleted_paths(output: io.StringIO) -> set[pathlib.Path]:
    """
    Parse dry-run deletion output and return a set of deleted file paths.

    Args:
        output (io.StringIO): The output stream containing deletion log lines.

    Returns:
        set[pathlib.Path]: A set of file paths parsed from the output.
    """
    output_list = [line.strip() for line in output.getvalue().strip().split("\n")]
    deleted_files = [" ".join(line.split(" ")[3:]) for line in output_list]
    return {pathlib.Path(path) for path in deleted_files}
