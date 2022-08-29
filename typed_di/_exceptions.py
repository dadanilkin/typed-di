from __future__ import annotations

from typing import Iterable, Literal, Mapping, Sequence, TypeAlias

from typed_di import _depends


class Error(Exception):
    pass


CreationType: TypeAlias = Literal["explicit", "implicit", "bootstrap", "implicit-or-bootstrap"]


class CreationError(Error):
    def __init__(
        self,
        dep_type: type[_depends.Depends[object]],
        dep_or_name: _depends.Depends[object] | str,
        creation_type: CreationType,
        *args: object,
    ) -> None:
        super().__init__(dep_type, dep_or_name, creation_type, *args)
        self.dep_type = dep_type
        self.dep_or_name = dep_or_name
        self.creation_type = creation_type


class DependencyByNameNotFound(CreationError, LookupError):
    def __init__(
        self,
        dep_type: type[_depends.Depends[object]],
        dep_or_name: str,
        creation_type: CreationType,
    ) -> None:
        super().__init__(dep_type, dep_or_name, creation_type)


class ValueOfUnexpectedTypeReceived(CreationError, TypeError):
    def __init__(
        self,
        dep_type: type[_depends.Depends[object]],
        dep_or_name: _depends.Depends[object] | str,
        creation_type: CreationType,
        val_type: type[object],
        actual_type: type[object],
    ) -> None:
        super().__init__(dep_type, dep_or_name, creation_type, val_type, actual_type)
        self.val_type = val_type
        self.actual_type = actual_type


class HandlerScopeDepRequestedFromAppScope(CreationError, RuntimeError):
    ...


class ValueFromFactoryAlreadyResolved(CreationError, RuntimeError):
    def __init__(
        self,
        dep_type: type[_depends.Depends[object]],
        dep_or_name: _depends.Depends[object] | str,
        creation_type: CreationType,
        requested_as: object,
        factory: object,
    ) -> None:
        super().__init__(dep_type, dep_or_name, creation_type, requested_as, factory)


class ValueFromFactoryWereRequestedUnresolved(CreationError, RuntimeError):
    def __init__(
        self,
        dep_type: type[_depends.Depends[object]],
        dep_or_name: _depends.Depends[object] | str,
        creation_type: CreationType,
        requested_as: object,
        factory: object,
    ) -> None:
        super().__init__(dep_type, dep_or_name, creation_type, requested_as, factory)


class InvokeError(Error):
    def __init__(self, invokable: object, *args: object, fn_overridden: object | None = None) -> None:
        super().__init__(invokable, *(args + (fn_overridden,) if fn_overridden else ()))
        self.invokable = invokable
        self.fn_overridden = fn_overridden


class InvalidInvokableFunction(InvokeError, ValueError):
    def __init__(
        self, invokable: object, args_errs: Mapping[str, Sequence[str]], fn_overridden: object | None = None
    ) -> None:
        super().__init__(invokable, args_errs, fn_overridden=fn_overridden)
        self.args_errs = args_errs

    def __repr__(self) -> str:
        def render_arg_errs(errs: Iterable[str]) -> str:
            return "\n".join(f"\t{err}" for err in errs)

        args_errs_rendered = "\n".join(
            f"{arg_name}:\n{render_arg_errs(arg_errs)}" for arg_name, arg_errs in self.args_errs.items()
        )
        return f"Could not invoke function `{self.invokable!r}` due to args annotations errors:\n{args_errs_rendered}\n"


class NestedInvokeError(InvokeError, RuntimeError):
    def __init__(
        self,
        invokable: object,
        invoke_err: InvokableDependencyError | NestedInvokeError | InvalidInvokableFunction,
        fn_overridden: object | None = None,
    ) -> None:
        super().__init__(invokable, invoke_err, fn_overridden=fn_overridden)
        self.invoke_err = invoke_err


class InvokableDependencyError(InvokeError, RuntimeError):
    def __init__(self, invokable: object, dep_err: CreationError, fn_overridden: object | None = None) -> None:
        super().__init__(invokable, dep_err, fn_overridden=fn_overridden)
        self.dep_err = dep_err
