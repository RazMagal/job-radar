"""Importing this package registers every built-in source."""

from . import ashby, greenhouse, jobspy_source, lever, smartrecruiters, workday  # noqa: F401
from .base import (  # noqa: F401
    DESCRIBERS,
    REGISTRY,
    SourceError,
    get,
    get_describer,
    register,
    register_describer,
)

__all__ = [
    "DESCRIBERS",
    "REGISTRY",
    "SourceError",
    "get",
    "get_describer",
    "register",
    "register_describer",
]
