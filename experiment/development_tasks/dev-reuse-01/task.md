Add `find_record(records, name)` to `src/exporter.py`.

It must return the first record whose `name` is canonically equal to the query,
or `None` when no record matches. Canonical matching ignores surrounding
whitespace, letter case, and runs of non-alphanumeric separators. Keep the
canonicalization behavior centralized and run the repository tests.
