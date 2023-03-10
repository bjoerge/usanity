from tests.helpers import TestError

if __name__ == "__main__":
    import tests.query as query_tests
    import tests.mutation as mutation_tests

    test_modules = [query_tests, mutation_tests]

    for test_module in test_modules:
        for name, test in test_module.__dict__.items():
            if name.startswith("test_") and callable(test):
                try:
                    test()
                    print(f"PASS {name}")
                except TestError as e:
                    print(f"FAIL {name}: {e}")
