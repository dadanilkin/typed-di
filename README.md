# Typed Dependency Injection library

Типобезопасный и эргономичный DI


## IN PROGRESS

TODO list:

* [ ] tests mocks
* [ ] exceptions
* [ ] more tests
* [ ] more docs and docstrings
* [ ] polish code
* [ ] translate documentation to English


## Пример

```python
from typed_di import scoped, enter_next_scope, Depends, invoke

@scoped("app")
def app_dep() -> AsyncContextManager[Foo]: ...
def handler_dep(app_dep_: Depends[Foo] = Depends(app_dep)) -> Bar: ...

async def handler(handler_dep_: Depends[Bar] = Depends(handler_dep)) -> None:
    reveal_type(handler_dep_())  # Revealed type is `Bar`
    # Do something useful with `Bar` instance ...

root_ctx = RootContext()
async with enter_next_scope(root_ctx) as app_ctx:
    async with enter_next_scope(app_ctx) as handler_ctx:
        await invoke(handler_ctx, handler)
```

Старт приложения производится с создания корневого контекста. С его помощью происходит вход в скоуп
приложения c использованием контекстного менеджера `enter_next_scope`. Время жизни зависимостей, аннотированных как
`@scoped("app")`, будет ограничено блоком внутри `async with enter_next_scope(root_ctx)`, то есть после его закрытия
будет деинициализирован и контекстный менеджер `AsyncContextManager[Foo]` фабрики `app_dep`. Далее, т.к.
наша целевая функция `handler` зависит от зависимости скоупа хэндлера, необходим вход в следующий скоуп.
Теперь с помощью полученного `handler_ctx` можно вызывать целевую функцию вызовом `await invoke(handler_ctx, handler)`.

Внутри целевой функции значение самой зависимости можно получить через вызов инстанса `Depends[Bar]`.


## Основные фичи

1. Гарантии типобезопасности: способ связывания зависимостей и фабрик делает анализ их совместимости
   возможным на этапе статического анализа (к примеру, mypy)
2. Эргономичность: требует написания минимума кода для фабрик зависимостей, в некоторых случаях позволяет
   переиспользовать фабрики из библиотек
3. Строгий контроль времени жизни зависимостей: библиотека даёт такие же гарантии, какие имеет асинхронный контекстный
   менеджер
4. Скоупинг: время жизни зависимости может быть ограниченно как временем жизни приложения, так и временем жизни хэндлера
5. Библиотека, а не фреймворк: не накладывает никакие ограничения на среду исполнения, кроме async/await,
   также не зависит от сторонних библиотек
6. Простая интеграция в тесты: позволяет переопределить фабрики зависимостей в тестах


## Документация

### Зависимости и фабрики

Ниже показано, как можно определять фабрику, создающую зависимость, четырьмя основными способами:

```python
class Foo: ...

def foo_sync() -> Foo: ...
def foo_cm() -> ContextManager[Foo]: ...
def foo_async() -> Awaitable[Foo]: ...
def foo_async_cm() -> AsyncContextManager[Foo]: ...

async def handler(
    foo_from_sync: Depends[Foo] = Depends(foo_sync),
    foo_from_cm: Depends[Foo] = Depends(foo_cm),
    foo_from_async: Depends[Foo] = Depends(foo_async),
    foo_from_async_cm: Depends[Foo] = Depends(foo_async_cm),
) -> None: ...
```

Как можно видеть в данном примере, не смотря на способ создания, DI вызовет функцию `handler`
со всеми аргументами - инстансами класса `Foo`.

> **NOTE:** синхронные зависимости вида `(...) -> T` и `(...) -> ContextManager[T]` выполняются синхронно, без
> делегации выполнения в executor цикла событий


#### Кеширование зависимостей

Зависимости, созданные фабрикой, кешируются на время жизни скоупа, которому они принадлежат, так что
если несколько фабрик зависят от одной зависимости, все они получат один и тот же объект.


#### Гарантии типов на этапе статического анализа

Ниже показано, как конструкция `Depends(factory)` помогает избегать ошибок типов при связывании зависимостей и фабрик:

```python
class Foo: ...
class Bar: ...

def create_bar() -> Bar: ....

async def handler(
    foo: Depends[Foo] = Depends(create_bar),  # type: ignore[arg-type]
) -> None: ...
```

