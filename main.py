import asyncio
import sys

import test_client
import test_eventsource
import test_listen
import test_mutation
import test_query
from test_helpers import TestError

test_modules = [test_query, test_mutation, test_listen, test_eventsource, test_client]

passed = 0
failed = 0

for test_module in test_modules:
    for name, test in sorted(test_module.__dict__.items()):
        if name.startswith("test_") and callable(test):
            try:
                result = test()
                if result is not None and hasattr(result, "__await__"):
                    asyncio.run(result)
                print(f"PASS {name}")
                passed += 1
            except TestError as e:
                print(f"FAIL {name}: {e}")
                failed += 1
            except Exception as e:
                print(f"ERROR {name}: {type(e).__name__}: {e}")
                failed += 1


print(f"\n{passed} passed, {failed} failed, {passed + failed} total")
if failed:
    sys.exit(1)
