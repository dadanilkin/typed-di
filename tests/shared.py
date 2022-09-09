import contextlib
import dataclasses
from typing import AsyncContextManager, AsyncIterator, ContextManager, Iterator


@dataclasses.dataclass(frozen=True)
class Foo:
    val: str


class Bar:
    ...


def sync_foo() -> Foo:
    return Foo("sync")


def cm_foo() -> ContextManager[Foo]:
    @contextlib.contextmanager
    def cm() -> Iterator[Foo]:
        yield Foo("cm")

    return cm()


async def async_foo() -> Foo:
    return Foo("async")


def async_cm_foo() -> AsyncContextManager[Foo]:
    @contextlib.asynccontextmanager
    async def cm() -> AsyncIterator[Foo]:
        yield Foo("async-cm")

    return cm()
