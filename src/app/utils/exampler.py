import secrets
from typing import Any, Self

from polyfactory.factories.pydantic_factory import ModelFactory


def get_random_seed() -> int:
    return secrets.randbits(32)


class ExamplerMixIn:
    @classmethod
    def create_example(cls, *, seed: int | None = None, **kwargs: Any) -> Self:
        random_seed = seed or get_random_seed()

        class Factory(ModelFactory[cls]):  # type: ignore[misc]
            __random_seed__ = random_seed

        return Factory.build(**kwargs)  # type: ignore[no-any-return]

    @classmethod
    def create_examples(
        cls, count: int, *, seed: int | None = None, **kwargs: Any
    ) -> list[Self]:
        random_seed = seed or get_random_seed()

        return [
            cls.create_example(seed=random_seed + i, **kwargs) for i in range(count)
        ]
