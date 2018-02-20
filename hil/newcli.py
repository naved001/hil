#!/usr/bin/env python

import argparse
import sys
import os
import schema
import pkg_resources

from hil.client.client import Client, RequestsHTTPClient
from hil.client.base import FailedAPICallException
from hil.errors import BadArgumentError
from hil.commands.util import ensure_not_root


MIN_PORT_NUMBER = 1
MAX_PORT_NUMBER = 2**16 - 1
VERSION = pkg_resources.require('hil')[0].version


class HILClientFailure(Exception):
    """Exception indicating that the HIL client failed"""


# HELPER METHODS


def hil_client_connect(endpoint_ip, name, pw):
    """Returns a HIL client object"""

    hil_http_client = RequestsHTTPClient()
    hil_http_client.auth = (name, pw)

    return Client(endpoint_ip, hil_http_client)


def add_arguments(parser, args):
    """Wrapper to add arguments (args) to parser. Usefull when we just want
    to add a list of arguments without any customizations
    """
    for arg in args:
        parser.add_argument(arg)


class HILCLI(object):

    def __init__(self):
        parser = argparse.ArgumentParser(
            description='HIL CLI',
            usage="hil <command> [<args>]\n \
                list_nodes     list_nodes --free or all\n \
                show_node      show the node\n")

        parser.add_argument('command', help='Subcommand to run')

        # some stuff to setup hil_client
        endpoint = os.getenv('HIL_ENDPOINT')
        username = os.getenv('HIL_USERNAME')
        password = os.getenv('HIL_PASSWORD')
        self.hil_client = hil_client_connect(endpoint, username, password)

        # only validate the 2nd argument
        args = parser.parse_args(sys.argv[1:2])
        if not hasattr(self, args.command):
            print 'Unrecognized command'
            parser.print_help()
            exit(1)

        # invoke the method with the same name
        try:
            getattr(self, args.command)()
        except FailedAPICallException as e:
            sys.exit('Error: %s\n' % e.message)
        except BadArgumentError as e:
            sys.exit('Error: %s\n' % e.message)
        except Exception as e:
            sys.exit('Unexpected error: %s\n' % e.message)

    # Should probably move this to hil-admin commands?
    def serve(self):
        """Run a development api server. Don't use this in production."""

        parser = argparse.ArgumentParser(
            description='Run a development api server')

        parser.add_argument('port', type=int)
        args = parser.parse_args(sys.argv[2:])

        if not MIN_PORT_NUMBER <= args.port <= MAX_PORT_NUMBER:
            raise BadArgumentError('Error: Invaid port. '
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
        rest.serve(args.port, debug=debug)

    def list(self):
        parser = argparse.ArgumentParser(description='List commands')
        parser.add_argument('object', choice=['nodes', 'projects'])
        args = parser.parse_args(sys.argv[2:3])

        # what I am trying to do here is so that users can type
        # `hil list nodes`. I could, make the call to client right here,
        # but then I can't use the parser to validate arguments since they
        # they could differ for list calls eg; list nodes can take --free, but
        # list projects doesn't take any argument.
        if args.object == 'nodes':
            self.list_nodes()
        if args.object == 'projects':
            self.list_projects()

    def list_nodes(self):
        # this method can be called directly, without going through `list`.
        # so at the moment, somebody could either do `hil list_nodes --free`
        # or `hil list nodes --free`. The latter is quicker to type.

        parser = argparse.ArgumentParser(
            description='List all nodes or free nodes with --free')

        parser.add_argument('--free', action='store_true')

        # now parse the rest of the arguments
        args = parser.parse_args(sys.argv[3:])
        if args.free:
            response = self.hil_client.node.list("free")
        else:
            response = self.hil_client.node.list("all")

        print response

    def list_projects(self):
        parser = argparse.ArgumentParser(description='List all projects')

        # now parse the rest of the arguments
        args = parser.parse_args(sys.argv[3:])
        response = self.hil_client.project.list()
        print response

    def show_node(self):
        parser = argparse.ArgumentParser(description='Show details about node')
        parser.add_argument('node_name')
        args = parser.parse_args(sys.argv[2:])

        response = self.hil_client.node.show(args.node_name)
        # we should format the output to make it look neato
        print response

    def node_register(self):
        parser = argparse.ArgumentParser(
            description="Register a node named <node>, with the given type.\n \
                        If obm is of type: ipmi then provide arguments \n \
                        ipmi, <hostname>, <ipmi-username>, <ipmi-password>")

        arguments = ['node_name', 'obm_type', 'hostname', 'username',
                     'password']
        add_arguments(parser, arguments)

        args = parser.parse_args(sys.argv[2:])
        self.hil_client.node.register(
             args.node_name, args.obm_type, args.hostname, args.username,
             args.password)
        print response


def main():
    ensure_not_root()
    HILCLI()
