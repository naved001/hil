"""This module implements the HIL command line tool."""
from hil import config, server, migrations
from hil.config import cfg
from hil.commands.util import ensure_not_root

import inspect
import json
import os
import requests
import sys
import urllib
import schema
import logging

import pkg_resources

from functools import wraps

from hil.client.client import Client, RequestsHTTPClient, KeystoneHTTPClient
from hil.client.base import FailedAPICallException
from hil.errors import BadArgumentError


logger = logging.getLogger(__name__)
command_dict = {}
usage_dict = {}
MIN_PORT_NUMBER = 1
MAX_PORT_NUMBER = 2**16 - 1
VERSION = pkg_resources.require('hil')[0].version

# An instance of HTTPClient, which will be used to make the request.
http_client = None
C = None


class InvalidAPIArgumentsException(Exception):
    """Exception indicating that the user passed invalid arguments."""


def setup_http_client():
    """Set `http_client` to a valid instance of `HTTPClient`

    and pass it as parameter to initialize the client library.

    Sets http_client to an object which makes HTTP requests with
    authentication. It chooses an authentication backend as follows:

    1. If the environment variables HIL_USERNAME and HIL_PASSWORD
       are defined, it will use HTTP basic auth, with the corresponding
       user name and password.
    2. If the `python-keystoneclient` library is installed, and the
       environment variables:

           * OS_AUTH_URL
           * OS_USERNAME
           * OS_PASSWORD
           * OS_PROJECT_NAME

       are defined, Keystone is used.
    3. Oterwise, do not supply authentication information.

    This may be extended with other backends in the future.

    `http_client` is also passed as a parameter to the client library.
    Until all calls are moved to client library, this will support
    both ways of intereacting with HIL.
    """
    global http_client
    global C  # initiating the client library
    # First try basic auth:
    ep = (
            os.environ.get('HIL_ENDPOINT') or
            sys.stdout.write("Error: HIL_ENDPOINT not set \n")
            )
    basic_username = os.getenv('HIL_USERNAME')
    basic_password = os.getenv('HIL_PASSWORD')
    if basic_username is not None and basic_password is not None:
        # For calls with no client library support yet.
        # Includes all headnode calls; registration of nodes and switches.
        http_client = RequestsHTTPClient()
        http_client.auth = (basic_username, basic_password)
        # For calls using the client library
        C = Client(ep, http_client)
        return
    # Next try keystone:
    try:
        from keystoneauth1.identity import v3
        from keystoneauth1 import session
        os_auth_url = os.getenv('OS_AUTH_URL')
        os_password = os.getenv('OS_PASSWORD')
        os_username = os.getenv('OS_USERNAME')
        os_user_domain_id = os.getenv('OS_USER_DOMAIN_ID') or 'default'
        os_project_name = os.getenv('OS_PROJECT_NAME')
        os_project_domain_id = os.getenv('OS_PROJECT_DOMAIN_ID') or 'default'
        if None in (os_auth_url, os_username, os_password, os_project_name):
            raise KeyError("Required openstack environment variable not set.")
        auth = v3.Password(auth_url=os_auth_url,
                           username=os_username,
                           password=os_password,
                           project_name=os_project_name,
                           user_domain_id=os_user_domain_id,
                           project_domain_id=os_project_domain_id)
        sess = session.Session(auth=auth)
        http_client = KeystoneHTTPClient(sess)
        # For calls using the client library
        C = Client(ep, http_client)
        return
    except (ImportError, KeyError):
        pass
    # Finally, fall back to no authentication:
    http_client = requests.Session()
    C = Client(ep, http_client)


def check_status_code(response):
    """Check the status code of the response.

    If it is a successful status code, print the body of the response to
    stdout. Otherwise, print an error message, and raise a
    FailedAPICallException.
    """
    if response.status_code < 200 or response.status_code >= 300:
        sys.stderr.write('Unexpected status code: %d\n' % response.status_code)
        sys.stderr.write('Response text:\n')
        sys.stderr.write(response.content + "\n")
        raise FailedAPICallException()
    else:
        sys.stdout.write(response.content + "\n")

