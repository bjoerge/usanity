class TestError(Exception):
    pass


def expect_equal(a, b):
    if a != b:
        raise TestError(f"Expected '{a}' to equal '{b}'")
