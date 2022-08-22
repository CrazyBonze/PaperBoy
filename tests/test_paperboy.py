from paperboy import __version__
import pytest


def test_version():
    assert __version__ == "0.1.0"


def test_user_agent():
    from paperboy.app import USER_AGENT

    assert USER_AGENT, "no user agent"

class RaiseExceptions:
    def __init__(self, exceptions):
        self.exceptions = exceptions

    def run(self):
        if len(self.exceptions):
            expt = self.exceptions.pop()
            raise(expt)
        else:
            return True


def test_retry():
    from paperboy.retry import Retry

    expts = RaiseExceptions([Exception, Exception])

    with Retry(Exception) as r:
        print('entering retry')
        if r.trys < 2:
            expts.run()
        assert r.trys == 2
        assert expts.run()

    expts = RaiseExceptions([Exception])

    with pytest.raises(Exception) as exc_info:
        with Retry(ValueError) as r:
            print('entering retry')
            if r.trys == 0:
                expts.run()
                assert False, "This should never run"
            assert t.trys == 1
            assert expts.run()