# Function object_url should be DELETED.


def object_url(*args):
    """Return a url with a prefix of the HIL endpoint, and args as the
    (remaining) segments of the path.

    TODO: This function's name is no longer very accurate.  As soon as it is
    safe, we should change it to something more generic.
    """
    # Prefer an environmental variable for getting the endpoint if available.
    url = os.environ.get('HIL_ENDPOINT')
    if url is None:
        config.setup()
        url = cfg.get('client', 'endpoint')

    for arg in args:
        url += '/' + urllib.quote(arg, '')
    return url


# Helper functions for making HTTP requests against the API.
#    Uses the global variable `http_client` to make the request.
#
#    Arguments:
#
#        `url` - The url to make the request to
#        `data` - the body of the request (for PUT, POST and DELETE)
#        `params` - query parameters (for GET)

def do_put(url, data={}):
    """do a put request and check the response."""
    check_status_code(http_client.request('PUT', url, data=json.dumps(data)))


def do_post(url, data={}):
    """do a post request and check the response."""
    check_status_code(http_client.request('POST', url, data=json.dumps(data)))


def do_get(url, params=None):
    """do a get request and check the response."""
    check_status_code(http_client.request('GET', url, params=params))


def do_delete(url):
    """do a delete request and check the response."""
    check_status_code(http_client.request('DELETE', url))

# DELETE UPTIL HERE once all calls have client library support.


def version():
    """Check hil version"""
    sys.stdout.write("HIL version: %s\n" % VERSION)


def serve(port):
    """Run a development api server. Don't use this in production."""
    try:
        port = schema.And(
            schema.Use(int),
            lambda n: MIN_PORT_NUMBER <= n <= MAX_PORT_NUMBER).validate(port)
    except schema.SchemaError:
        raise InvalidAPIArgumentsException(
            'Error: Invaid port. Must be in the range 1-65535.'
        )
    except Exception as e:
        sys.exit('Unxpected Error!!! \n %s' % e)

    """Start the HIL API server"""
    config.setup()
    if cfg.has_option('devel', 'debug'):
        debug = cfg.getboolean('devel', 'debug')
    else:
        debug = False
    # We need to import api here so that the functions within it get registered
    # (via `rest_call`), though we don't use it directly:
    # pylint: disable=unused-variable
    from hil import api, rest
    server.init()
    migrations.check_db_schema()
    server.stop_orphan_consoles()
    rest.serve(port, debug=debug)


def list_users():
    """List all users when the database authentication is active.

    Administrative  privileges required.
    """
    q = C.user.list()
    for item in q.items():
        sys.stdout.write('%s \t : %s\n' % (item[0], item[1]))


def user_create(username, password, is_admin):
    """Create a user <username> with password <password>.

    <is_admin> may be either "admin" or "regular", and determines whether
    the user has administrative privileges.
    """
    if is_admin not in ('admin', 'regular'):
        raise ValueError(
            "invalid privilege type: must be either 'admin' or 'regular'."
            )
    C.user.create(username, password, is_admin == 'admin')


def user_set_admin(username, is_admin):
    """Changes the admin status of user <username>.

    <is_admin> may by either "admin" or "regular", and determines whether
    a user is authorized for administrative privileges.
    """
    if is_admin not in ('admin', 'regular'):
        raise ValueError(
            "invalid user privilege: must be either 'admin' or 'regular'."
            )
    C.user.set_admin(username, is_admin == 'admin')


def network_create(network, owner, access, net_id):
    """Create a link-layer <network>.  See docs/networks.md for details"""
    C.network.create(network, owner, access, net_id)


def network_create_simple(network, project):
    """Create <network> owned by project.  Specific case of network_create"""
    C.network.create(network, project, project, "")


def network_delete(network):
    """Delete a <network>"""
    C.network.delete(network)


def user_delete(username):
    """Delete the user <username>"""
    C.user.delete(username)


