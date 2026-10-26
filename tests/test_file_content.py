import tempfile
import unittest
from pathlib import Path

from functions.get_file_content import get_file_content, schema_get_file_content


class FileContentRangeTests(unittest.TestCase):
    def test_can_start_from_a_later_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notes.txt"
            path.write_text("one\ntwo\nthree\n")
            self.assertEqual(get_file_content(directory, "notes.txt", 2), "two\nthree\n")
            self.assertEqual(get_file_content(directory, "notes.txt", 9), "")
            self.assertIn("positive integer", get_file_content(directory, "notes.txt", 0))
            self.assertEqual(get_file_content(directory, "notes.txt", 2, 1), "two\n")
            self.assertIn("between 1 and 1000", get_file_content(directory, "notes.txt", 1, 1001))

    def test_tool_schema_exposes_the_optional_start_line(self):
        properties = schema_get_file_content["function"]["parameters"]["properties"]
        self.assertEqual(properties["start_line"]["minimum"], 1)
        self.assertEqual(properties["line_count"]["maximum"], 1000)


if __name__ == "__main__":
    unittest.main()
