#!/usr/bin/env python

import sys
import os
import schema
import pkg_resources
from argparse import ArgumentParser

from hil.client.client import Client, RequestsHTTPClient
from hil.client.base import FailedAPICallException
from hil.errors import BadArgumentError
from hil.commands.util import ensure_not_root
from hil.cli import setup_http_client, C, InvalidAPIArgumentsException
from hil.cli import show_switch, show_port, show_network, show_node, \
 list_switches, list_nodes, list_networks, list_projects, node_register, \
 node_delete, list_project_networks, list_project_nodes, project_connect_node,\
 project_detach_node, node_connect_network, node_detach_network


MIN_PORT_NUMBER = 1
MAX_PORT_NUMBER = 2**16 - 1
VERSION = pkg_resources.require('hil')[0].version

cli = ArgumentParser(description='HIL CLI')
subcli = cli.add_subparsers()


# Helper Functions #
####################
def subcommand(args=[],  parentparser=subcli):
    def decorator(func):
        parser = parentparser.add_parser(func.__name__,
                                         description=func.__doc__)
        for arg in args:
            # putting nargs=+ lets me accept any additional arguments. Those
            # additional arguments are checked by the parser of whatever
            # command is called. I think it is messing up with optional
            # argument though.
            parser.add_argument(arg, nargs='+')
        parser.set_defaults(func=func)
    return decorator


def add_arguments(parser, args):
    """Wrapper to add arguments (args) to parser. Useful when we just want
    to add a list of arguments without any customizations
    """
    for arg in args:
        parser.add_argument(arg)


###############################
# Argparse structures go here #
###############################
@subcommand(['port'])
def serve(args):
    """Run a development api server. Don't use this in production."""
    if not MIN_PORT_NUMBER <= int(args.port[0]) <= MAX_PORT_NUMBER:
        raise BadArgumentError('Error: Invalid port. '
                               'Must be in the range 1-65535.')

    """Start the HIL API server"""
    from hil import api, rest, server, config, migrations
    from hil.config import cfg
    config.setup()
    if cfg.has_option('devel', 'debug'):
        debug = cfg.getboolean('devel', 'debug')
    else:
        debug = False
    # We need to import api here so that the functions within it get
    # registered (via `rest_call`), though we don't use it directly:
    # pylint: disable=unused-variable
    server.init()
    migrations.check_db_schema()
    server.stop_orphan_consoles()
    rest.serve(int(args.port[0]), debug=debug)


@subcommand(['object_type'])
def list(args):
    """Run list command on different objects"""
    object_type = args.object_type[0]

    if object_type == 'switches':
        list_switches()

    elif object_type == 'nodes':
        node_parser = ArgumentParser(description="list project subcommands")
        node_parser.add_argument('--free', action='store_true')
        node_args = node_parser.parse_args(sys.argv[3:])
        if node_args.free:
            list_nodes('free')
        else:
            list_nodes('all')

    elif object_type == 'projects':
        list_projects()

    elif object_type == 'networks':
        list_networks()

    elif object_type == 'project':

        project_parser = ArgumentParser(description="list project subcommands")
        project_parser.add_argument('project_name')
        project_parser.add_argument('subobject_type', choices=['networks',
                                    'nodes'])
        project_args = project_parser.parse_args(sys.argv[3:])

        if project_args.subobject_type == 'networks':
            list_project_networks(project_args.project_name)
        elif project_args.subobject_type == 'nodes':
            list_project_nodes(project_args.project_name)

    else:
        print "invalid object_type"


@subcommand(['object_type'])
def show(args):
    """Run show command on different objects"""
    show_parser = ArgumentParser(description='Show commands')
    show_parser.add_argument('object_type', choices=['switch', 'node',
                             'network', 'port'])
    show_parser.add_argument('subobject_name')
    show_args = show_parser.parse_args(sys.argv[2:])

    object_type = show_args.object_type
    object_name = show_args.subobject_name
    if object_type == 'switch':
        show_switch(object_name)
    elif object_type == 'node':
        show_node(object_name)
    elif object_type == 'network':
        show_network(object_name)
    elif object_type == 'port':
        show_port(object_name)
    else:
        print "invalid object_type"


@subcommand(['action'])
def node(args):
    """Perform calls related to a node"""
    node_parser = ArgumentParser(description='Node commands')

    # should obm calls be a part of the node subcommand?
    node_parser.add_argument('node_name')
    node_parser.add_argument('action_type', choices=['show', 'register',
                             'delete', 'connect', 'detach'])
    node_args = node_parser.parse_args(sys.argv[2:4])
    action = node_args.action_type

    if action == 'show':
        # this is duplicate, this is already exposed via the show call
        show_node(node_args.node_name)

    elif action == 'register':
        register_parser = ArgumentParser(description='Register a node')
        register_parser.add_argument('obm_type', choices=['ipmi', 'mock'])
        add_arguments(register_parser, ['hostname', 'username', 'password'])
        register_args = register_parser.parse_args(sys.argv[4:])

        node_register(node_args.node_name, register_args.obm_type,
                      register_args.hostname, register_args.username,
                      register_args.password)

    elif action == 'delete':
        node_delete(node_args.node_name)

    elif action == 'connect':
        connect_parser = ArgumentParser(description='Connect node to pasta')
        add_arguments(connect_parser, ['subobject_type', 'subobject_name'])
        connect_args = connect_parser.parse_args(sys.argv[4:6])

        # if I get rid of the hook to project here, this becomes simpler.
        if connect_args.subobject_type == 'project':
            project_connect_node(connect_args.subobject_name,
                                 node_args.node_name)

        elif connect_args.subobject_type == 'network':
            network_parser = ArgumentParser(description='connect to network')
            # can't make channel optional here :(
            add_arguments(network_parser, ['nic', 'channel'])
            network_args = network_parser.parse_args(sys.argv[6:])
            node_connect_network(node_args.node_name, network_args.nic,
                                 connect_args.subobject_name,
                                 network_args.channel)


def main():
    ensure_not_root()
    setup_http_client()
    args = cli.parse_args()
    try:
        args.func(args)
    except FailedAPICallException as e:
        sys.exit('Error: %s\n' % e.message)
    except InvalidAPIArgumentsException as e:
        sys.exit('Error: %s\n' % e.message)
    except BadArgumentError as e:
        sys.exit('Error: %s\n' % e.message)
