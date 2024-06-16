from importlib.metadata import version

from .client import (  # noqa
    ScoutnetClient,
    ScoutnetMailinglist,
    ScoutnetMailinglistMember,
    ScoutnetMember,
)

__version__ = version("scoutnet")
