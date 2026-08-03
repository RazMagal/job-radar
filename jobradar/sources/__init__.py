"""Importing this package registers every built-in source."""

from . import (  # noqa: F401
    amazon,
    amd,
    arm,
    ashby,
    avature,
    comeet,
    eightfold,
    elbit,
    google,
    greenhouse,
    iai,
    jobspy_source,
    lever,
    oracle,
    rafael,
    smartrecruiters,
    workable,
    workday,
)
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
