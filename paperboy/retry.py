
class Retry():
    def __init__(self, exception, max_trys=3):
        #print('init method called')
        self.exception = [exception]
        self.trys = 0
        self._max_trys = max_trys
        self.acomplished = False

    def __enter__(self):
        #print('enter method called')
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        #print('exit method called')
        if not exc_type:
             self.acomplished = True
             return True
        self.trys += 1
        if self.trys >= self._max_trys:
            return False
        if exc_type not in self.exception:
            return False
        if exc_type in self.exception:
            self.__enter__()
        return True