На этапе статического анализа типов будет выявлено несоответствие типа аргумента `foo`, который имеет тип `Depends[Foo]`
и его дефолтного значения, которое будет иметь тип `Depends[Bar], поэтому и будет выброшена ошибка, что гарантирует
типобезопасность такой системы DI.

Это главная причина, почему явное связывание фабрик и зависимостей было положено в основу данного DI.


#### Неявные фабрики

Требование о явном связывании фабрик и зависимостей может быть снято для "простых" типов, то есть тех, которые могут
использоваться вторым аргументом в вызове функции `isinsntace`, тогда связывание будет происходить по имени с проверкой
типа. Это делает использование данного DI чуть более простым и удобным тогда, когда это возможно не в ущерб гарантиям
валидности типов.

Также неявные фабрики не допускают использование `runtime_checkable` протоколов, т.к. проверка на соответствие
инстанса протоколу формальная и не предоставляет гарантий.

Неявные фабрики регистрируются при входе в скоуп через функцию `enter_next_scope` по имени,
которое затем сопоставляется с именем переменной, через которую результат этой неявной фабрики запрашивается.
Данный механизм аналогичен связыванию фикстур в pytest.

В остальном неявные фабрики полностью соответствуют явным фабрикам, они также могут иметь зависимости (явные и неявные),
также могут иметь одну из четырёх форм создания объекта.

Короткий пример:

```python
class Foo: ...

def create_foo() -> Foo: ...

async def handler(foo: Depends[Foo]) -> None: ...

async with enter_next_scope(RootContext()) as app_ctx:
    async with enter_next_scope(app_ctx, implicit_factories={"foo": create_foo}) as handler_ctx:
        await invoke(handler_ctx, handler)
```


#### Bootstrap-зависимости

Большинству приложений нужны объекты, которые определяют работу этого приложения в той или иной степени. К примеру,
часто нужен конфиг приложения с настройками БД, кешей, и т.д. Такие объекты можно передать в другие фабрики DI через
механизм bootstrap-зависимостей. Они аналогичны неявным фабрикам, т.к. также связываются по имени и также
требуют простой тип внутри `Depends`, однако передаются через передачу готовых значений в `RootContext`.

Короткий пример:

```python
class Settings: ...

async def dep(settings: Depends[Settings]) -> Foo: ...

root_ctx = RootContext(settings=Settings(...))
async with enter_next_scope(root_ctx) as app_ctx:
    ...
```


#### Скоупинг

Разделение зависимостей на зависимости уровня приложения и зависимости уровня хэндлера - одно из основных
требований к данному DI. Скоуп зависимости - это свойство фабрики зависимости, ведь только она знает,
сколько живёт объект. Поэтому объявлять скоуп предлагается через аннотацию фабрики при помощи
декораторов `@scoped("app")`/`@scoped("handler")`, при этом фабрики без аннотации по умолчанию
считаются фабриками зависимостей уровня хэндлера.

Корректный пример:

```python
@scoped("app")
def app_dep() -> int:
    return 1024

@scoped("handler")
def handler_dep(dep: Depends[int] = Depends(app_dep)) -> str:
    return str(dep())

async def handler(
    a_dep: Depends[int] = Depends(app_dep),
    h_dep: Depends[str] = Depends(handler_dep),
) -> None:
    assert a_dep() == 1024
    assert h_dep() == "1024"
```

Некорректный пример, в котором порядок скоупинга нарушен; зависимости хэндлера могут зависеть от приложения,
но не наоборот:

```python
@scoped("handler")
def handler_dep() -> int:
    return 1024

@scoped("app")
def app_dep(dep: Depends[int] = Depends(handler_dep)) -> str:
    return str(dep())

async def handler(dep: Depends[str] = Depends(app_dep)) -> None:
    assert dep() == "1024"
```


### Транзитивные зависимости

Данный DI был бы бесполезен без вложенных/рекурсивных зависимостей, в том числе зависимости `B` должно быть
полностью безразлично, как создаётся нужная ей зависимость `A`: синхронно, асинхронно, через контекстный менеджер и.т.д.

Ниже представлен исчерпывающий пример того, как можно использовать суб-зависимости в разных формах:

```python
class A: ...
@dataclass
class B:
    a: A
@dataclass
class C:
    b: B
@dataclass
class D:
    c: C

@asynccontextmanager
async def create_a() -> AsyncIterator[A]:
    yield A()

async def create_b(a: Depends[A] = Depends(create_a)) -> B:
    return B(a())

@contextmanager
def create_c(b: Depends[B] = Depends(create_b)) -> Iterator[C]:
    yield C(b())

