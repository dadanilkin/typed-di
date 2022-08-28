import pytest

from typed_di import RootContext, enter_next_scope


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
