import os
import random
import string
import threading
from server.app_concurrent.channels.double import AppUiDoubleQueuedChannel, AppNetDoubleQueuedChannel
from server.app_concurrent.events.events import Target, Subject, Action, AppEvent
from shared.net_lib.packets.packet import PacketFileSystem
from server.services.server import NetServerService
from server.ui.console.console_mediator import ConsoleUiMediator


class Application:

    def __init__(self):
        self.net_channel = AppNetDoubleQueuedChannel()
        self.ui_channel = AppUiDoubleQueuedChannel()
        self.ui_mediator = ConsoleUiMediator(self.ui_channel)
        self.server = NetServerService(self.net_channel)
        self.running = False

        self.net_listener_thread = threading.Thread(target=self.listen_net_events)
        self.ui_listener_thread = threading.Thread(target=self.listen_ui_events)

    def run(self):
        self.running = True
        self.server.start_async()
        self.ui_mediator.start_async()
        self.ui_listener_thread.start()
        self.net_listener_thread.start()
        self.ui_mediator.main_loop()

    def listen_ui_events(self):
        while self.running:
            event = self.ui_channel.take_from_ui()
            if event is None:
                continue
            elif event.target == Target.Server:
                if event.subject == Subject.Connection and event.action == Action.Get:
                    clients = self.server.get_clients()
                    event.object_data = clients
                    self.ui_channel.post_to_ui(event)
                    continue
            # forward event to net, again, in real applications
            # the decoupling between ui and net should be complete
            # in this case, for the sake of speeding development
            # net and ui know a little bit about each other
            self.net_channel.post_to_net(event)

    def listen_net_events(self):
        while self.running:
            event = self.net_channel.take_from_net()
            if event is None:
                continue

            target = event.target
            subject = event.subject
            action = event.action
            event_object = event.object_data

            if target == Target.Client:
                client = event.client
                client_id = client['client_id']

                if subject == Subject.PacketReceived:
                    packet = event_object
                    if type(packet) == PacketFileSystem \
                            and packet.success \
                            and packet.fs_action == PacketFileSystem.Actions.Download:
                        if not os.path.exists("./downloads/%s" % client_id):
                            os.makedirs('./downloads/%s' % client_id)

                        filename = os.path.basename(packet.path)
                        if filename.strip() == '':
                            filename = self.generate_random_string()
                        filepath = './downloads/%s/%s' % (client_id, filename)
                        with open(filepath, 'wb') as fd:
                            fd.write(packet.file_data)

                        self.ui_channel.post_to_ui(
                            AppEvent(target=Target.Ui, object_data={'type': 'success',
                                                                    'message': 'File written into %s'
                                                                               % filepath}))
                        continue

            # forward event to ui
            self.ui_channel.post_to_ui(event)

    @staticmethod
    def generate_random_string(str_length=16):
        return ''.join(random.choice(string.ascii_lowercase) for i in range(str_length))
