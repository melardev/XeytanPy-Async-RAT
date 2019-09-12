from shared.concurrent_lib.channels.single import SingleQueuedChannel


class DoubleQueuedChannel:
    def __init__(self):
        self.left_channel = SingleQueuedChannel()
        self.right_channel = SingleQueuedChannel()

    def take_from_left(self):
        return self.left_channel.take_sync()

    def take_from_right(self):
        return self.right_channel.take_sync()

    def post_to_right_sync(self, elem):
        return self.right_channel.post_sync(elem)

    def post_to_left_sync(self, elem):
        return self.left_channel.post_sync(elem)
