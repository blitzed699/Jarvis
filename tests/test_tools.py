import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tools.file_tools import FileReadTool, FileListTool
from tools.shell_tool import ShellTool
from tools.computer_tools import WriteFileTool, RunPythonTool
from tools.organize_tool import FileOrganizeTool


def test_file_list():
    tool = FileListTool()
    result = tool.run(path=".")
    assert result['success']
    assert isinstance(result['result'], list)
    print(f"FileListTool: found {len(result['result'])} items")

def test_write_and_read():
    write = WriteFileTool()
    read = FileReadTool()
    test_path = "/tmp/jarvis_test_tools.txt"
    content = "JARVIS test content"
    w = write.run(path=test_path, content=content)
    assert w['success']
    r = read.run(path=test_path)
    assert r['success']
    assert r['result'] == content
    print("WriteFileTool + FileReadTool: PASS")

def test_shell():
    tool = ShellTool()
    result = tool.run(command="echo 'JARVIS shell test'")
    assert result['success']
    assert "JARVIS shell test" in result['result']
    print("ShellTool: PASS")

def test_run_python():
    tool = RunPythonTool()
    result = tool.run(code="print(2 + 2)")
    assert result['success']
    assert "4" in result['result']
    print("RunPythonTool: PASS")

def test_organize():
    tool = FileOrganizeTool()
    os.makedirs("/tmp/jarvis_org_test", exist_ok=True)
    open("/tmp/jarvis_org_test/a.pdf", "w").close()
    open("/tmp/jarvis_org_test/b.txt", "w").close()
    result = tool.run(source_dir="/tmp/jarvis_org_test", rules=[{"pattern": "*.pdf", "target_dir": "TestPDFs"}])
    assert result['success']
    assert result['result']['total'] == 1
    print("OrganizeTool: PASS")


if __name__ == "__main__":
    test_file_list()
    test_write_and_read()
    test_shell()
    test_run_python()
    test_organize()
    print("\nAll tool tests: PASS")
