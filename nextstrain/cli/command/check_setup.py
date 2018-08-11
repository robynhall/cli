"""
Checks your local setup to make sure a container runner is installed and works.

Docker is the currently the only supported container system.  It must be
installed and configured, which this command will test by running:

    docker run --rm hello-world

"""

from functools import partial
from ..util import colored, check_for_new_version, runner_name
from ..runner import all_runners


def register_parser(subparser):
    parser = subparser.add_parser("check-setup", help = "Test your local setup")
    parser.description = __doc__
    return parser


def run(opts):
    success = partial(colored, "green")
    failure = partial(colored, "red")

    status = {
        True:  success("✔"),
        False: failure("✘"),
    }

    # Check our own version for updates
    check_for_new_version()

    # Run and collect our runners' self-tests
    print("Testing your setup…")

    runner_tests = [
        (runner, runner.test_setup())
            for runner in all_runners
    ]

    # Print test results.  The first print() separates results from the
    # previous header or stderr output, making it easier to read.
    print()

    for runner, tests in runner_tests:
        print(colored("blue", "#"), "%s support" % runner_name(runner))

        for description, result in tests:
            print(status.get(result, " "), description)

        print()

    # Print overall status.
    runner_status = [
        (runner, False not in [result for test, result in tests])
            for runner, tests in runner_tests
    ]

    supported_runners = [
        runner_name(runner)
            for runner, status_ok in runner_status
             if status_ok
    ]

    if supported_runners:
        print(success("Supported runners: %s" % ", ".join(supported_runners)))
    else:
        print(failure("No support for any runner"))

    # Return a 1 or 0 exit code
    return int(not supported_runners)
