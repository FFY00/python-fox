# SPDX-License-Identifier: EUPL-1.2

import collections
import io
import multiprocessing
import multiprocessing.connection
import sys

from collections.abc import Iterable
from typing import Any, Callable, Dict, List, Optional, Tuple

import colorful as cf


__version__ = '0.0.1'


cf.use_8_ansi_colors()


_Task = collections.namedtuple('_Task', ['name', 'func', 'isolated'])


Executor = Callable[[List[_Task]], None]


def _sequencial_executor(tasks: List[_Task]) -> None:
    for task in tasks:
        print(cf.bold_orange(f'> executing {task.name}'))
        task.func()


class _ProcessPool:
    def __init__(self) -> None:
        self._pool: Dict[str, Tuple[
            multiprocessing.Process,
            multiprocessing.connection.Connection,
        ]] = {}
        self._ready: multiprocessing.Queue[str] = multiprocessing.Queue()

    def submit(
        self,
        name: str,
        func: Callable[..., None],
        args: Optional[Tuple[Any, ...]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        recv_out, send_out = multiprocessing.Pipe()
        process = multiprocessing.Process(
            target=self._process_entry,
            args=(name, func, args or [], kwargs or {}, send_out),
        )
        process.start()
        self._pool[name] = process, recv_out

    def _process_entry(
        self,
        name: str,
        func: Callable[..., None],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        send_out: multiprocessing.connection.Connection,
    ) -> None:
        with io.StringIO() as out:
            sys.stdout, sys.stderr = out, out
            try:
                func(*args, **kwargs)
            finally:
                send_out.send(out.getvalue())
                self._ready.put(name)

    def as_completed(self) -> Iterable[Tuple[
        str,
        multiprocessing.Process,
        multiprocessing.connection.Connection,
    ]]:
        while True:
            name = self._ready.get()

            process, recv_out = self._pool[name]
            yield name, process, recv_out.recv()

            del self._pool[name]
            if not self._pool:  # no pending tasks
                break


def _parallel_executor(tasks: List[_Task]) -> None:
    import tqdm

    with tqdm.tqdm(total=len(tasks), desc='Running tasks', bar_format='{l_bar}{bar}| ') as progress:
        pool = _ProcessPool()
        for task in tasks:
            pool.submit(task.name, task.func)

        # wait for tasks to complete
        for name, process, out in pool.as_completed():
            process.join()
            if process.exitcode:
                progress.write(str(cf.bold_red(f'error executing: {name}!')))
                progress.write(out, end='')
            else:
                progress.write(str(cf.bold_green(f'sucessfully executed: {name}')))
            progress.update(1)


_tasks: List[_Task] = []


def task(
    isolated: bool = True,
) -> Callable[[Callable[..., Any]], None]:
    def decorator(func: Callable[..., Any]) -> None:
        _tasks.append(_Task(func.__name__, func, isolated))
    return decorator
