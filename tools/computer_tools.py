import os
import subprocess
import sys
import tempfile
from typing import Dict, Any
from .base import BaseTool


class OpenAppTool(BaseTool):
    name = "open_app"
    description = "Open an application by name. Params: app_name (str)"
    
    # Common Linux app mappings
    APP_MAP = {
        "chrome": "google-chrome",
        "firefox": "firefox",
        "browser": "firefox",
        "terminal": "gnome-terminal",
        "code": "code",
        "vscode": "code",
        "files": "nautilus",
        "file manager": "nautilus",
        "text editor": "gedit",
        "calculator": "gnome-calculator",
        "settings": "gnome-control-center",
    }
    
    def run(self, app_name: str) -> Dict[str, Any]:
        try:
            # Try mapped name first, then raw name
            command = self.APP_MAP.get(app_name.lower(), app_name)
            
            # Launch detached so JARVIS doesn't hang
            subprocess.Popen(
                [command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return {"success": True, "result": f"Opened {app_name}"}
        except FileNotFoundError:
            return {"success": False, "result": f"Application '{app_name}' not found. Try: {list(self.APP_MAP.keys())}"}
        except Exception as e:
            return {"success": False, "result": str(e)}


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write text or code to a file. Params: path (str), content (str)"
    
    def run(self, path: str, content: str) -> Dict[str, Any]:
        try:
            # Create parent directories if needed
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return {"success": True, "result": f"Wrote {len(content)} characters to {path}"}
        except Exception as e:
            return {"success": False, "result": str(e)}


class RunPythonTool(BaseTool):
    name = "run_python"
    description = "Execute Python code and return output. Params: code (str)"
    
    def run(self, code: str) -> Dict[str, Any]:
        try:
            # Write to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_path = f.name
            
            # Run it
            result = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            # Clean up
            os.unlink(temp_path)
            
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]: {result.stderr}"
            
            return {
                "success": result.returncode == 0,
                "result": output,
                "returncode": result.returncode
            }
        except Exception as e:
            return {"success": False, "result": str(e)}
