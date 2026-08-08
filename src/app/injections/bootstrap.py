from functools import cache

from .production import Container


@cache
def configure_container() -> Container:
    container = Container()
    container.wire(packages=["app"])  # pylint: disable=no-member
    return container
