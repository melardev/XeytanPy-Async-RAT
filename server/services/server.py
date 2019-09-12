import select
import socket
import sys
import threading
import time

from server.app_concurrent.events.events import ClientAppEvent, Subject, Target, Action, AppEvent
from server.services.client import NetClientService
from shared.net_lib.packets.packet import PacketInformation, PacketDesktop, PacketFileSystem, PacketProcess, PacketShell


class NetServerService:
    def __init__(self, channel):
        self.channel = channel

        self.readable_fd_list = []
        self.clients_socket = []
        # it is useless, because they point to the same list, but better readability
        self.writable_fd_list = self.clients_socket
        self.throwable_fd_list = []
        self.server = None
        self.running = False
        self.clients = {}
        # create the socket AF_INET states this is an Ipv4 Socket, SOCK_STREAM states this is a TCP socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.port = 3002
        self.address = '127.0.0.1'

        self.server_thread = threading.Thread(target=self.server_loop)
        self.app_evens_thread = threading.Thread(target=self.listen_app_events)

    def start_async(self):
        self.running = True
        # if we close the app, we want to release the used address immediately so other process
        # may use it, without this line if we restart the app, we won't be able to reuse immediately the address
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.address, self.port))
        # hint the OS how much connections may be queued while you are not in an accept() call
        # the OS is free to skip the value you provide so ... anyways, do not give as much attention here
        self.server_socket.listen(socket.SOMAXCONN)

        self.readable_fd_list.append(self.server_socket)

        self.server_thread.start()
        self.app_evens_thread.start()

    def server_loop(self):
        while self.running:
            try:
                # select function will take some lists and as 4th argument a titmeout=None arg the lists are consisting
                # on file descriptors, select will check each file description if it is has some pending data to read,
                # write, or error to handle example: let's say the server has a pending connection, select will notice
                # that because the server file descriptor(fd) is in the list of the first arg (read_list) and will return
                # fds_readY_to_read which is a list of descriptors that have pending data to read, among them is the
                # server fd
                fds_ready_to_read, fds_read_to_write, fds_with_err = select.select(
                    self.readable_fd_list, [], [])

            except select.error as e:
                sys.stdout.write('select error\n')
                break
            except socket.error as e:
                sys.stdout.write('socket error\n')
                break

            if len(fds_ready_to_read) > 0:
                for fd_ready_to_read in fds_ready_to_read:
                    if fd_ready_to_read == self.server_socket:
                        self.read_from_server()
                    else:
                        self.read_from_client(fd_ready_to_read)

            time.sleep(0.5)

    def read_from_server(self):
        client_socket_fd, address = self.server_socket.accept()
        sys.stdout.write('We have a new connection, address: (%d, %s)\n' % (client_socket_fd.fileno(), address))

        try:
            self.clients[client_socket_fd.fileno()] = NetClientService(self, address, client_socket_fd)
            # client sockets are readable and writable, append them to the appropriate list
            self.readable_fd_list.append(client_socket_fd)
            self.writable_fd_list.append(client_socket_fd)  # same as if clients.append(client)
        except socket.error:
            pass

        return client_socket_fd

    def read_from_client(self, socket_obj):
        client_id = socket_obj.fileno()
        self.clients[client_id].try_read_packet()
        return

    def listen_app_events(self):
        while self.running:
            event = self.channel.take_from_app()
            if event is None:
                print('event is None')
                continue

            target = event.target
            action = event.action
            subject = event.subject
            object_data = event.object_data

            if target == Target.Client:

                client_id = object_data['client_id']
                client = self.clients.get(client_id, None)
                if client is None:
                    continue
                if subject == Subject.ClientInformation:
                    packet = PacketInformation()
                    client.send_packet(packet=packet)

                elif subject == Subject.FileSystem:
                    path = object_data['path']

                    if action == Action.Get:
                        packet = PacketFileSystem()
                        packet.path = path
                        client.send_packet(packet=packet)

                    elif action == Action.Post:
                        try:
                            packet = PacketFileSystem(fs_action=PacketFileSystem.Actions.Upload, path=path)
                            with open(path, 'rb') as fd:
                                packet.file_data = fd.read()

                            client.send_packet(packet=packet)
                        except FileNotFoundError as err:
                            self.channel.post_to_app(
                                AppEvent(target=Target.Ui, object_data={'type': 'error',
                                                                        'message': 'File Not found: %s'
                                                                                   % str(err)}))
                elif subject == Subject.Process:
                    if action == Action.Get or action == Action.Start:
                        packet = PacketProcess()
                        client.send_packet(packet)
                    elif action == Action.Stop:
                        pid = object_data.get('pid', None)
                        if pid is not None:
                            packet = PacketProcess(ps_action=PacketProcess.Actions.Kill, pid=pid)
                            client.send_packet(packet)

                elif subject == Subject.Desktop:
                    packet = PacketDesktop()
                    client.send_packet(packet=packet)

                elif subject == Subject.Shell:

                    if action == Action.Post:  # Create process, don't care about output
                        command = object_data.get('command', None)
                        shell = object_data.get('shell', False)

                        if command is not None:
                            if shell:
                                packet = PacketShell(shell_action=PacketShell.Actions.Interactive, command=command)
                            else:
                                packet = PacketShell(shell_action=PacketShell.Actions.Exec, command=command)
                            client.send_packet(packet)

                    elif action == Action.Get:  # Create process, get output
                        command = object_data.get('command', None)
                        if command is not None:
                            packet = PacketShell(shell_action=PacketShell.Actions.ExecPiped, command=command)
                            client.send_packet(packet)
                    elif action == Action.Start:  # Interactive shell
                        packet = PacketShell(shell_action=PacketShell.Actions.Interactive)
                        client.send_packet(packet)
                    else:
                        print('Invalid Action')
                else:
                    print('Unknown packet')
            else:
                print('Unknown target')

    def on_client_disconnected(self, client_model):
        client_id = client_model['client_id']
        socket_object = client_model['socket_object']
        self.clients_socket.remove(socket_object)
        self.readable_fd_list.remove(socket_object)
        # self.writable_fd_list.remove(socket_object)
        del self.clients[socket_object.fileno()]

        self.channel.post_to_app(
            ClientAppEvent(client={'client_id': client_id}, subject=Subject.Connection,
                           action=Action.Stop))

    def on_exit(self):
        for client in self.clients_socket:
            client.close()

    def on_packet_received(self, client_model, packet):
        event = ClientAppEvent(client_model, Subject.PacketReceived, object_data=packet)
        self.channel.post_to_app(event)

    def get_clients(self):
        clients = []
        net_clients = self.clients.values()
        for net_client in net_clients:
            clients.append(net_client.get_client_model())
        return clients

    def send_packet(self, client, packet):
        client.send_packet(packet)
