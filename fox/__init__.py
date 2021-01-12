# SPDX-License-Identifier: EUPL-1.2

import collections
import concurrent.futures

from typing import Any, Callable, List


__version__ = '0.0.1'


_Task = collections.namedtuple('_Task', ['name', 'func', 'isolated'])


Executor = Callable[[List[_Task]], None]


def _sequencial_executor(tasks: List[_Task]) -> None:
    for task in tasks:
        print('> executing', task.name)
        task.func()


def _parallel_executor(tasks: List[_Task]) -> None:
    import tqdm

    with tqdm.tqdm(total=len(tasks)) as progress:
        with concurrent.futures.ProcessPoolExecutor() as executor:
            futures = [executor.submit(task.func) for task in tasks]
            for future in concurrent.futures.as_completed(futures):
                progress.update(1)


_tasks: List[_Task] = []


def task(
    isolated: bool = True,
) -> Callable[[Callable[..., Any]], None]:
    def decorator(func: Callable[..., Any]) -> None:
        _tasks.append(_Task(func.__name__, func, isolated))
    return decorator
