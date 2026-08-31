Extend `src/delivery.py` with `deliver_all(channels, message)`.

Each channel object exposes `send(message)`. Attempt every channel even when one
raises. Return one result per input channel, in order, with the channel name,
success status, and an error string for failures (otherwise `None`). Do not add
external dependencies. Run the repository tests.
