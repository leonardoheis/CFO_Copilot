from functools import cache

from .production import Container
from .test import TestContainer


@cache
def configure_container() -> Container:
    container = Container()
    container.wire(packages=["app"])  # pylint: disable=no-member
    return container


__all__ = ["Container", "TestContainer", "configure_container"]
