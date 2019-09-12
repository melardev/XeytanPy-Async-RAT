import getpass
import platform
import select
import socket
import threading
import time

from shared.net_lib.packets.packet import PacketPresentation
from shared.net_lib.services.net.asynchronous.select.base_client import BaseNetClientService


class NetClientService(BaseNetClientService):
    def __init__(self, app=None, channel=None):
        super(NetClientService, self).__init__()
        self.channel = channel
        self.app = app
        self.readable_fds = []
        self.writable_fds = []
        self.throwable_fds = []

        self.host = 'localhost'
        self.port = 3002
        self.running = True
        self.net_client_thread = threading.Thread(target=self.start)

    def start_async(self):
        self.net_client_thread.start()

    def start(self):
        self.running = True
        while True:
            try:
                # create the socket AF_INET states this is an Ipv4 Socket, SOCK_STREAM states this is a TCP socket
                self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket.connect((self.host, self.port))
                pc_name = platform.node()
                os_name = platform.system()  # platform.platform() is more complete
                username = getpass.getuser()
                self.send_packet(PacketPresentation(pc_name=pc_name, os_name=os_name, username=username))
                # Our socket may receive data(is readable) and also may write data (is writable)
                self.readable_fds.append(self.client_socket)
                self.writable_fds.append(self.client_socket)
                break
            except IOError as e:
                time.sleep(5)
        self.client_loop()

    def client_loop(self):
        while self.running:
            try:
                fds_ready_for_read, fds_ready_for_write, fds_ready_for_error = select.select(self.readable_fds,
                                                                                             self.writable_fds,
                                                                                             self.throwable_fds)
                if len(fds_ready_for_read) > 0:
                    for fd_ready_for_read in fds_ready_for_read:
                        if fd_ready_for_read == self.client_socket:
                            self.try_read_packet()
            except socket.error:
                self.on_client_disconnected()
                return

        time.sleep(1)

    def on_client_disconnected(self):
        self.readable_fds.clear()
        self.writable_fds.clear()
        self.throwable_fds.clear()
        self.client_socket.close()
        self.app.on_disconnected()

    def on_packet_received(self, packet):
        # self.channel.post_to_app(packet)
        self.app.on_packet_received(packet)
