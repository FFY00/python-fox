# SPDX-License-Identifier: EUPL-1.2

import argparse
import importlib.util
import sys

from typing import List, Optional

import fox


def main_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--parallel',
        '-p',
        action='store_true',
        help='run tasks in parallel',
    )
    return parser


def main(cli_args: List[str], prog: Optional[str] = None) -> None:
    parser = main_parser()
    if prog:
        parser.prog = prog
    args = parser.parse_args(cli_args)

    executor: fox.Executor
    if args.parallel:
        executor = fox._parallel_executor
    else:
        executor = fox._sequencial_executor

    # load foxfile.py
    foxfile_spec = importlib.util.spec_from_file_location('foxfile', 'foxfile.py')
    if not foxfile_spec.loader:
        raise ImportError('Unable to import foxfile: no loader')
    foxfile_module = importlib.util.module_from_spec(foxfile_spec)
    foxfile_spec.loader.exec_module(foxfile_module)  # type: ignore

    # execute tasks
    executor(fox._tasks)


def entrypoint() -> None:
    main(sys.argv[1:])


if __name__ == '__main__':  # pragma: no cover
    main(sys.argv[1:], 'python -m fox')
