"""
Runs a pathogen build in an ephemeral container.

The build directory should contain a Snakefile, which will be run with
snakemake inside the container.

Docker is the currently the only supported container system.  It must be
installed and configured, which you can test by running:

    nextstrain check-setup

The `nextstrain build` command is designed to cleanly separate the Nextstrain
build interface from Docker itself so that we can more seamlessly use other
container systems in the future as desired or necessary.
"""

from ..runner import all_runners, default_runner
from ..util import warn, runner_name
from ..volume import store_volume


def register_parser(subparser):
    parser = subparser.add_parser("build", help = "Run pathogen build")
    parser.description = __doc__

    # Positional parameters
    parser.add_argument(
        "directory",
        help    = "Path to pathogen build directory",
        metavar = "<directory>",
        action  = store_volume("build"))

    # XXX TODO runner selection... how to handle differing options?

    # Runner options...
    runner_options = parser.add_mutually_exclusive_group()

    runner_options.set_defaults( __runner__ = default_runner )

    import argparse

    for runner in all_runners:
        runner_options.add_argument(
            "--" + runner_name(runner),
            help   = runner.__doc__.strip().splitlines()[0] + (" (default)" if runner is default_runner else ""),
            action = "store_const",
            dest   = "__runner__",
            const  = runner,
            default = argparse.SUPPRESS)

        if False:
            runner.register_arguments(
                parser,
                exec    = ["snakemake", ...],
                volumes = ["sacra", "fauna", "augur"])

    return parser


def run(opts):
    print(opts)
    return 1

    # Ensure our build dir exists
    if not opts.build.src.is_dir():
        warn("Error: Build path \"%s\" does not exist or is not a directory." % opts.build.src)

        if not opts.build.src.is_absolute():
            warn()
            warn("Perhaps your current working directory is different than you expect?")

        return 1

    return docker.run(opts, working_volume = opts.build)
