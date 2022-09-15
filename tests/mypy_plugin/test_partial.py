import re
from pathlib import Path

import mypy.api
import pytest


@pytest.fixture
def cfg_path():
    return Path(__file__).parent / "mypy.ini"


@pytest.fixture
def fn_examples_code_file():
    return Path(__file__).parent / "fixtures/partial_examples.py"


def test_reveals_correct_type(cfg_path, fn_examples_code_file):
    stdout, stderr, code = mypy.api.run(["--config-file", str(cfg_path), str(fn_examples_code_file)])

    assert stderr == ""
    assert code in (0, 1)

    lines = stdout.split("\n")[:-2]  # Strip last status message
    lines = [
        re.sub(r"^(.+ note: Revealed type is )(.*)$", lambda match: match.groups()[1], line, flags=re.MULTILINE)
        for line in lines
    ]

    assert "\n".join([""] + lines + [""]) == (
        """
"def (Union[typed_di._contexts.AppContext, typed_di._contexts.HandlerContext]) -> typing.Coroutine[Any, Any, None]"
"def (Union[typed_di._contexts.AppContext, typed_di._contexts.HandlerContext], v: builtins.str) -> typing.Coroutine[Any, Any, None]"
"def (Union[typed_di._contexts.AppContext, typed_di._contexts.HandlerContext], builtins.str) -> typing.Coroutine[Any, Any, None]"
"def (Union[typed_di._contexts.AppContext, typed_di._contexts.HandlerContext], *, v: builtins.str) -> typing.Coroutine[Any, Any, None]"
"def (Union[typed_di._contexts.AppContext, typed_di._contexts.HandlerContext], *args: builtins.str) -> typing.Coroutine[Any, Any, None]"
"def (Union[typed_di._contexts.AppContext, typed_di._contexts.HandlerContext], **kwargs: builtins.str) -> typing.Coroutine[Any, Any, None]"
"def (Union[typed_di._contexts.AppContext, typed_di._contexts.HandlerContext], v: builtins.str) -> typing.Coroutine[Any, Any, None]"
"def (Union[typed_di._contexts.AppContext, typed_di._contexts.HandlerContext], builtins.str) -> typing.Coroutine[Any, Any, None]"
"def (Union[typed_di._contexts.AppContext, typed_di._contexts.HandlerContext], *, v: builtins.str) -> typing.Coroutine[Any, Any, None]"
"def (Union[typed_di._contexts.AppContext, typed_di._contexts.HandlerContext], *args: builtins.str) -> typing.Coroutine[Any, Any, None]"
"def (Union[typed_di._contexts.AppContext, typed_di._contexts.HandlerContext], **kwargs: builtins.str) -> typing.Coroutine[Any, Any, None]"
"def (Union[typed_di._contexts.AppContext, typed_di._contexts.HandlerContext], builtins.int, val2: builtins.str, *, val3: builtins.float =) -> typing.Coroutine[Any, Any, None]"
"""
    )
