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


MIN_PORT_NUMBER = 1
MAX_PORT_NUMBER = 2**16 - 1
VERSION = pkg_resources.require('hil')[0].version
hil_client = None


cli = ArgumentParser(description='HIL CLI')
subcli = cli.add_subparsers()


# Exceptions #
##############
class HILClientFailure(Exception):
    """Exception indicating that the HIL client failed"""


# Setup a client somehow #
##########################
def hil_client_connect():
    """Sets up the global hil client"""
    global hil_client
    endpoint = os.getenv('HIL_ENDPOINT')
    username = os.getenv('HIL_USERNAME')
    password = os.getenv('HIL_PASSWORD')
    hil_http_client = RequestsHTTPClient()
    hil_http_client.auth = (username, password)
    hil_client = Client(endpoint, hil_http_client)


# Helper Functions #
####################
def subcommand(parentparser, args=[]):
    def decorator(func):
        parser = parentparser.add_parser(func.__name__,
                                         description=func.__doc__)
        for arg in args:
            parser.add_argument(arg)
        parser.set_defaults(func=func)
    return decorator


@subcommand(subcli, ['port'])
def serve(args):
    """Run a development api server. Don't use this in production."""

    if not MIN_PORT_NUMBER <= args.port <= MAX_PORT_NUMBER:
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
    rest.serve(args.port, debug=debug)


@subcommand(subcli, ['object_type'])
def list(args):
    """Run list command on different objects"""


@subcommand(subcli, ['node_name', 'obme_type', 'hostname', 'username',
                     'password'])
def node_register(args):
    """Register a node named <node>, with the given type.\n \
                    If obm is of type: ipmi then provide arguments \n \
                    ipmi, <hostname>, <ipmi-username>, <ipmi-password>")
    """
    hil_client.node.register(
         args.node_name, args.obm_type, args.hostname, args.username,
         args.password)
    print response


def main():
    ensure_not_root()
    hil_client_connect()
    args = cli.parse_args()
    args.func(args)