def list_projects():
    """List all projects"""
    q = C.project.list()
    sys.stdout.write('%s Projects :    ' % len(q) + " ".join(q) + '\n')


def user_add_project(user, project):
    """Add <user> to <project>"""
    C.user.add(user, project)


def user_remove_project(user, project):
    """Remove <user> from <project>"""
    C.user.remove(user, project)


def network_grant_project_access(project, network):
    """Add <project> to <network> access"""
    C.network.grant_access(project, network)


def network_revoke_project_access(project, network):
    """Remove <project> from <network> access"""
    C.network.revoke_access(project, network)


def project_create(project):
    """Create a <project>"""
    C.project.create(project)


def project_delete(project):
    """Delete <project>"""
    C.project.delete(project)


def headnode_create(headnode, project, base_img):
    """Create a <headnode> in a <project> with <base_img>"""
    url = object_url('headnode', headnode)
    do_put(url, data={'project': project,
                      'base_img': base_img})


def headnode_delete(headnode):
    """Delete <headnode>"""
    url = object_url('headnode', headnode)
    do_delete(url)


def project_connect_node(project, node):
    """Connect <node> to <project>"""
    C.project.connect(project, node)


def project_detach_node(project, node):
    """Detach <node> from <project>"""
    C.project.detach(project, node)


def headnode_start(headnode):
    """Start <headnode>"""
    url = object_url('headnode', headnode, 'start')
    do_post(url)


def headnode_stop(headnode):
    """Stop <headnode>"""
    url = object_url('headnode', headnode, 'stop')
    do_post(url)


def node_register(node, subtype, *args):
    """Register a node named <node>, with the given type
        if obm is of type: ipmi then provide arguments
        "ipmi", <hostname>, <ipmi-username>, <ipmi-password>
    """
    C.node.register(node, subtype, *args)


def node_delete(node):
    """Delete <node>"""
    C.node.delete(node)


def node_power_cycle(node):
    """Power cycle <node>"""
    C.node.power_cycle(node)


def node_power_off(node):
    """Power off <node>"""
    C.node.power_off(node)


def node_set_bootdev(node, dev):
    """
    Sets <node> to boot from <dev> persistently

    eg; hil node_set_bootdev dell-23 pxe
    for IPMI, dev can be set to disk, pxe, or none
    """
    C.node.set_bootdev(node, dev)


def node_register_nic(node, nic, macaddr):
    """
    Register existence of a <nic> with the given <macaddr> on the given <node>
    """
    C.node.add_nic(node, nic, macaddr)


def node_delete_nic(node, nic):
    """Delete a <nic> on a <node>"""
    C.node.remove_nic(node, nic)


def headnode_create_hnic(headnode, nic):
    """Create a <nic> on the given <headnode>"""
    url = object_url('headnode', headnode, 'hnic', nic)
    do_put(url)


def headnode_delete_hnic(headnode, nic):
    """Delete a <nic> on a <headnode>"""
    url = object_url('headnode', headnode, 'hnic', nic)
    do_delete(url)


def node_connect_network(node, nic, network, channel):
    """Connect <node> to <network> on given <nic> and <channel>"""
    print C.node.connect_network(node, nic, network, channel)


def node_detach_network(node, nic, network):
    """Detach <node> from the given <network> on the given <nic>"""
    print C.node.detach_network(node, nic, network)


def headnode_connect_network(headnode, nic, network):
    """Connect <headnode> to <network> on given <nic>"""
    url = object_url('headnode', headnode, 'hnic', nic, 'connect_network')
    do_post(url, data={'network': network})


def headnode_detach_network(headnode, hnic):
    """Detach <headnode> from the network on given <nic>"""
    url = object_url('headnode', headnode, 'hnic', hnic, 'detach_network')
    do_post(url)


def metadata_set(node, label, value):
    """Register metadata with <label> and <value> with <node> """
    C.node.metadata_set(node, label, value)


def metadata_delete(node, label):
    """Delete metadata with <label> from a <node>"""
    C.node.metadata_delete(node, label)


