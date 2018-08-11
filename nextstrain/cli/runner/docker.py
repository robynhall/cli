"""
Run commands inside a container image using Docker.
"""

import os
import shutil
import argparse
import subprocess
from ..util import warn, colored, capture_output
from ..volume import store_volume


DEFAULT_IMAGE = "nextstrain/base"
COMPONENTS    = ["sacra", "fauna", "augur", "auspice"]


def register_arguments(parser, exec=None, volumes=[]):
    # Unpack exec parameter into the command and everything else
    (exec_cmd, *exec_args) = exec

    # Development options
    development = parser.add_argument_group(
        "development options",
        "These should generally be unnecessary unless you're developing build images.")

    development.add_argument(
        "--image",
        help    = "Container image in which to run the pathogen build",
        metavar = "<name>",
        default = DEFAULT_IMAGE)

    development.add_argument(
        "--exec",
        help    = "Program to exec inside the build container",
        metavar = "<prog>",
        default = exec_cmd)

    development.set_defaults(volumes = [])

    for name in volumes:
        development.add_argument(
            "--" + name,
            help    = "Replace the image's copy of %s with a local copy" % name,
            metavar = "<dir>",
            action  = store_volume(name))

    development.add_argument(
        "--docker-arg",
        help    = "Additional arguments to pass to `docker run`",
        metavar = "...",
        dest    = "docker_args",
        action  = "append")

    # Optional exec arguments
    parser.set_defaults(exec_args = exec_args)
    parser.set_defaults(extra_exec_args = [])

    if ... in exec_args:
        parser.add_argument(
            "extra_exec_args",
            help    = "Additional arguments to pass to the executed build program",
            metavar = "...",
            nargs   = argparse.REMAINDER)


def run(opts):
    # Ensure all volume source paths exist.  Docker will auto-create missing
    # directories in the path, which, while desirable under some circumstances,
    # doesn't match up well with our use case.  We're aiming to not surprise or
    # confuse the user.
    #
    missing_volumes = [ vol for vol in opts.volumes if not vol.src.is_dir() ]

    if missing_volumes:
        warn("Error: The path(s) given for the following components do not exist")
        warn("or are not directories:")
        warn()
        for vol in missing_volumes:
            warn("    • %s: %s" % (vol.name, vol.src))
        return 1

    if opts.docker_args is None:
        opts.docker_args = []

    argv = [
        "docker", "run",
        "--rm",             # Remove the ephemeral container after exiting
        "--tty",            # Colors, etc.
        "--interactive",    # Pass through control signals (^C, etc.)

        # On Unix (POSIX) systems, run the process in the container with the same
        # UID/GID so that file ownership is correct in the bind mount directories.
        # The getuid()/getgid() functions are documented to be only available on
        # Unix systems, not, for example, Windows.
        *(["--user=%d:%d" % (os.getuid(), os.getgid())] if os.name == "posix" else []),

        # Map directories to bind mount into the container.
      *["--volume=%s:/nextstrain/%s" % (v.src.resolve(), v.name)
            for v in opts.volumes
             if v.src is not None],

        # Pass through credentials as environment variables
        "--env=RETHINK_HOST",
        "--env=RETHINK_AUTH_KEY",

        *opts.docker_args,
        opts.image,
        opts.exec,
        *replace_ellipsis(opts.exec_args, opts.extra_exec_args)
    ]

    try:
        subprocess.run(argv, check = True)
    except subprocess.CalledProcessError as e:
        warn("Error running %s, exited %d" % (e.cmd, e.returncode))
        return e.returncode
    else:
        return 0


def replace_ellipsis(items, elided_items):
    """
    Replaces any Ellipsis items (...) in a list, if any, with the items of a
    second list.
    """
    return [
        y for x in items
          for y in (elided_items if x is ... else [x])
    ]


def test_setup():
    def test_run():
        try:
            status = subprocess.run(
                ["docker", "run", "--rm", "hello-world"],
                check = True,
                stdout = subprocess.DEVNULL)
        except:
            return False
        else:
            return status.returncode == 0

    return [
        ('docker is installed',
            shutil.which("docker") is not None),
        ('docker run works',
            test_run()),
    ]


def update():
    print(colored("bold", "Updating Docker image %s…" % DEFAULT_IMAGE))
    print()

    # Pull the latest image down
    try:
        subprocess.run(
            ["docker", "image", "pull", DEFAULT_IMAGE],
            check = True)
    except subprocess.CalledProcessError:
        return False

    # Prune any old images which are now dangling to avoid leaving lots of
    # hidden disk use around.  We don't use `docker image prune` because we
    # want to just remove _our_ dangling images, not all.  We very much don't
    # want to automatically prune unrelated images.
    print()
    print(colored("bold", "Pruning old copies of image…"))
    print()

    try:
        images = dangling_images(DEFAULT_IMAGE)

        if images:
            subprocess.run(
                ["docker", "image", "rm", *images],
                check = True)
    except subprocess.CalledProcessError as error:
        warn("Error pruning old image versions: ", error)
        return False

    return True


def dangling_images(name):
    """
    Return a list of Docker image IDs which are untagged ("dangling") and thus
    likely no longer in use.

    Since dangling images are untagged, this finds images by name using our
    custom org.nextstrain.image.name label.
    """
    name_sans_tag = name.split(":")[0]

    return capture_output([
        "docker", "image", "ls",
            "--no-trunc",
            "--format={{.ID}}",
            "--filter=dangling=true",
            "--filter=label=org.nextstrain.image.name=%s" % name_sans_tag
    ])


def print_version():
    print_image_version()
    print_component_versions()


def print_image_version():
    """
    Print the Docker image name and version.
    """

    # Qualify the name with the "latest" tag if necessary so we only get a
    # single id back.
    qualified_image = DEFAULT_IMAGE

    if ":" not in DEFAULT_IMAGE:
        qualified_image += ":latest"

    image_ids = capture_output([
        "docker", "image", "ls",
            "--format={{.ID}} ({{.CreatedAt}})", qualified_image])

    assert len(image_ids) <= 1

    # Print the default image name as-is, without the implicit :latest
    # qualification (if any).  The :latest tag is often confusing, as it
    # doesn't mean you have the latest version.  Thus we avoid it.
    #
    # This function (via the version command), may be run before the image is
    # downloaded, so we handle finding no image ids.
    print("%s docker image %s" % (DEFAULT_IMAGE, image_ids[0] if image_ids else "not present"))


def print_component_versions():
    """
    Print the git ids of the Nextstrain components in the image.
    """

    # It is much faster to spin up a single ephemeral container and read all
    # the versions with a little bash than to do it one-by-one.  It also lets
    # us more easily do fine-grained reporting of presence/absence.
    report_versions = """
        for component in %s; do
            if [[ -e /nextstrain/$component/.GIT_ID ]]; then
                echo $component $(</nextstrain/$component/.GIT_ID)
            elif [[ -d /nextstrain/$component ]]; then
                echo $component unknown
            else
                echo $component not present
            fi
        done
    """ % " ".join(COMPONENTS)

    versions = capture_output([
        "docker", "run", "--rm", "-it", DEFAULT_IMAGE,
            "bash", "-c", report_versions
    ])

    for version in versions:
        print("  " + version)
