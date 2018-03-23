"""Test invoking the command line tool"""


import subprocess
import pytest
from hil.test_common import fail_on_log_warnings

fail_on_log_warnings = pytest.fixture(autouse=True)(fail_on_log_warnings)


PROJECT1 = 'foo'
NODE1 = 'dell-1'
NIC1 = 'eth1'

SWITCH1 = 'mock-switch1'
SWITCH2 = 'mock-switch2'
PORT = 'gi1/0/1'


def hil(*args):
    """Convenience function that calls the hil command line tool with
    the given arguments.
    """
    args = " ".join(args)
    args = args.split(" ")
    return subprocess.check_output(['hil'] + args)


def test_cli():

    """These tests a lot of different operations together

    It tests two things:
    1. The subprocess calls are run without error.
    2. Some assertions that actually check the output of the subprocess call.
    """

    # Test node and nic creation
    hil('node register', NODE1, 'mock host user password')
    assert NODE1 in hil('node list all')
    assert NODE1 in hil('node list free')

    # Register a nic
    hil('node nic register', NODE1, NIC1, 'aa:bb:cc:dd:ee:ff')
    assert NIC1 in hil('node show', NODE1)

    # Test that obm related calls run succesfully
    hil('node bootdev', NODE1, 'pxe')
    hil('node console start', NODE1)
    output = hil('node console show', NODE1)
    assert output.strip('\n') == 'Some console output'

    hil('node console stop', NODE1)
    hil('node power off', NODE1)
    hil('node power cycle', NODE1)

    # Test node metadata calls
    hil('node metadata add', NODE1, 'metadata-label metadata-value')
    hil('node metadata delete', NODE1, 'metadata-label')

    # Test project create command
    hil('project create', PROJECT1)
    assert PROJECT1 in hil('project list')

    # project and node connect
    hil('project node add', PROJECT1, NODE1)
    assert NODE1 in hil('project node list', PROJECT1)
    assert NODE1 not in hil('node list free')

    # test switch register in 2 ways

    hil('switch register', SWITCH1, 'mock host user pass')
    assert SWITCH1 in hil('switch list')

    switch_api = "http://schema.massopencloud.org/haas/v0/switches/mock"
    args = '{"hostname": "host", "username": "user", "password": "pass"}'
    # use subprocess directly here, because the helper function messes up the
    # switchinfo
    subprocess.check_call(['hil', 'switch', 'register',
                          SWITCH2, switch_api, args])
    assert SWITCH2 in hil('switch list')

    # Register a port and see that it's shown in show switch
    hil('port register', SWITCH1, PORT)
    assert PORT in hil('switch show', SWITCH1)
    assert PORT not in hil('switch show', SWITCH2)

    # delete everything
    hil('port delete', SWITCH1, PORT)
    hil('switch delete', SWITCH1)
    hil('switch delete', SWITCH2)
    hil('project node remove', PROJECT1, NODE1)
    hil('project delete', PROJECT1)
    hil('node nic delete', NODE1, NIC1)
    hil('node delete', NODE1)
