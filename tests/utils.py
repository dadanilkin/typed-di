import contextlib
from typing import Generic, Iterator, TypeVar

import pytest
from _pytest._code import ExceptionInfo

from typed_di import Depends
from typed_di._depends import Resolved

T = TypeVar("T")


class ComparableDepends(Depends[T], Generic[T]):
    def __eq__(self, other):
        return isinstance(other, Depends) and other._state == self._state

    @staticmethod
    def resolved(val: T) -> Depends[T]:
        d = ComparableDepends(lambda: None)
        d._state = Resolved(val)
        return d


@contextlib.contextmanager
def raises_match_by_val(exc: BaseException) -> Iterator[ExceptionInfo]:
    with pytest.raises(type(exc)) as exc_info:
        yield exc_info

    assert exc_info.value == exc
