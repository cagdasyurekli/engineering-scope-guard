Add `read_many(base, names)` to `src/safe_files.py`.

Return a dictionary mapping each requested relative name to its UTF-8 text.
Existing path-safety behavior must continue to apply to every name. If any name
is invalid, raise `ValueError` before reading outside the base directory. Run
the repository tests.
