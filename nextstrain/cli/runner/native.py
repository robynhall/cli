"""
Run commands on the native host, outside of any container image.
"""

import os
import shutil
import argparse
import subprocess
from .. import runner
from ..util import warn
from ..volume import store_volume


def register_arguments(parser, exec=None, volumes=[]):
    # Unpack exec parameter into the command and everything else
    (exec_cmd, *exec_args) = exec

    # Development options
    development = parser.add_argument_group(
        "development options",
        "These should generally be unnecessary unless you're developing Nextstrain.")

    development.add_argument(
        "--exec",
        help    = "Program to exec",
        metavar = "<prog>",
        default = exec_cmd)

    # Optional exec arguments
    parser.set_defaults(exec_args = exec_args)
    parser.set_defaults(extra_exec_args = [])

    if ... in exec_args:
        parser.add_argument(
            "extra_exec_args",
            help    = "Additional arguments to pass to the executed build program",
            metavar = "...",
            nargs   = argparse.REMAINDER)


def run(opts, working_volume = None):
    # XXX TODO: Is this the right approach?  We could also try to setup
    # --directory and --snakefile arguments, but that doesn't generalize very
    # well.  This may invalidate paths given in other arguments... but that's
    # probably ok?
    if working_volume:
        os.chdir(str(working_volume.src))

    return runner.run([
        opts.exec,
        *runner.replace_ellipsis(opts.exec_args, opts.extra_exec_args)
    ])


def test_setup():
    return [
        ('snakemake is installed',
            shutil.which("snakemake") is not None),

        ('augur is installed',
            shutil.which("augur") is not None),

        # XXX TODO: Test other programs here too?  auspice, for example, once it
        # has a native entry point.
        #   -trs, 31 July 2018
    ]


def update():
    return True