def switch_register(switch, subtype, *args):
    """Register a switch with name <switch> and
    <subtype>, <hostname>, <username>,  <password>
    eg. hil switch_register mock03 mock mockhost01 mockuser01 mockpass01

    FIXME: current design needs to change. CLI should not know about every
    backend. Ideally, this should be taken care of in the driver itself or
    client library (work-in-progress) should manage it.
    """
    switch_api = "http://schema.massopencloud.org/haas/v0/switches/"
    if subtype == "nexus" or subtype == "delln3000":
        if len(args) == 4:
            switchinfo = {
                "type": switch_api + subtype,
                "hostname": args[0],
                "username": args[1],
                "password": args[2],
                "dummy_vlan": args[3]}
        else:
            sys.stderr.write('ERROR: subtype ' + subtype +
                             ' requires exactly 4 arguments\n'
                             '<hostname> <username> <password>'
                             '<dummy_vlan_no>\n')
            return
    elif subtype == "mock":
        if len(args) == 3:
            switchinfo = {"type": switch_api + subtype, "hostname": args[0],
                          "username": args[1], "password": args[2]}
        else:
            sys.stderr.write('ERROR: subtype ' + subtype +
                             ' requires exactly 3 arguments\n')
            sys.stderr.write('<hostname> <username> <password>\n')
            return
    elif subtype == "powerconnect55xx":
        if len(args) == 3:
            switchinfo = {"type": switch_api + subtype, "hostname": args[0],
                          "username": args[1], "password": args[2]}
        else:
            sys.stderr.write('ERROR: subtype ' + subtype +
                             ' requires exactly 3 arguments\n'
                             '<hostname> <username> <password>\n')
            return
    elif subtype == "brocade" or "dellnos9":
        if len(args) == 4:
            switchinfo = {"type": switch_api + subtype, "hostname": args[0],
                          "username": args[1], "password": args[2],
                          "interface_type": args[3]}
        else:
            sys.stderr.write('ERROR: subtype ' + subtype +
                             ' requires exactly 4 arguments\n'
                             '<hostname> <username> <password> '
                             '<interface_type>\n'
                             'NOTE: interface_type refers '
                             'to the speed of the switchports\n '
                             'ex. TenGigabitEthernet, FortyGigabitEthernet, '
                             'etc.\n')
            return
    else:
        sys.stderr.write('ERROR: Invalid subtype supplied\n')
        return
    url = object_url('switch', switch)
    do_put(url, data=switchinfo)


def switch_delete(switch):
    """Delete a <switch> """
    C.switch.delete(switch)


def list_switches():
    """List all switches"""
    q = C.switch.list()
    sys.stdout.write('%s switches :    ' % len(q) + " ".join(q) + '\n')


def port_register(switch, port):
    """Register a <port> with <switch> """
    C.port.register(switch, port)


def port_delete(switch, port):
    """Delete a <port> from a <switch>"""
    C.port.delete(switch, port)


def port_connect_nic(switch, port, node, nic):
    """Connect a <port> on a <switch> to a <nic> on a <node>"""
    C.port.connect_nic(switch, port, node, nic)


def port_detach_nic(switch, port):
    """Detach a <port> on a <switch> from whatever's connected to it"""
    C.port.detach_nic(switch, port)


def port_revert(switch, port):
    """Detach a <port> on a <switch> from all attached networks."""
    print C.port.port_revert(switch, port)


def list_network_attachments(network, project):
    """List nodes connected to a network
    <project> may be either "all" or a specific project name.
    """
    print C.network.list_network_attachments(network, project)


def list_nodes(is_free):
    """List all nodes or all free nodes

    <is_free> may be either "all" or "free", and determines whether
        to list all nodes or all free nodes.
    """
    q = C.node.list(is_free)
    if is_free == 'all':
        sys.stdout.write('All nodes %s\t:    %s\n' % (len(q), " ".join(q)))
    elif is_free == 'free':
        sys.stdout.write('Free nodes %s\t:   %s\n' % (len(q), " ".join(q)))
    else:
        sys.stdout.write('Error: %s is an invalid argument\n' % (is_free))


