import os
import shutil
import fnmatch
from datetime import datetime
from typing import Dict, Any, List
from .base import BaseTool


class FileOrganizeTool(BaseTool):
    name = "organize_files"
    description = "Move files by pattern into target folders. Params: source_dir (str), rules (list of dicts with 'pattern' and 'target_dir')"

    def run(self, source_dir: str, rules: List[Dict[str, str]]) -> Dict[str, Any]:
        try:
            if not os.path.exists(source_dir):
                return {"success": False, "result": f"Source not found: {source_dir}"}

            moved = []
            files = [f for f in os.listdir(source_dir) if os.path.isfile(os.path.join(source_dir, f))]

            for filename in files:
                file_path = os.path.join(source_dir, filename)
                for rule in rules:
                    pattern = rule.get("pattern", "")
                    target_dir = rule.get("target_dir", "")
                    if fnmatch.fnmatch(filename.lower(), pattern.lower()):
                        full_target = os.path.expanduser(os.path.join("~", target_dir))
                        os.makedirs(full_target, exist_ok=True)
                        target_path = os.path.join(full_target, filename)
                        if os.path.exists(target_path):
                            base, ext = os.path.splitext(filename)
                            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                            target_path = os.path.join(full_target, f"{base}_{ts}{ext}")
                        shutil.move(file_path, target_path)
                        moved.append({"file": filename, "to": target_path, "rule": pattern})
                        break

            return {"success": True, "result": {"moved": moved, "total": len(moved)}}

        except Exception as e:
            return {"success": False, "result": str(e)}