def create_d(c: Depends[C] = Depends(create_c)) -> D:
    return D(c())

async def handler(d: Depends[D] = Depends(create_d)) -> None:
    d_ = d()
    assert isinstance(d_, D)
    assert isinstance(d_.c, C)
    assert isinstance(d_.c.b, B)
    assert isinstance(d_.c.b.a, A)
```


> **NOTE:** неявные зависимости могут создать циклические зависимости, при обнаружении таковых при создании
>  будет выброшена ошибка


## API формализовано

#### `typed_di.enter_next_scope`

```python
@overload
def enter_next_scope(
    ctx: RootContext, /, *, implicit_factories: Mapping[str, Callable[..., object]] | None = None
) -> AsyncContextManager[AppContext]: ...

@overload
def enter_next_scope(
    ctx: AppContext, /, *, implicit_factories: Mapping[str, Callable[..., object]] | None = None
) -> AsyncContextManager[HandlerContext]: ...

@overload
def enter_next_scope(
    ctx: HandlerContext, /, *, implicit_factories: Mapping[str, Callable[..., object]] | None = None
) -> AsyncContextManager[HandlerContext]: ...
```

Возвращает контекстный менеджер, который ограничивает время жизни зависимостей следующего скоупа, а также
предоставляет объект контекста следующего скоупа. Функция принимает:

1. Текущий контекст
2. Keyword-аргумент `implicit_factories` - реестр неявных фабрик


#### `typed_di.create`

```python
def create(
    ctx: AppContext | HandlerContext,
    dep_type: type[Depends[T]],
    dep_or_name: Depends[T] | str,
    /,
) -> T: ...
```

Функция для создания зависимости со всеми её вложенными зависимостями. Функция принимает:

1. Текущий контекст

    Создаваемые функции зависимости ограничены сверху передаваемым контекстом. В итоге:

    * `AppContext` - может создавать только зависимости уровня приложения и передавать bootstrap-значения
    * `HandlerContext` - может создавать любые зависимости

2. Выражение типа, как в аннотации функции после `:` (прим. `Depends[Foo]`)
3. Объект `Depends`, созданный для фабрики

    Либо имя зависимости для создания значения из неявной фабрики (со всеми ограничениями на принимающий тип `Depends`)
    или передачи bootstrap-значения


Данная функция сохраняет все гарантии по соответствию типов зависимости и фабрики, как и для обычного способа
запроса зависимостей.


#### `typed_di.invoke`

```python
async def invoke(ctx: AppContext | HandlerContext, fn: Callable[P, Awaitable[R]], /) -> R: ...
```

Вызывает переданную функцию `fn` со всеми разрешёнными зависимостями, принимает текущий контекст.


#### `typed_di.scoped`

```python
def scoped[C: Callable](scope: Literal["app", "handler"]) -> C: ...
```

Декоратор, аннотирующий фабрику как фабрику либо уровня приложения, либо как фабрику уровня хэндлера.


## Тестирование и моккинг

Для целей тестирования могут использоваться bootstrap-значения, но не всегда это удобно или возможно. Для этого
предлагается механизм подмены фабрик через первый позиционный аргумент `RootContext`, полная сигнатура конструктора:

```python
class RootContext:
    def __init__(
        self,
        override_factories: Mapping[Callable[..., object], Callable[..., object]],
        /,
        **bootstrap_values: object,
    ) -> None: ...
```

Подменить можно явные и неявные фабрики одинаковым образом. Фабрики-моки,
как и обычные фабрики, также могут запрашивать зависимости.

Эффект использования `override_factories` можно увидеть в следующем примере:

```python
foo_real = Foo(...)
foo_mock = Mock(Foo)

@scope("app")
def create_foo(...) -> Foo:
    return foo_real

def app(foo: Depends[Foo] = Depends(create_foo)) -> Foo:
    return foo()

