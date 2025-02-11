import pathlib
import unittest
from py_dedup.persistent_cache import *
from tests.global_test_vars import (
    TEST_DIR,
    CMPR_DIR,
    COPY_CMPR_DIR
)


class TestPersistentCache(unittest.TestCase):
    def test_get_tempfile_prefix(self):
        cwd = pathlib.Path.cwd()
        absolute_paths = [TEST_DIR, CMPR_DIR, COPY_CMPR_DIR]
        relative_paths = [ path.relative_to(cwd) for path in absolute_paths ]
        parent_paths = [ path.parent for path in relative_paths ]
        reverse_paths = relative_paths[::-1]

        prefix_absolute = get_tempfile_prefix(absolute_paths)
        prefix_relative = get_tempfile_prefix(relative_paths)
        prefix_parents = get_tempfile_prefix(parent_paths)
        prefix_reversed = get_tempfile_prefix(reverse_paths)

        # Same prefix is expected no matter if paths are relative or absolute
        self.assertEqual(prefix_absolute, prefix_relative)
        
        # Same prefix is expected no matter the order
        self.assertEqual(prefix_absolute, prefix_reversed)
        
        # Different actual dirs should result in different prefixes
        self.assertNotEqual(prefix_relative, prefix_parents)


if __name__ == "__main__":
    unittest.main()
