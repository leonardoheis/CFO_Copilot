from app.injections import configure_container
from app.injections.test import TestContainer


def pytest_configure() -> None:
    container = configure_container()
    container.override(TestContainer)
    container.wire(packages=["tests"])  # pylint: disable=no-member
