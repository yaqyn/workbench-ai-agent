import json
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import subprocess
import stat

from openai.types.chat import ChatCompletionMessage
from call_function import call_function
from functions.get_file_content import get_file_content
from functions.get_files_info import get_files_info
from functions.write_file import write_file
from functions.run_python_file import run_python_file
from main import main, run_agent, save_transcript


def tool(name, arguments):
    return SimpleNamespace(id="call_1", function=SimpleNamespace(name=name, arguments=arguments))


def response(content=None, calls=None):
    return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=ChatCompletionMessage(
        role="assistant", content=content, tool_calls=calls))])


class ToolTests(unittest.TestCase):
    def test_large_directory_listing_is_bounded_and_stably_sorted(self):
        for index in range(205):
            (self.root / f"file-{index:03}.txt").touch()
        result = get_files_info(str(self.root))
        lines = result.splitlines()
        self.assertEqual(len(lines), 201)
        self.assertTrue(lines[0].startswith("- file-000.txt:"))
        self.assertTrue(lines[199].startswith("- file-199.txt:"))
        self.assertIn("5 more entries omitted", lines[-1])
        self.assertNotIn("file-204.txt", result)

    def test_python_tool_cannot_consume_the_callers_input(self):
        import sys
        script = self.root / "reader.py"
        script.write_text("print(input())", encoding="utf-8")
        code = (
            "from functions.run_python_file import run_python_file; "
            f"print(run_python_file({str(self.root)!r}, 'reader.py'))"
        )
        result = subprocess.run([sys.executable, "-c", code], input="private caller input\n",
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EOFError", result.stdout)
        self.assertNotIn("private caller input", result.stdout)

    def test_python_tool_does_not_inherit_sensitive_environment(self):
        write_file(
            self.root,
            "env.py",
            "import os; print(os.getenv('WORKBENCH_TEST_SECRET', 'missing'))",
        )
        with patch.dict("os.environ", {"WORKBENCH_TEST_SECRET": "private-value"}):
            result = run_python_file(str(self.root), "env.py")
        self.assertIn("missing", result)
        self.assertNotIn("private-value", result)

    def test_python_tool_does_not_inherit_connection_urls(self):
        write_file(self.root, "env.py", "import os; print(os.getenv('DATABASE_URL', 'missing'))")
        with patch.dict("os.environ", {"DATABASE_URL": "postgres://user:secret@db/private"}):
            result = run_python_file(str(self.root), "env.py")
        self.assertIn("missing", result)
        self.assertNotIn("postgres://", result)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "workspace"
        self.root.mkdir()

    def test_write_read_and_execute(self):
        self.assertIn("Successfully", write_file(str(self.root), "sub/test.py", "print('hello')"))
        self.assertEqual(get_file_content(str(self.root), "sub/test.py"), "print('hello')")
        self.assertIn("hello", run_python_file(str(self.root), "sub/test.py"))

    def test_read_strips_utf8_byte_order_mark(self):
        (self.root / "bom.py").write_bytes(b"\xef\xbb\xbfprint('hello')")
        self.assertEqual(get_file_content(str(self.root), "bom.py"), "print('hello')")

    def test_read_rejects_binary_content(self):
        (self.root / "asset.bin").write_bytes(b"safe-prefix\x00hidden")
        result = get_file_content(str(self.root), "asset.bin")
        self.assertTrue(result.startswith("Error: Binary file"))
        self.assertNotIn("hidden", result)

    def test_read_rejects_invalid_utf8_without_leaking_content(self):
        (self.root / "invalid.txt").write_bytes(b"visible\xffsecret")
        result = get_file_content(str(self.root), "invalid.txt")
        self.assertEqual(result, 'Error: File is not valid UTF-8 text: "invalid.txt"')
        self.assertNotIn("secret", result)

    def test_large_output_is_truncated(self):
        write_file(str(self.root), "noisy.py", "print('x' * 20000)")
        output = run_python_file(str(self.root), "noisy.py")
        self.assertIn("[Output truncated]", output)
        self.assertLess(len(output), 10100)

    def test_unencodable_content_preserves_existing_file(self):
        path = self.root / "notes.txt"
        path.write_text("original", encoding="utf-8")
        result = write_file(str(self.root), "notes.txt", "invalid \ud800")
        self.assertTrue(result.startswith("Error:"))
        self.assertEqual(path.read_text(encoding="utf-8"), "original")

    def test_overwrite_preserves_existing_mode(self):
        path = self.root / "launch"
        path.write_text("original", encoding="utf-8")
        path.chmod(0o751)
        self.assertIn("Successfully", write_file(str(self.root), "launch", "replacement"))
        self.assertEqual(path.read_text(encoding="utf-8"), "replacement")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o751)

    def test_failed_replace_preserves_existing_file(self):
        path = self.root / "notes.txt"
        path.write_text("original", encoding="utf-8")
        with patch("functions.write_file.os.replace", side_effect=OSError("blocked")):
            result = write_file(str(self.root), "notes.txt", "replacement")
        self.assertTrue(result.startswith("Error:"))
        self.assertEqual(path.read_text(encoding="utf-8"), "original")
        self.assertEqual([item.name for item in self.root.iterdir()], ["notes.txt"])

    def test_timeout_returns_tool_error(self):
        write_file(str(self.root), "slow.py", "pass")
        with patch("functions.run_python_file.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("python", 30)):
            self.assertIn("timed out", run_python_file(str(self.root), "slow.py"))

    def test_run_rejects_oversized_arguments_before_starting_process(self):
        write_file(str(self.root), "echo.py", "print('ok')")
        with patch("functions.run_python_file.subprocess.run") as run:
            self.assertIn("safe size", run_python_file(str(self.root), "echo.py", ["x" * 4097]))
            self.assertIn("at most 100", run_python_file(str(self.root), "echo.py", ["x"] * 101))
            run.assert_not_called()

    def test_symlink_escape(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        (outside / "secret.py").write_text("print('secret')")
        (self.root / "link").symlink_to(outside, target_is_directory=True)
        for result in [get_file_content(str(self.root), "link/secret.py"),
                       write_file(str(self.root), "link/new.txt", "oops"),
                       run_python_file(str(self.root), "link/secret.py")]:
            self.assertIn("outside", result)
        self.assertFalse((outside / "new.txt").exists())

    def test_traversal(self):
        self.assertIn("outside", write_file(str(self.root), "../escape", "oops"))

    def test_listing_survives_dangling_symlink(self):
        (self.root / "broken").symlink_to(self.root / "missing")
        (self.root / "regular.txt").write_text("hello")
        result = get_files_info(str(self.root))
        self.assertIn("- broken: Error:", result)
        self.assertIn("- regular.txt: file_size=5 bytes, is_dir=False", result)

    def test_listing_rejects_outside_symlink_metadata(self):
        outside = Path(self.temp.name) / "secret"
        outside.write_text("private")
        (self.root / "link").symlink_to(outside)
        (self.root / "inside").mkdir()
        (self.root / "local-link").symlink_to(self.root / "inside")
        result = get_files_info(str(self.root))
        self.assertIn("- link: Error: Path is outside", result)
        self.assertIn("- local-link: file_size=", result)
        self.assertNotIn("file_size=7 bytes", result)

    def test_invalid_tool_calls_return_errors(self):
        for name, arguments in [("unknown", "{}"), ("write_file", "{"),
                                ("write_file", "[]"), ("write_file", "{}"),
                                ("get_file_content", '{"working_directory":"/"}'),
                                ("run_python_file", '{"file_path":"a.py","args":[1]}')]:
            with self.subTest(name=name, arguments=arguments):
                result = call_function(tool(name, arguments), working_directory=self.root)
                self.assertEqual(result["tool_call_id"], "call_1")
                self.assertTrue(result["content"].startswith("Error:"))

    def test_read_only_blocks_mutations(self):
        for name in ["write_file", "run_python_file"]:
            self.assertIn("disabled", call_function(tool(name, "{}"), read_only=True)["content"])


class AgentTests(unittest.TestCase):
    def test_transcript_creates_directories_and_round_trips_unicode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reports" / "conversation.json"
            history = [{"role": "assistant", "content": "Café"}]
            save_transcript(path, history)
            self.assertEqual(json.loads(path.read_text()), history)
            self.assertTrue(path.read_text().endswith("\n"))

    def test_transcript_failure_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "conversation.json"
            path.write_text("existing")
            with patch("main.os.replace", side_effect=OSError("blocked")):
                with self.assertRaises(OSError):
                    save_transcript(path, [])
            self.assertEqual(path.read_text(), "existing")
            self.assertEqual([item.name for item in Path(directory).iterdir()],
                             ["conversation.json"])

    @patch.dict("os.environ", {"OPENROUTER_API_KEY": "test"})
    @patch("main.save_transcript", side_effect=OSError("disk full"))
    @patch("main.OpenAI")
    def test_transcript_failure_changes_success_exit_status(self, client_class, _save):
        client = client_class.return_value.__enter__.return_value
        client.chat.completions.create.return_value = response("Done")
        with patch("sys.stderr", new_callable=io.StringIO) as error:
            self.assertEqual(main(["Inspect", "--transcript", "result.json"]), 1)
        self.assertIn("Could not save transcript", error.getvalue())

    def test_tool_round_trip_without_usage(self):
        client = Mock()
        client.chat.completions.create.side_effect = [response(calls=[{
            "id": "call_1", "type": "function", "function": {
                "name": "get_files_info", "arguments": "{}"}}]), response("Done")]
        history = []
        self.assertEqual(run_agent(client, "Inspect", read_only=True, messages=history), "Done")
        self.assertEqual(history[3]["role"], "tool")
        tools = client.chat.completions.create.call_args.kwargs["tools"]
        self.assertEqual(len(tools), 2)

    def test_step_limit(self):
        client = Mock()
        client.chat.completions.create.return_value = response(calls=[{
            "id": "call_1", "type": "function", "function": {
                "name": "unknown", "arguments": "{}"}}])
        with self.assertRaisesRegex(RuntimeError, "Maximum steps"):
            run_agent(client, "Loop", max_steps=2)
        self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_empty_response(self):
        client = Mock()
        client.chat.completions.create.return_value = response()
        with self.assertRaisesRegex(RuntimeError, "empty final"):
            run_agent(client, "Test")
