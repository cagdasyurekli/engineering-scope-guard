Fix the username normalization bug reported by the CLI: `Straße` and `STRASSE`
must normalize to the same value.

Preserve surrounding-whitespace removal and ensure every existing caller of the
shared normalization behavior receives the fix. Run the repository tests.
