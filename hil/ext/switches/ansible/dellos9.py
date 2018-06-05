"""This module holds the functions that make appropriate dictionary objects
and run those using ansible_runner.

Currently this is hardcoded to work with dellos9_{config, command}
"""
import ansible_runner


def host_information(host, user, password, ansible_network_os):
    """Generates the dictionary object with host information.

    Will simplify this later"""
    return {
        'hosts': {
            'myswitch': {
                'ansible_host': host,
            }
        },
        'vars': {
            'ansible_user': user,
            'ansible_password': password
        },
        'children': {
            'switch': {
                'vars': {
                    'ansible_network_os': ansible_network_os,
                },
                'hosts': {
                    'myswitch': {}
                }
            }
        }
    }


def run_config_command(command, name):
    """Run any config command <command>

    Command must be a list.
    Name is the name of the command
    """
    config_command = {
        "name": name,
        "dellos9_config": {
            "commands": command
        }
    }
    return [config_command]


def run_show_command(command, name):
    """Run a show command <command> and give it <name>

    It stores the output in stdout so that we can parse it because at this
    point I don't know how to store outputs in python variables using ansible
    runner"""
    gather_information = {
        "name": name,
        "dellos9_command": {
            "commands": command
        },
        "register": "output"
    }
    print_to_stdout = {
        "name": "output to stdout",
        "debug": {
            "var": "output.stdout_lines",
        }
    }
    tasks = [gather_information, print_to_stdout]
    return tasks


def port_off(port):
    """Power off port"""
    goto_switchport = ['interface gigabitethernet ' + port]
    disable_switchport = ['no switchport', 'no portmode hybrid', 'shutdown']
    commands = goto_switchport + disable_switchport
    return run_config_command(commands, "port off")


def port_on(port):
    """Power on port"""
    goto_switchport = ['interface gigabitethernet ' + port]
    enable_switchport = ['portmode hybrid', 'switchport', 'no shutdown']
    commands = goto_switchport + enable_switchport
    return run_config_command(commands, "port on")


def add_trunk_vlan(port, trunk_vlan):
    """Sets the VLANs using the dellos9_config module"""
    goto_switchport = ['interface gigabitethernet ' + port]
    add_vlan = ['interface vlan ' + trunk_vlan,
                'tagged gigabitethernet ' + port]
    commands = goto_switchport + add_vlan
    return run_config_command(commands, "add vlan to trunk")


def add_native_vlan(port, native_vlan):
    """Sets the VLANs using the dellos9_config module"""
    goto_switchport = ['interface gigabitethernet ' + port]
    enable_switchport = ['portmode hybrid', 'switchport', 'no shutdown']
    add_vlan = ['interface vlan ' + native_vlan,
                'untagged gigabitethernet ' + port]
    commands = goto_switchport + enable_switchport + add_vlan
    return run_config_command(commands, "add native vlan")


def remove_native_vlan(port, native_vlan):
    """Remove the native vlan and power it off.

    Ideally, I should power off the port separately, but this
    is more efficient to do in one call"""
    remove_native = ['interface vlan ' + native_vlan,
                     'no untagged gigabitethernet ' + port]
    goto_switchport = ['interface gigabitethernet ' + port]
    disable_switchport = ['no switchport', 'no portmode hybrid', 'shutdown']
    commands = remove_native + goto_switchport + disable_switchport

    return run_config_command(commands, "remove native vlan")


def get_port_info(port):
    """Create the dictionary object to gather port information"""
    command = ["show interface switchport gigabitethernet " + port]
    return run_show_command(command, "show port information")


def run_task(tasks, hosts):
    """Run <tasks> on <hosts>

    tasks is a list.
    hosts is a dictionary containing hosts.
    return stdout
    """
    playbook = {
        "hosts": "switch",
        "gather_facts": False,
        "connection": "local",
        "tasks": tasks
    }

    kwargs = {
        'playbook': [playbook],
        'inventory': {'all': hosts},
    }
    result = ansible_runner.run(**kwargs)

    stdout = result.stdout.read()

    return stdout