assert invoke(RootContext(), app) is foo_real
assert invoke(RootContext({create_foo: lambda: foo_mock}), app) is foo_mock
```

Однако, подменяемые фабрики не могут быть статически типизированы (только сложными проверками в рантайме), поэтому
данный механизм предполагается к использованию **только** в тестах.


## Примеры интеграций

### FastAPI

FastAPI имеет собственный механизм внедрения зависимостей, который будет конфликтовать с данным DI. Поэтому предлагается
аннотировать хэндлеры декоратором, который отдаст на сторону FastAPI функцию с обрезанными аргументами типов 
`Depends[...]`, а внутри будет проводить магию по подстановке зависимостей, заресовленных силами данного DI.

Вход в скоуп хэндлера предлагается сделать на уровне middleware, что бы и в них иметь доступ к DI.

Кратко, интеграция с FastAPI будет выглядеть так:

```python
class DILifespan:
    def __init__(self, root_ctx: RootContext): ...
    @asynccontextmanager
    async def __call__(self, app):
        assert isinstance(app, fastapi.FastAPI)
        async with enter_next_scope(self._root_ctx) as app_ctx:
            app.ctx = app_ctx
            yield

class DIASGIMiddleware:
    def __init__(self, next_: ASGIApp): ...
    async def __call__(self, scope, receive, send):
        # Здесь пропущено игнорирования ASGI скоупа "lifespan"
        assert isinstance(app := scope.get("app"), fastapi.FastAPI)
        assert isinstance(ctx := getattr(app, "ctx", None), AppContext)
        async with enter_next_scope(ctx) as handler_ctx:
            scope["handler_ctx"] = handler_ctx
            await self._next(scope, receive, send)
            
app = FastAPI(...)
app.router.lifespan_context = DILifespan(root_ctx)

@di
async def handler(
    request: fastapi.Request,
    body: SomeModel,
    fastapi_dep: Foo = fastapi.Depends(create_foo),
    di_dep: Depends[Foo] = Depends(create_foo),
) -> int: ...
```

`DILifespan` открывает контекст приложения из `RootContext`, `DIASGIMiddleware` открывает контекст хэндлера из
`AppContext`, создаваемого в `DILifespan`. Декоратор `di`, реализация которого тут не приведена, как и было сказано
выше, будет дружить два способа подстановки зависимостей.


### Starlette

TODO


## Подводные камни

### Двойственность `Depends[Foo]` и `Depends[ContextManager[Foo]]`

Рассмотрим пример:

```python
class Foo: ...
def create_cm() -> ContextManager[Foo]: ...

def handler(
    cm_from_callable: Depends[ContextManager[Foo]] = Depends(create_cm),
    val_from_cm: Depends[Foo] = Depends(create_cm),
) -> None: ...
```

Здесь видно, что зависимость с фабрикой `create_cm` привязывается двумя разными способами: как `Depends[Foo]` и
как `Depends[ContextManager[Foo]]`. И для mypy здесь нет ошибки.

И казалось бы, тут нет особой проблемы, использование как в аргументе `cm_from_callable` едва ли кажется возможным,
однако факт возможного противоречия между типами на этапе статического анализа и типами в рантайме исключает
компромиссы. Ведь рантайме поведение достаточно прямолинейное: если из фабрики возвращается контекстный менеджер - в
него происходит "вход", если awaitable - происходит `await`, но пользователь может написать и 
`foo: Depends[Foo] = Depends(create_cm)` и `foo: Depends[ContextManager[Foo]] = Depends(create_cm)`, но во втором
варианте в рантайме вместо `ContextManager[Foo]` придёт `Foo` - что есть критическая ошибка. Ситуация ещё хуже, если
представить, что это могут быть вложенные контекстные менеджеры...

Если подробнее, проблема в том, как вычисляется `T` в конструкторе `Depends`. Он, среди прочих, принимает аргументы
типов `Callable[..., T]` и `Callable[..., ContextManager[T]]`, поэтому и возвращаемое фабрикой `create_cm` значение
может заматчиться на `T` как `ContextManager[Foo]` и как `Foo`, это зависит от значения `T` слева.

Пока решить данную проблему с точки зрения тайпинга невозможно, т.к. для этого нужно и Higher-Kinded Generics, и
пересечения типов с типами-отрицаниями. Поэтому, на данный момент, проверки вложенности будут происходить в рантайме.
Для этого будет определяться сколько уровней вложенности слева, и сколько справа; таким образом,
кол-во вложенностей справа минус кол-во вложенностей слева, если в результате 1, тогда "входим",
если 0 - отдаём как есть, всё остальные величины - ошибки тайпинга.

Все сказанное выше справедливо и для `Awaitable[T]` и для `AsyncContextManager[T]`.


### Forward-refs и `TYPE_CHECKING`

TODO

```python
if TYPE_CHECKING:
    from bar import Foo

async def do(dep: Depends[Foo]) -> Smth: ...

await invoke(handler_ctx, do)  # Exception here, can't get annotations for `do` ...
```
