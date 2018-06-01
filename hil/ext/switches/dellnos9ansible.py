"""A switch driver for Dell S3048-ON running Dell OS 9.

Uses Ansible networking to manage the switch
"""

import logging
import re
from schema import Schema, Optional

from hil.model import db, Switch
from hil.errors import BadArgumentError
from hil.model import BigIntegerType
from hil.ext.switches.common import check_native_networks, parse_vlans
from hil.config import core_schema, string_is_bool
from hil.ext.switches import _vlan_http

import hil.ext.switches.ansible.dellos9 as ansible_dellos9


logger = logging.getLogger(__name__)

core_schema[__name__] = {
    Optional('save'): string_is_bool
}


class DellNOS9Ansible(Switch, _vlan_http.Session):
    """Dell S3048-ON running Dell NOS9"""
    api_name = 'http://schema.massopencloud.org/haas/v0/switches/dellnos9ansible'

    __mapper_args__ = {
        'polymorphic_identity': api_name,
    }

    id = db.Column(BigIntegerType,
                   db.ForeignKey('switch.id'), primary_key=True)
    hostname = db.Column(db.String, nullable=False)
    username = db.Column(db.String, nullable=False)
    password = db.Column(db.String, nullable=False)
    port_type = db.Column(db.String, nullable=False)

    @property
    def host_information(self):
        """Return the dictionary containing host information needed by ansible
        runner.
        """
        # This is the dictionary object; could probably trim this down a little.
        return {
            'hosts': {
                'myswitch': {
                    'ansible_host': self.hostname,
                }
            },
            'vars': {
                'ansible_user': self.username,
                'ansible_password': self.password
            },
            'children': {
                'switch': {
                    'vars': {
                        'ansible_network_os': "dellos9",
                    },
                    'hosts': {
                        'myswitch': {}
                    }
                }
            }
        }

    @staticmethod
    def validate(kwargs):
        Schema({
            'hostname': basestring,
            'username': basestring,
            'password': basestring,
            'port_type': basestring,
        }).validate(kwargs)

    def session(self):
        return self

    def ensure_legal_operation(self, nic, op_type, channel):
        check_native_networks(nic, op_type, channel)

    def get_capabilities(self):
        return []

    @staticmethod
    def validate_port_name(port):
        """Valid port names for this switch are of the form 1/0/1 or 1/2"""

        if not re.match(r'^\d+/\d+(/\d+)?$', port):
            raise BadArgumentError("Invalid port name. Valid port names for "
                                   "this switch are of the form 1/0/1 or 1/2")

    def _is_port_on(self, port):
        """ Returns a boolean that tells the status of a switchport"""
        command = ["show running-config interface gigabitethernet " + port]
        task = ansible_dellos9.run_show_command(command, "check if port is on")
        response = ansible_dellos9.run_task(task, self.host_information)
        match = re.search(r'no shutdown', response)
        if match is not None:
            return True
        else:
            match = re.search(r'shutdown', response)
            if match is None:
                assert False, "unexpected state of switchport"
            else:
                return False

    def _get_vlans(self, port):
        """ Return the vlans of a trunk port.

        Does not include the native vlan. Use _get_native_vlan.

        Args:
            port: port to return the vlans of

        Returns: List containing the vlans of the form:
        [('vlan/vlan1', vlan1), ('vlan/vlan2', vlan2)]
        """
        if not self._is_port_on(port):
            return []
        response = self._get_port_info(port)
        response = response.replace(' ', '')

        # finds a comma separated list of integers and/or ranges starting with
        # T. Sample T12,14-18,23,28,80-90 or T20 or T20,22 or T20-22
        match = re.search(r'T(\d+(-\d+)?)(,\d+(-\d+)?)*', response)
        if match is None:
            return []

        vlan_list = parse_vlans(match.group().replace('T', ''))

        return [('vlan/%s' % x, x) for x in vlan_list]

    def _get_native_vlan(self, port):
        """ Return the native vlan of an port.

        Args:
            port: port to return the native vlan of

        Returns: Tuple of the form ('vlan/native', vlan) or None

        Similar to _get_vlans()
        """
        if not self._is_port_on(port):
            return None
        response = self._get_port_info(port)
        response = response.replace(' ', '')
        match = re.search(r'NativeVlanId:(\d+)\.', response)
        if match is not None:
            vlan = match.group(1)
        else:
            logger.error('Unexpected: No native vlan found')
            return

        return ('vlan/native', vlan)

    def _get_port_info(self, port):
        """Returns port information"""
        task = ansible_dellos9.get_port_info(port)
        response = ansible_dellos9.run_task(task, self.host_information)
        return response

    def _add_vlan_to_trunk(self, port, vlan):
        """ Add a vlan to a trunk port.

        The HIL API makes sure that this can only be called after a native
        vlan is already set which turns on the port and enables switching.

        Args:
            port: port to add the vlan to
            vlan: vlan to add
        """
        task = ansible_dellos9.add_trunk_vlan(port, vlan)
        ansible_dellos9.run_task(task, self.host_information)

    def _remove_vlan_from_trunk(self, port, vlan):
        """ Remove a vlan from a trunk port.

        Args:
            port: port to remove the vlan from
            vlan: vlan to remove
        """
        command = self._remove_vlan_command(port, vlan)
        task = ansible_dellos9.run_show_command(command)
        ansible_dellos9.run_task(task, self.host_information)

    # def _remove_all_vlans_from_trunk(self, port):
    #     """ Remove all vlan from a trunk port.

    #     Args:
    #         port: port to remove the vlan from
    #     """
    #     # I COULDNT GET THIS TO WORK. IT ONLY REMOVES THE FIRST VLAN IN THE
    #     # LIST

    #     # generate a big command to remove all vlans in one trip
    #     command = []
    #     for vlan in self._get_vlans(port):
    #         command += self._remove_vlan_command(port, vlan[1])
    #     # execute command only if there are some vlans to remove, otherwise
    #     # the switch complains
    #     if command is not []:
    #         task = ansible_dellos9.run_config_command(
    #             command, "remove all trunk vlans")
    #         ansible_dellos9.run_task(task, self.host_information)

    def _remove_all_vlans_from_trunk(self, port):
        """ Remove all vlan from a trunk port.

        Args:
            port: port to remove the vlan from
        """
        for vlan in self._get_vlans(port):
            command = self._remove_vlan_command(port, vlan[1])
            task = ansible_dellos9.run_config_command(
                command, "remove vlan: " + vlan[1])
            ansible_dellos9.run_task(task, self.host_information)

    def _remove_vlan_command(self, port, vlan):
        """Returns command to remove <vlan> from <port>"""
        return ['interface vlan ' + vlan, 'no tagged ' + self.port_type + ' ' + port]

    def _set_native_vlan(self, port, vlan):
        """ Set the native vlan of an port.

        Args:
            port: port to set the native vlan to
            vlan: vlan to set as the native vlan

        Method relies on the REST API CLI which is slow
        """
        if not self._is_port_on(port):
            self._port_on(port)
        task = ansible_dellos9.add_native_vlan(port, vlan)
        ansible_dellos9.run_task(task, self.host_information)

    def _remove_native_vlan(self, port):
        """ Remove the native vlan from a port.

        Args:
            port: port to remove the native vlan from.vlan
        """
        try:
            vlan = self._get_native_vlan(port)[1]
            task = ansible_dellos9.remove_native_vlan(port, vlan)
            ansible_dellos9.run_task(task, self.host_information)
        except TypeError:
            logger.error('No native vlan to remove')

    def _port_shutdown(self, port):
        """ Shuts down <port>

        Turn off portmode hybrid, disable switchport, and then shut down the
        port. All non-default vlans must be removed before calling this.
        """
        task = ansible_dellos9.port_off(port)
        ansible_dellos9.run_task(task, self.host_information)

    def _port_on(self, port):
        """ Turns on <port>

        Turn on port and enable hybrid portmode and switchport.
        """
        task = ansible_dellos9.port_on(port)
        ansible_dellos9.run_task(task, self.host_information)
