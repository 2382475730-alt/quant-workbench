"""Render our own Tk window on an isolated desktop; capture only its HWND."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import time
import subprocess
import os

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))
from PIL import Image
from quant_workbench_app.desktop import Workbench
from quant_workbench_app.paths import SETTINGS

OUT = PROJECT / 'runtime/verification_artifacts/background'
OUT.mkdir(parents=True, exist_ok=True)
u, g = ctypes.windll.user32, ctypes.windll.gdi32
u.GetParent.argtypes = [wintypes.HWND]
u.GetParent.restype = wintypes.HWND
u.GetWindowDC.argtypes = [wintypes.HWND]
u.GetWindowDC.restype = wintypes.HDC
g.CreateCompatibleDC.argtypes = [wintypes.HDC]
g.CreateCompatibleDC.restype = wintypes.HDC
g.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
g.CreateCompatibleBitmap.restype = wintypes.HBITMAP
g.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
g.SelectObject.restype = wintypes.HGDIOBJ
u.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
g.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
g.DeleteObject.argtypes = [wintypes.HGDIOBJ]
g.DeleteDC.argtypes = [wintypes.HDC]
u.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]

class Header(ctypes.Structure):
    _fields_ = [('size',wintypes.DWORD),('width',wintypes.LONG),('height',wintypes.LONG),
                ('planes',wintypes.WORD),('bits',wintypes.WORD),('compression',wintypes.DWORD),
                ('image_size',wintypes.DWORD),('x',wintypes.LONG),('y',wintypes.LONG),
                ('used',wintypes.DWORD),('important',wintypes.DWORD)]

def capture(app, name):
    app.update_idletasks()
    hwnd = u.GetParent(app.winfo_id())
    rect = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right-rect.left, rect.bottom-rect.top
    assert '--isolated' in sys.argv, 'Capture requires isolated desktop'
    dc = u.GetWindowDC(hwnd)
    memory = g.CreateCompatibleDC(dc)
    bitmap = g.CreateCompatibleBitmap(dc, width, height)
    old = g.SelectObject(memory, bitmap)
    try:
        if not u.PrintWindow(hwnd, memory, 2):
            raise RuntimeError('PrintWindow failed')
        header = Header(ctypes.sizeof(Header), width, -height, 1, 32, 0, width*height*4, 0, 0, 0, 0)
        buffer = ctypes.create_string_buffer(width*height*4)
        if not g.GetDIBits(memory, bitmap, 0, height, buffer, ctypes.byref(header), 0):
            raise RuntimeError('GetDIBits failed')
        img = Image.frombytes('RGB', (width,height), buffer.raw, 'raw', 'BGRX')
        if all(lo == hi for lo, hi in img.getextrema()):
            raise RuntimeError('Blank screenshot')
        img.save(OUT / (name+'.png'))
        return {'name':name, 'size':[width,height], 'window_origin':[rect.left,rect.top]}
    finally:
        g.SelectObject(memory, old)
        g.DeleteObject(bitmap)
        g.DeleteDC(memory)
        u.ReleaseDC(hwnd, dc)

if '--isolated' not in sys.argv:
    u.CreateDesktopW.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    u.CreateDesktopW.restype = wintypes.HANDLE
    u.CloseDesktop.argtypes = [wintypes.HANDLE]
    desktop_name = 'QuantWorkbenchQA_' + str(os.getpid())
    handle = u.CreateDesktopW(desktop_name, None, None, 0, 0x01FF, None)
    if not handle:
        raise ctypes.WinError()
    try:
        startup = subprocess.STARTUPINFO()
        startup.lpDesktop = desktop_name
        result = subprocess.run([sys.executable, __file__, '--isolated'], startupinfo=startup, capture_output=True, text=True)
        print(result.stdout)
        if result.returncode:
            print(result.stderr)
        sys.exit(result.returncode)
    finally:
        u.CloseDesktop(handle)

app = Workbench(state_path=OUT/f'capture_state_{time.time_ns()}.json')
app.withdraw()
app.geometry('1420x940+40+40')
app.report_callback_exception = lambda exc,value,tb: app.errors.append(str(value))
records=[]
try:
    app.deiconify()
    for _ in range(10):
        app.update()
        time.sleep(.02)
    for key in app.buttons:
        app.show_module(key)
        app.update()
        panel=app.panels[key]
        for index in range(len(panel.pages.tabs())):
            panel.pages.select(index)
            app.update()
            records.append(capture(app, f'{key}_{index}'))
        if key == 'pork':
            for section in ('cycle','companies','valuation'):
                panel.pages.select(panel.frames[section])
                for index in range(1,len(panel.research_books[section].tabs())):
                    panel.research_books[section].select(index)
                    app.update()
                    records.append(capture(app,f'swine_deep_{section}'+('' if index==1 else f'_{index}')))
                panel.research_books[section].select(0)
            panel.pages.select(panel.frames['valuation'])
            for label, code in panel.valuation_names.items():
                panel.valuation_company.set(label)
                panel.draw_valuation()
                app.update()
                records.append(capture(app, f'swine_valuation_{code}'))
            panel.pages.select(panel.frames['companies'])
            for code in panel.valuation_names.values():
                panel.company_table.selection_set(code)
                panel.show_company()
                app.update()
                records.append(capture(app, f'swine_company_{code}'))
            for label,code in panel.deep_names.items():
                panel.pages.select(panel.frames['companies']);panel.research_books['companies'].select(1)
                panel.funding_company.set(label);panel.calculate_funding();app.update()
                records.append(capture(app,f'swine_funding_{code}'))
                panel.pages.select(panel.frames['valuation']);panel.research_books['valuation'].select(1)
                panel.recovery_company.set(label);panel.calculate_recovery();app.update()
                records.append(capture(app,f'swine_recovery_{code}'))
            panel.research_books['companies'].select(0);panel.research_books['valuation'].select(2)
            for label,code in panel.bridge_names.items():
                panel.bridge_company.set(label);panel.calculate_profit_bridge();app.update()
                records.append(capture(app,f'swine_profit_bridge_{code}'))
            panel.research_books['valuation'].select(0)
            sources=panel.open_source_catalog();sources.geometry('1000x680+40+40');sources.source_query.set('002714');app.update()
            records.append(capture(sources,'swine_source_search'));sources.destroy()
            prices=panel.open_price_observations();prices.geometry('1060x660+40+40');app.update()
            records.append(capture(prices,'swine_price_observations'));prices.destroy()
        if key == 'stocks':
            panel.pages.select(0)
            for label, code in panel.names.items():
                panel.company.set(label)
                panel.refresh()
                app.update()
                records.append(capture(app, f'stocks_{code}'))
    app.show_module('pork')
    app.panels['pork'].valuation_company.set(next(iter(app.panels['pork'].valuation_names)))
    app.panels['pork'].draw_valuation()
    app.geometry('1100x700+40+40')
    for index in range(len(app.panels['pork'].pages.tabs())):
        app.panels['pork'].pages.select(index)
        app.update()
        records.append(capture(app, f'pork_small_{index}'))
    for section in ('cycle','companies','valuation'):
        app.panels['pork'].pages.select(app.panels['pork'].frames[section])
        for index in range(1,len(app.panels['pork'].research_books[section].tabs())):
            app.panels['pork'].research_books[section].select(index)
            app.update()
            records.append(capture(app,f'swine_deep_small_{section}'+('' if index==1 else f'_{index}')))
        app.panels['pork'].research_books[section].select(0)
    if app.errors:
        raise RuntimeError(str(app.errors))
finally:
    app.destroy()
    (OUT/'capture_report.json').write_text(json.dumps({'captures':records,'errors':app.errors},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'captures':len(records),'errors':app.errors}))
