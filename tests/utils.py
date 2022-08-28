from typing import Generic, TypeVar

from typed_di import Depends

T = TypeVar("T")


class ComparableDepends(Depends[T], Generic[T]):
    def __eq__(self, other):
        return isinstance(other, Depends) and other._state == self._state
