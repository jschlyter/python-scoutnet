from importlib.metadata import PackageNotFoundError, version

from .client import (  # noqa
    ScoutnetClient,
    ScoutnetMailinglist,
    ScoutnetMailinglistMember,
    ScoutnetMember,
)

try:
    __version__ = version("scoutnet")
except PackageNotFoundError:
    __version__ = "0.0.0"
