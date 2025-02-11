# py-dedup

A Python utility to **find and handle duplicate files** across one or more directories. It identifies duplicates by comparing file sizes and then verifying file content via MD5 hashing.

---

## Features

- **Find duplicate files** by size and hash checking.
- **List empty files** (0 bytes).
- **Optionally delete** duplicates in specified directories.
- **Dry-run mode** for safe testing before deletion.
- Customizable chunk size and sorting.

---

## Requirements
- Python version >= 3.11
- No external dependencies required

---

## Installation

You can install `py-dedup` using `pip` directly from the Git repository or by cloning the repository and installing it manually.

### 1. Install via `pip` from GitHub (SSH)

This is the quickest way to install `py-dedup` without cloning the repository.

```bash
pip install git+ssh://git@github.com/andreas-thoren/py-dedup.git
```

### 2. Clone the Repository and Install Manually

If you prefer to have a local copy of the repository, follow these steps:

1. **Clone** this repository or download it as a ZIP.

    ```bash
    git clone https://github.com/yourusername/py-dedup.git
    ```

2. **Navigate** to the project directory.

    ```bash
    cd py-dedup
    ```

3. **(Optional)** Create and activate a virtual environment:

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

4. **Install** the package using `pip`:

    ```bash
    pip install .
    ```

---

## Usage

Below is an example of how to use `py-dedup` to:
1. **Find duplicates** in one or more directories.
2. **Perform a dry-run** of deletions to see what would happen.
3. **Actually delete** duplicates for real.

### Example

```python
import pathlib
from py_dedup import DupFinder, DupHandler

# 1. Create a DupFinder instance, specifying one or more directories.
finder = DupFinder(
    dirs=[r"/path/to/dir1", r"/path/to/dir2"],
    chunk_size=8192,  # Optional. Default is 8192 bytes per chunk for hashing.
)

# 2. Sort and get duplicates:
finder.sort_duplicates_alphabetically()
duplicates: list[tuple[int, list[list[pathlib.Path]]]] = finder.get_size_sorted_duplicates()
# do something with duplicates...

# 3. Print duplicates and empty files:
finder.print_duplicates()  # Prints duplicates (if any) in descending order by size
print("Empty files detected:", finder.empty_files)

# 4. Create a DupHandler to manage deletions.
handler = DupHandler(finder)

# 5. --- DRY-RUN deletion ---
# This won't delete anything; it only shows which files WOULD be deleted.
deleted_files_dry_run, failed_deletions_dry_run = handler.remove_dir_duplicates(
    dirs=[r"/path/to/dir1"],  # The directory in which duplicates should be removed
    dry_run=True,             # IMPORTANT: This ensures we do not actually delete anything
)

print("Dry-run deleted files:", deleted_files_dry_run)
print("Dry-run failed deletions:", failed_deletions_dry_run)

# 6. If satisfied with the dry-run results, you can do the actual deletion:
deleted_files, failed_deletions = handler.remove_dir_duplicates(
    dirs=[r"/path/to/dir1"],
    dry_run=False,  # Now set to False for actual deletion
)

print("Actually deleted files:", deleted_files)
print("Failed deletions:", failed_deletions)
```

---

## How It Works

1. **Size Grouping**: Files are first grouped by their size. 
2. **Empty Files**: Any files of size 0 are immediately marked as empty files.
3. **MD5 Hash Check**: For each size group with more than one file, MD5 hashes are calculated to confirm exact duplicates.
4. **Duplicates Listing**: Duplicates are stored in a dictionary, keyed by file size, with each value containing lists of files sharing the same hash.
5. **Deletion**: If desired, you can use `DupHandler` to remove duplicates in a specified directory (or set of directories). A dry-run mode is available for safety.

---

## Project Structure

```
py-dedup/
│
├─ py_dedup/
│   ├─ __init__.py
│   ├─ core.py # Contains DirectoryValidator, DupFinder, DupHandler
│   ├─ cli.py    # CLI interface (work in progress)
│
├─ tests/
│   └─ ...        # Unit tests
│
├─ pyproject.toml
├─ LICENSE
├─ README.md      # This file
├─ manual_tests.py # Used for manual testing. Not necessary for end user.
```

---

## TODO

- [ ] Add cli usage examples to README.md (cli branch)
- [ ] Add docstrings to cli.py and persistent_cache.py (cli branch)
- [ ] Change datastructure of DupFinder to contain two dictionaries. One { "hash_value": dup_instance(file_size, set(file_paths)) }. The other { file_path: "hash_value" }. This so you can modify DupFinder instances easier.
- [ ] Write more tests for cli.py and persistent_cache.py 
- [ ] Write method for removing redundant dirs ex "parentdir/" and "parentdir/childdir/" could be reduced to only parentdir.
- [ ] Add gui.py

---

**License**: MIT
