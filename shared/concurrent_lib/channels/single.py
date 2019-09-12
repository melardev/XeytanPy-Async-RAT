import queue


class SingleQueuedChannel:
    def __init__(self):
        self.channel = queue.Queue()

    def take_sync(self):
        return self.channel.get(True)

    def post_async(self, elem):
        self.channel.put(elem, False)

    def post_sync(self, elem):
        self.channel.put(elem, True)
