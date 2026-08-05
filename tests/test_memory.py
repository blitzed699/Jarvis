import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import shutil
from core.memory import JARVISMemory


def test_memory():
    if os.path.exists('memory'):
        shutil.rmtree('memory')
    
    mem = JARVISMemory()
    mem.log_message("user", "My name is Alex.")
    mem.log_message("jarvis", "Hello Alex.")
    mem.store_fact("User's name is Alex", category="person")
    mem.store_fact("User prefers dark mode", category="preference")
    
    wm = mem.get_working_memory(current_query="What do you know about me?")
    
    assert len(wm['recent_facts']) == 2
    assert len(wm['recent_conversation']) == 2
    
    formatted = mem.format_working_memory_for_prompt(wm)
    assert "Alex" in formatted
    assert "dark mode" in formatted
    
    mem.close()
    print("test_memory: PASS")


if __name__ == "__main__":
    test_memory()
