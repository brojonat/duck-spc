"""duck-spc: statistical process control over large Parquet datasets via DuckDB.

How I learned to stop worrying and trust statistics.
"""

from duck_spc.core import Limits, Report, Source, Stream

__all__ = ["Limits", "Report", "Source", "Stream"]
__version__ = "0.1.0"
