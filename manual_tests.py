import pathlib
from py_dedup.core import DupFinder
from tests.utils_tests import timer
from tests.global_test_vars import TEST_DIR, CMPR_DIR, MANUAL_TEST_DIR


def time_dup_finder_methods(dirs):
    finder = DupFinder._for_testing(dirs=dirs)

    with timer("_collect_files_by_size"):
        size_map: dict[int, list[str]] = {}
        for dir_path in finder._dirs:
            finder._collect_files_by_size(dir_path, size_map)

    with timer("pop empty files"):
        # Pop empty files and populate _empty files attribute
        empty_files = [pathlib.Path(path) for path in size_map.pop(0, [])]
        finder._empty_files.extend(empty_files)

    with timer("get potential duplicates"):
        potential_duplicates = []
        potential_duplicates_sizes = []  # Will be needed to create duplicates dict
        for file_size in tuple(size_map.keys()):
            paths = size_map.pop(file_size)
            if (num_paths := len(paths)) > 1:
                potential_duplicates.extend(paths)
                potential_duplicates_sizes.extend([file_size] * num_paths)

    with timer("find duplicates with md5 hashing"):
        duplicates = finder._filter_potential_duplicates(
            potential_duplicates, potential_duplicates_sizes
        )
        del potential_duplicates
        del potential_duplicates_sizes

    with timer("convert duplicates to pathlib.Path instances"):
        for size_value, size_duplicates in duplicates.items():
            finder._duplicates[size_value] = [
                [pathlib.Path(path) for path in path_list]
                for path_list in size_duplicates
            ]
    
def temp_test():
    """
    Ensure the dirs property reflects what we passed in.
    """
    handler = DupFinder(dirs=[TEST_DIR, CMPR_DIR])
    # dirs property is a frozenset of resolved Paths
    # We'll check that both test_dir and cmpr_dir are in there.
    result_dirs = handler.dirs

    # Compare as Path objects (no need to cast to str)
    assert TEST_DIR.resolve() in result_dirs
    assert CMPR_DIR.resolve() in result_dirs


if __name__ == "__main__":
    time_dup_finder_methods([MANUAL_TEST_DIR])
