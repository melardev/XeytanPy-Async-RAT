from shared.concurrent_lib.channels.double import DoubleQueuedChannel


class AppNetDoubleQueuedChannel(DoubleQueuedChannel):
    def __init__(self):
        super().__init__()

    def take_from_app(self):
        return self.take_from_right()

    def take_from_net(self):
        return self.take_from_left()

    def post_to_app(self, elem):
        self.post_to_left_sync(elem)

    def post_to_net(self, elem):
        self.post_to_right_sync(elem)
