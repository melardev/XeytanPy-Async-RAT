class Target:
    InvalidTarget = -1
    Server = 1
    Client = 2
    App = 3
    Ui = 4


class Subject:
    InvalidSubject = -1
    Connection = 1,
    ClientInformation = 2

    # PacketReceived is used to pass a Packet object to the Ui and hence speed up development.
    # This way, I only have to check the packet_type and process it once, at the ui, the problem
    # is that we tightly couple the ui subsystem to the packets which come from the net subsystem.
    # It is fine for this app and we speed up development A LOT. This app already decouples at
    # a good degree the ui from the net, which most applications out there don't
    PacketReceived = 3,
    FileSystem = 4,
    Process = 5,
    Shell = 6,
    Desktop = 7,


class Action:
    InvalidAction = -1
    Get = 1,
    Start = 2,
    Post = 3,
    Pause = 4,
    Stop = 5,
    GetConfig = 6,


class AppEvent:
    def __init__(self,
                 target=Target.InvalidTarget, subject=Subject.InvalidSubject, action=Action.InvalidAction,
                 description=None, object_data=None):
        self.target = target
        self.subject = subject
        self.action = action
        self.description = description
        self.object_data = object_data


class ClientAppEvent(AppEvent):
    def __init__(self, client,
                 subject=Subject.InvalidSubject, action=Action.InvalidAction,
                 description=None, object_data=None):
        super(ClientAppEvent, self).__init__(Target.Client, subject=subject, action=action,
                                             description=description, object_data=object_data)
        self.client = client
