"""Run all tests on an isolated Windows desktop, without activating user windows."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

project=Path(__file__).resolve().parents[1]
out=project/'runtime/verification_artifacts'
out.mkdir(parents=True,exist_ok=True)
user=ctypes.windll.user32
user.CreateDesktopW.argtypes=[wintypes.LPCWSTR,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p]
user.CreateDesktopW.restype=wintypes.HANDLE
user.CloseDesktop.argtypes=[wintypes.HANDLE]
name='QuantWorkbenchTests_'+str(__import__('os').getpid())
handle=user.CreateDesktopW(name,None,None,0,0x01FF,None)
if not handle:raise ctypes.WinError()
try:
    startup=subprocess.STARTUPINFO();startup.lpDesktop=name
    result=subprocess.run([sys.executable,'-m','pytest','tests','-q'],cwd=project,
                          startupinfo=startup,capture_output=True,text=True,encoding='utf8',errors='replace')
    (out/'pytest_background.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf8')
    passed=re.search(r'(\d+) passed',result.stdout)
    record={'checked_at':datetime.now(timezone.utc).isoformat(),'exit_code':result.returncode,
            'tests_passed':int(passed[1]) if passed else 0,'isolated_desktop':True,
            'log':'pytest_background.log'}
    (out/'pytest_background.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    print(result.stdout);print(json.dumps(record))
finally:
    user.CloseDesktop(handle)
raise SystemExit(result.returncode)
