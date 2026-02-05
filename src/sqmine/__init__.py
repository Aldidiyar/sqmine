"""sqmine: service-quality episode processing for data-mining research.

A small, dependency-free toolkit that normalises service-episode data from
heterogeneous source systems into one canonical record, pseudonymises it at the
boundary, derives reproducible features and scores inter-annotator agreement on
the labelled corpus.
"""

from sqmine.schema import SCHEMA_VERSION, Channel, Episode, Outcome, SchemaError

__version__ = "0.3.0"

__all__ = [
    "SCHEMA_VERSION",
    "Channel",
    "Episode",
    "Outcome",
    "SchemaError",
    "__version__",
]
