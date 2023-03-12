from test_helpers import TestError
import test_query
import test_mutation

test_modules = [test_query, test_mutation]

for test_module in test_modules:
    for name, test in test_module.__dict__.items():
        if name.startswith("test_") and callable(test):
            try:
                test()
                print(f"PASS {name}")
            except TestError as e:
                print(f"FAIL {name}: {e}")
