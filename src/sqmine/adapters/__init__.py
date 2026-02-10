"""Source adapters. Importing this package registers the built-in adapters."""

from sqmine.adapters.base import (
    LoadResult,
    Reject,
    SourceAdapter,
    available_adapters,
    get_adapter,
    register_adapter,
)
from sqmine.adapters.contact_centre_json import ContactCentreJsonAdapter
from sqmine.adapters.crm_csv import CrmCsvAdapter

__all__ = [
    "ContactCentreJsonAdapter",
    "CrmCsvAdapter",
    "LoadResult",
    "Reject",
    "SourceAdapter",
    "available_adapters",
    "get_adapter",
    "register_adapter",
]
