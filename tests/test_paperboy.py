from paperboy import __version__


def test_version():
    assert __version__ == "0.1.0"


def test_user_agent():
    from paperboy.app import USER_AGENT
    assert USER_AGENT, "no user agent"
