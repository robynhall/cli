"""
Visualizes a completed pathogen build in auspice, the Nextstrain web frontend.

The data directory should contain sets of files with at least two files:

    <prefix>_tree.json
    <prefix>_meta.json

The viewer runs inside a container, which requires Docker.  Run `nextstrain
check-setup` to check if Docker is installed and works.
"""

import re
import netifaces as net
import zeroconf
import socket
from pathlib import Path
from ..runner import docker
from ..util import colored, warn, remove_suffix


def register_parser(subparser):
    parser = subparser.add_parser("view", help = "View pathogen build")
    parser.description = __doc__

    parser.add_argument(
        "--allow-remote-access",
        help   = "Allow other computers on the network to access the website",
        action = "store_true")

    # Positional parameters
    parser.add_argument(
        "directory",
        help    = "Path to pathogen build data directory",
        metavar = "<directory>",
        action  = docker.store_volume("auspice/data"))

    # Runner options
    docker.register_arguments(
        parser,
        exec    = ["auspice"],
        volumes = ["auspice"])

    return parser


def run(opts):
    # Try to find the available dataset paths since we may not have a manifest
    data_dir = Path(opts.auspice_data.src)
    datasets = [
        re.sub(r"_tree$", "", path.stem).replace("_", "/")
            for path in data_dir.glob("*_tree.json")
    ]

    # Setup the published port.  Default to localhost for security reasons
    # unless explicitly told otherwise.
    #
    # There are docker-specific implementation details here that should be
    # refactored once we have more than one nextstrain.cli.runner module in
    # play.  Doing that work now would be premature; we'll get a better
    # interface for ports/environment when we have concrete requirements.
    #   -trs, 27 June 2018
    host = "0.0.0.0" if opts.allow_remote_access else "127.0.0.1"
    port = 4000

    if opts.docker_args is None:
        opts.docker_args = []

    opts.docker_args = [
        *opts.docker_args,

        # PORT is respected by auspice's server.js
        "--env=PORT=%d" % port,

        # Publish the port
        "--publish=%s:%d:%d" % (host, port, port),
    ]

    # Find the best remote address if we're allowing remote access.  While we
    # listen on all interfaces (0.0.0.0), only the local host can connect to
    # that successfully.  Remote hosts need a real IP on the network, which we
    # do our best to discover.  If something goes wrong, ignore it and leave
    # the host IP as-is (0.0.0.0); it'll at least work for local access.
    if opts.allow_remote_access:
        try:
            remote_address = best_remote_address()
        except:
            pass
        else:
            host = remote_address

    # Try to advertise ourselves using mDNS on nextstrain.local (or a uniquely
    # numbered version of it).  If we're successful, then use that hostname in
    # our messaging.
    mdns = None
    try:
        (advertised_host, mdns) = advertise_service(host, port)
    except:
        pass
    else:
        host = advertised_host

    # Show a helpful message about where to connect
    print_url(host, port, datasets)

    # Run auspice
    status = docker.run(opts)

    # Cleanup mDNS instance, if any
    if mdns:
        mdns.close()

    return status


def print_url(host, port, datasets):
    """
    Prints a list of available dataset URLs, if any.  Otherwise, prints a
    generic URL.
    """

    def url(path = None):
        return colored(
            "blue",
            "http://{host}:{port}/{path}".format(
                host = host,
                port = port,
                path = path if path is not None else ""))

    horizontal_rule = colored("green", "—" * 78)

    print()
    print(horizontal_rule)

    if len(datasets):
        print("    The following datasets should be available in a moment:")
        for path in sorted(datasets, key = str.casefold):
            print("       • %s" % url(path))
    else:
        print("    Open <%s> in your browser." % url())

    print(horizontal_rule)


def best_remote_address():
    """
    Returns the "best" non-localback IP address for the local host, if
    possible.  The "best" IP address is that bound to either the default
    gateway interface, if any, else the arbitrary first interface found.

    IPv4 is preferred, but IPv6 will be used if no IPv4 interfaces/addresses
    are available.
    """
    default_gateway   = net.gateways().get("default", {})
    default_interface = default_gateway.get(net.AF_INET,  (None, None))[1] \
                     or default_gateway.get(net.AF_INET6, (None, None))[1] \
                     or net.interfaces()[0]

    interface_addresses = net.ifaddresses(default_interface).get(net.AF_INET)  \
                       or net.ifaddresses(default_interface).get(net.AF_INET6) \
                       or []

    addresses = [
        address["addr"]
            for address in interface_addresses
             if address.get("addr")
    ]

    return addresses[0] if addresses else None


def advertise_service(host, port):
    mdns = zeroconf.Zeroconf()

    service = zeroconf.ServiceInfo(
        "_http._tcp.local.",
        "nextstrain._http._tcp.local.",
        server     = "nextstrain.local",
        address    = socket.inet_aton(host),
        port       = port,
        properties = {})

    # Check that our service name is unique on the network.  If it's not, an
    # increasing integer will be appended until it is, yielding, for example:
    #
    #    nextstrain-2._http._tcp.local.
    #
    # We then use this unique service name to set a unique server name
    # (hostname) based on it (e.g. nextstrain-2.local.).
    #
    # This allows multiple people on the same network to advertise a local
    # Nextstrain instance at the same time.
    mdns.check_service(service, allow_name_change = True)

    service.server = remove_suffix(service.type + '.local.', service.name)

    # This starts a new set of threads which listen and respond to mDNS queries
    # in the background until we exit.  The default TTL is 120s, so we reduce
    # to 30s for less cache lag since we're likely to be spinning up and down
    # quickly unlike other services.
    mdns.register_service(service, ttl = 30)

    # Return the server name, without the trailing dot, and the Zeroconf
    # instance for lifecycle management
    return (service.server.rstrip("."), mdns)
