import subprocess
from typing import List
from ..util import warn
from . import native, docker

all_runners = [
    native,
    docker,
]

default_runner = docker


def run(argv: List[str]) -> int:
    try:
        subprocess.run(argv, check = True)
    except subprocess.CalledProcessError as e:
        warn("Error running %s, exited %d" % (e.cmd, e.returncode))
        return e.returncode
    else:
        return 0


def replace_ellipsis(items: List, elided_items: List) -> List:
    """
    Replaces any Ellipsis items (...) in a list, if any, with the items of a
    second list.
    """
    return [
        y for x in items
          for y in (elided_items if x is ... else [x])
    ]
