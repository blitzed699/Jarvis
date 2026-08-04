import os
from typing import Dict, Any
from .base import BaseTool


class FileReadTool(BaseTool):
    name = "file_read"
    description = "Read the contents of a file. Params: path (str)"
    
    def run(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {"success": True, "result": content}
        except Exception as e:
            return {"success": False, "result": str(e)}


class FileListTool(BaseTool):
    name = "file_list"
    description = "List files in a directory. Params: path (str, default '.')"
    
    def run(self, path: str = ".") -> Dict[str, Any]:
        try:
            items = os.listdir(path)
            return {"success": True, "result": items}
        except Exception as e:
            return {"success": False, "result": str(e)}
