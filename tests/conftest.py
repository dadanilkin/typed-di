from unittest.mock import patch

import pytest

from typed_di import Error, RootContext, enter_next_scope


@pytest.fixture
def root_ctx():
    return RootContext()


@pytest.fixture
async def app_ctx(root_ctx):
    async with enter_next_scope(root_ctx) as app_ctx:
        yield app_ctx


@pytest.fixture
async def handler_ctx(app_ctx):
    async with enter_next_scope(app_ctx) as handler_ctx:
        yield handler_ctx


@pytest.fixture(autouse=True, scope="session")
def make_di_exceptions_comparable():
    def new_eq(self, other):
        if not isinstance(other, type(self)):
            return NotImplemented
        return other.args == self.args

    with patch.object(Error, "__eq__", new_eq):
        yield
