# SPDX-License-Identifier: EUPL-1.2

from __future__ import annotations

import collections
import io
import multiprocessing
import multiprocessing.connection
import sys
import typing

from collections.abc import Iterable
from types import TracebackType
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

import rich.columns
import rich.console
import rich.padding
import rich.panel
import rich.progress
import rich.traceback


__version__ = '0.0.1'


_Task = collections.namedtuple('_Task', ['name', 'func', 'isolated'])


Executor = Callable[[List[_Task]], bool]


def _sequencial_executor(tasks: List[_Task]) -> bool:
    console = rich.console.Console()
    result_columns = rich.columns.Columns()
    fail = False
    for task in tasks:
        console.print(f'[bold dark_orange]> executing {task.name}')
        result = rich.panel.Panel('', title=f'[bold]{task.name}')
        try:
            task.func()
        except Exception:
            exc_type, exc_value, tb = sys.exc_info()
            assert exc_type and exc_value
            console.print(rich.traceback.Traceback.from_exception(
                exc_type,
                exc_value,
                tb.tb_next if tb else tb,
            ))
            console.print(f"[bold red]error executing '{task.name}'!")
            result.renderable = 'failed'
            result.style = 'red'
        else:
            result.renderable = 'success'
            result.style = 'green'
            fail = True
        result_columns.add_renderable(result)
    console.print(result_columns)
    return fail


_Traceback = Tuple[
    Optional[Type[BaseException]],
    Optional[BaseException],
    Optional[TracebackType],
]


class _ProcessPool:
    def __init__(self) -> None:
        self._pool: Dict[str, Tuple[
            multiprocessing.Process,
            multiprocessing.Queue[str],
            multiprocessing.Queue[_Traceback],
        ]] = {}
        self._ready: multiprocessing.Queue[str] = multiprocessing.Queue()

    def submit(
        self,
        name: str,
        func: Callable[..., None],
        args: Optional[Tuple[Any, ...]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        queue_out: multiprocessing.Queue[str] = multiprocessing.Queue()
        queue_exc: multiprocessing.Queue[_Traceback] = multiprocessing.Queue()
        console = rich.console.Console()
        process = multiprocessing.Process(
            target=self._process_entry,
            args=(name, func, args or [], kwargs or {}, queue_out, queue_exc, console),
        )
        process.start()
        self._pool[name] = process, queue_out, queue_exc

    def _process_entry(
        self,
        name: str,
        func: Callable[..., None],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        queue_out: multiprocessing.Queue[str],
        queue_exc: multiprocessing.Queue[_Traceback],
        console: rich.console.Console,
    ) -> None:
        with io.StringIO() as out:
            sys.stdout, sys.stderr = out, out
            try:
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    exc_type, exc_value, tb = sys.exc_info()
                    assert exc_type and exc_value
                    console.print(rich.traceback.Traceback.from_exception(
                        exc_type,
                        exc_value,
                        tb.tb_next if tb else tb,
                    ))
                    raise e
            finally:
                queue_out.put(out.getvalue())
                self._ready.put(name)

    def as_completed(self) -> Iterable[Tuple[
        str,
        multiprocessing.Process,
        str,
        Optional[_Traceback],
    ]]:
        while True:
            name = self._ready.get()

            process, queue_out, queue_exc = self._pool[name]

            process.join()
            if not queue_exc.empty():
                exc: Optional[_Traceback] = queue_exc.get_nowait()
            else:
                exc = None
            yield name, process, queue_out.get(), exc

            del self._pool[name]
            if not self._pool:  # no pending tasks
                break


class _ProgressWithResults(rich.progress.Progress):
    def __init__(
        self,
        *args: Any,
        result_columns: Optional[rich.columns.Columns] = None,
        **kwargs: Any,
    ) -> None:
        self.result_columns = typing.cast(rich.console.ConsoleRenderable, result_columns)
        super().__init__(*args, **kwargs)

    def get_renderables(self) -> Iterable[rich.console.RenderableType]:
        yield self.result_columns
        table = self.make_tasks_table(self.tasks)
        yield table


def _parallel_executor(tasks: List[_Task]) -> bool:
    result_columns = rich.columns.Columns()
    results: Dict[str, rich.panel.Panel] = {}
    fail = False

    with _ProgressWithResults(
        rich.progress.SpinnerColumn(spinner_name='point'),
        '[bold blue]{task.description}',
        rich.progress.BarColumn(bar_width=80),
        '[progress.percentage]{task.completed}/{task.total}',
        result_columns=result_columns,
    ) as progress:
        task_progress = progress.add_task('running tasks...', total=len(tasks))

        pool = _ProcessPool()
        for task in tasks:
            pool.submit(task.name, task.func)
            status = rich.panel.Panel('running', title=f'[bold]{task.name}')
            results[task.name] = status
            result_columns.add_renderable(status)

        # wait for tasks to complete
        for name, process, out, exc in pool.as_completed():
            if process.exitcode:
                progress.print(f'[bold red]error executing: {name}')
                progress.print(out, end='', highlight=False)
                results[name].renderable = 'failed'
                results[name].style = 'red'
                fail = True
            else:
                progress.print(f'[bold green]sucessfully executed: {name}')
                results[name].renderable = 'success'
                results[name].style = 'green'
            progress.advance(task_progress)
    return fail


_tasks: List[_Task] = []


def task(
    isolated: bool = True,
) -> Callable[[Callable[..., Any]], None]:
    def decorator(func: Callable[..., Any]) -> None:
        _tasks.append(_Task(func.__name__, func, isolated))
    return decorator
