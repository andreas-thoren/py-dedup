import pathlib
import tomllib

TESTS_DIR = pathlib.Path(__file__).parent
TEST_DATA_DIR = TESTS_DIR / "test_data"
TEST_DIR = TEST_DATA_DIR / "test_dir"
CMPR_DIR = TEST_DATA_DIR / "cmpr_dir"
COPY_CMPR_DIR = TEST_DATA_DIR / "copy_of_cmpr_dir"

TEST_CONFIG_PATH = TESTS_DIR / "test_config.toml"
with TEST_CONFIG_PATH.open("rb") as config_file:
    test_config = tomllib.load(config_file)

MANUAL_TEST_DIR = pathlib.Path(test_config["paths"]["manual_test_dir"])

assert TEST_DATA_DIR.is_dir()
assert TEST_DIR.is_dir()
assert CMPR_DIR.is_dir()
assert COPY_CMPR_DIR.is_dir()
assert MANUAL_TEST_DIR.is_dir()

EXPECTED_DUPLICATES = frozenset(  # First level frosenset contains all duplicates
    [
        frozenset(  # Second level frozensets represents duplicate of specific size
            [
                frozenset(  # Third level frozensets represents files that are duplicates
                    [
                        TEST_DIR / "common1.txt",
                        CMPR_DIR / "common1.txt",
                    ]
                )
            ]
        ),
        frozenset(
            [
                frozenset(
                    [
                        TEST_DIR / "common_dir" / "common2.txt",
                        CMPR_DIR / "common_dir" / "common2.txt",
                    ]
                )
            ]
        ),
    ]
)
