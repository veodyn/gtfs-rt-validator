"""The static side of a realtime run: the GTFS archive, read once, copied out.

`adapter.py` is the only module in this project that imports the sibling
`gtfs-validator`. Everything downstream consumes the plain dicts it returns.
"""

from __future__ import annotations
