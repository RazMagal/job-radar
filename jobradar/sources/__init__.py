"""Importing this package registers every built-in source."""

from . import ashby, greenhouse, jobspy_source, lever, smartrecruiters, workday  # noqa: F401
from .base import REGISTRY, SourceError, get, register  # noqa: F401

__all__ = ["REGISTRY", "SourceError", "get", "register"]
