import time
import os
import string
import ConfigParser
from oeqa.oetest import oeRuntimeTest
from oeqa.utils.helper import shell_cmd_timeout
from oeqa.utils.decorators import tag

eth_config = ConfigParser.ConfigParser()
config_path = os.path.join(os.path.dirname(__file__), "files/config.ini")
eth_config.readfp(open(config_path))

@tag(TestType="Functional Positive")
class CommEthernet(oeRuntimeTest):
    def get_ipv6(self):
        time.sleep(1)
        # Check ip address by ifconfig command
        interface = "nothing"
        (status, interface) = self.target.run("ifconfig | grep '^enp' | awk '{print $1}'")
        (status, output) = self.target.run("ifconfig %s | grep 'inet6 addr:' | awk '{print $3}' | cut -d'/' -f1" % interface)
        return output

    @tag(FeatureID="IOTOS-489")
    def test_ethernet_ipv6_ping(self):
        '''Ping other device via ipv6 address of the ethernet'''
        # Get target ipv6 address
        ip6_address = self.get_ipv6()
        # ping6 needs host's ethernet interface by -I, 
        # because default gateway is only for ipv4
        host_eth = eth_config.get("Ethernet","interface")
        cmd = "ping6 -I %s %s -c 1" % (host_eth, ip6_address) 
        status, output = shell_cmd_timeout(cmd, timeout=60)
        self.assertEqual(status, 0, msg="Error messages: %s" % output)

    @tag(FeatureID="IOTOS-489")
    def test_ethernet_ipv6_ssh(self):
        '''SSH other device via ipv6 address of the ethernet'''
        # Get target ipv6 address
        ip6_address = self.get_ipv6()
        # Same as ping6, ssh with ipv6 also need host's ethernet interface
        # ssh root@<ipv6 address>%<eth>
        host_eth = eth_config.get("Ethernet","interface")
        exp = os.path.join(os.path.dirname(__file__), "files/ipv6_ssh.exp")
        cmd = "expect %s %s %s %s" % (exp, ip6_address, "ostro", host_eth)
        status, output = shell_cmd_timeout(cmd, timeout=60)
        # In expect, it will input yes and password while login. And do 'ls /'
        # If see /home folder, it will return 2 as successful status.
        self.assertEqual(status, 2, msg="Error messages: %s" % output)
