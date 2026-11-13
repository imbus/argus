import importlib
import unittest


class Package(unittest.TestCase):
    def test_package_imports(self) -> None:
        self.assertEqual(importlib.import_module("argus").__name__, "argus")


if __name__ == "__main__":
    unittest.main()