def list_project_nodes(project):
    """List all nodes attached to a <project>"""
    q = C.project.nodes_in(project)
    sys.stdout.write('Nodes allocated to %s:  ' % project + " ".join(q) + '\n')


def list_project_networks(project):
    """List all networks attached to a <project>"""
    q = C.project.networks_in(project)
    sys.stdout.write(
            "Networks allocated to %s\t:   %s\n" % (project, " ".join(q))
            )


def show_switch(switch):
    """Display information about <switch>"""
    q = C.switch.show(switch)
    for item in q.items():
        sys.stdout.write("%s\t  :  %s\n" % (item[0], item[1]))


def show_port(switch, port):
    """Show what's connected to <port>"""
    print C.port.show(switch, port)


def list_networks():
    """List all networks"""
    q = C.network.list()
    for item in q.items():
        sys.stdout.write('%s \t : %s\n' % (item[0], item[1]))


def show_network(network):
    """Display information about <network>"""
    q = C.network.show(network)
    for item in q.items():
        sys.stdout.write("%s\t  :  %s\n" % (item[0], item[1]))


def show_node(node):
    """Display information about a <node>

    FIXME: Recursion should be implemented to the output.
    """
#    The output of show_node is a dictionary that can be list of list, having
#    multiple nics and networks. More metadata about node could be shown
#    via this call. Suggestion to future developers of CLI to use
#    recursion in the call for output of such metadata.

    q = C.node.show(node)
    for item in q.items():
        sys.stdout.write("%s\t  :  %s\n" % (item[0], item[1]))


def list_project_headnodes(project):
    """List all headnodes attached to a <project>"""
    url = object_url('project', project, 'headnodes')
    do_get(url)


def show_headnode(headnode):
    """Display information about a <headnode>"""
    url = object_url('headnode', headnode)
    do_get(url)


def list_headnode_images():
    """Display registered headnode images"""
    url = object_url('headnode_images')
    do_get(url)


def show_console(node):
    """Display console log for <node>"""
    url = object_url('node', node, 'console')
    do_get(url)


def start_console(node):
    """Start logging console output from <node>"""
    C.node.start_console(node)


def stop_console(node):
    """Stop logging console output from <node> and delete the log"""
    C.node.stop_console(node)


def create_admin_user(username, password):
    """Create an admin user. Only valid for the database auth backend.

    This must be run on the HIL API server, with access to hil.cfg and the
    database. It will create an user named <username> with password
    <password>, who will have administrator privileges.

    This command should only be used for bootstrapping the system; once you
    have an initial admin, you can (and should) create additional users via
    the API.
    """
    config.setup()
    if not config.cfg.has_option('extensions', 'hil.ext.auth.database'):
        sys.exit("'make_inital_admin' is only valid with the database auth"
                 " backend.")
    from hil import model
    from hil.model import db
    from hil.ext.auth.database import User
    model.init_db()
    db.session.add(User(label=username, password=password, is_admin=True))
    db.session.commit()


def list_active_extensions():
    """List active extensions by type. """
    all_extensions = C.extensions.list_active()
    if not all_extensions:
        print "No active extensions"
    else:
        for ext in all_extensions:
            print ext


def show_networking_action(status_id):
    """Displays the status of the networking action"""
    print C.node.show_networking_action(status_id)


def help(*commands):
    """Display usage of all following <commands>, or of all commands if none
    are given
    """
    if not commands:
        sys.stdout.write('Usage: %s <command> <arguments...> \n' % sys.argv[0])
        sys.stdout.write('Where <command> is one of:\n')
        commands = sorted(command_dict.keys())
    for name in commands:
        # For each command, print out a summary including the name, arguments,
        # and the docstring (as a #comment).
        sys.stdout.write('  %s\n' % usage_dict[name])
        sys.stdout.write('      %s\n' % command_dict[name].__doc__)
