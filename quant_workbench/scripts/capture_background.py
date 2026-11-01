"""Render our own Tk window on an isolated desktop; capture only its HWND."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import sys
import time
import subprocess
import os
import faulthandler

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
    check_notes(app, name)
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
diagnostics=(OUT/'layout_diagnostics.log').open('w',encoding='utf8')
faulthandler.dump_traceback_later(25,repeat=True,file=diagnostics)
app.withdraw()
app.geometry('1420x940+40+40')
app.report_callback_exception = lambda exc,value,tb: app.errors.append(str(value))
records=[]
note_geometry=[]
def check_notes(widget, name):
    from quant_workbench_app.ui_presentation import NoteLabel
    if isinstance(widget, NoteLabel) and widget.winfo_ismapped():
        note_geometry.append({'page':name,'text':widget.cget('text'),
            'width':widget.winfo_width(),'height':widget.winfo_height(),
            'requested':widget.winfo_reqheight(),'lines':widget.cget('height'),
            'display_lines':widget.count('1.0','end-1c','displaylines'),
            'end_visible':widget.dlineinfo('end-1c') is not None})
    for child in widget.winfo_children():check_notes(child,name)
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
            panel.pages.select(panel.frames['overview'])
            app.update()
            cards_bottom=max(c.winfo_rooty()+c.winfo_height() for c in panel.overview_metric_cards)
            viewport_bottom=panel.overview_scroll.winfo_rooty()+panel.overview_scroll.winfo_height()
            assert cards_bottom <= viewport_bottom, f'Default industry cards clipped: {cards_bottom} > {viewport_bottom}'
            before = panel.overview_scroll.yview()[0]
            panel.overview_metric_cards[0].winfo_children()[0].event_generate('<MouseWheel>',delta=-120)
            app.update()
            assert panel.overview_scroll.yview()[0] > before, 'Nested card wheel must scroll overview'
            panel.scroll_to_overview_companies();app.update()
            records.append(capture(app, 'overview_company_section'))
            panel.overview_scroll.yview_moveto(0.0);app.update()
            for code in panel.overview_profiles:
                panel.overview_table.selection_set(code)
                details = panel.open_overview_company()
                details.geometry('990x730+40+40');app.update()
                records.append(capture(details, f'overview_cash_{code}'));details.destroy()
            for metric in ('capacity','price','hog_inventory','slaughter','pork_output','psy'):
                details = panel.open_overview_metric(metric)
                details.geometry('960x700+40+40');app.update()
                records.append(capture(details, f'overview_metric_{metric}'));details.destroy()
            details = panel.open_overview_sources();app.update()
            records.append(capture(details, 'overview_official_sources'));details.destroy()
            # Check all data exports without activating an external application.
            folder = panel.export_overview()
            assert folder.is_relative_to(PROJECT/'runtime/exports/swine_overview')
            assert (folder/'companies.csv').is_file() and (folder/'sources.json').is_file()
            panel.overview_export_note.pack_forget()
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
            panel.pages.select(1);app.update()
            records.append(capture(app, 'stocks_financial_reading'))
        if key in ('pork', 'enhancement', 'small'):
            before=set(app.winfo_children())
            if key == 'pork':
                panel.open_deep_report()
            else:
                panel.open_text('reports/' + ('enhancement_v1' if key == 'enhancement' else 'small_capital_v1') + '/report.md', '研究报告')
            app.update()
            documents=[w for w in app.winfo_children() if w not in before]
            for window in documents:
                window.geometry('1000x740+40+40');app.update()
                records.append(capture(window, f'{key}_reading_dialog'));window.destroy()
    app.show_module('pork')
    app.panels['pork'].valuation_company.set(next(iter(app.panels['pork'].valuation_names)))
    app.panels['pork'].draw_valuation()
    app.geometry('1100x700+40+40')
    for index in range(len(app.panels['pork'].pages.tabs())):
        app.panels['pork'].pages.select(index)
        app.update()
        records.append(capture(app, f'pork_small_{index}'))
        if index == 0:
            app.panels['pork'].scroll_to_overview_companies();app.update()
            records.append(capture(app, 'pork_small_overview_jump'))
            app.panels['pork'].overview_scroll.yview_moveto(1.0);app.update()
            records.append(capture(app, 'pork_small_overview_bottom'))
            app.panels['pork'].overview_scroll.yview_moveto(0.0)
    for section in ('cycle','companies','valuation'):
        app.panels['pork'].pages.select(app.panels['pork'].frames[section])
        for index in range(1,len(app.panels['pork'].research_books[section].tabs())):
            app.panels['pork'].research_books[section].select(index)
            app.update()
            records.append(capture(app,f'swine_deep_small_{section}'+('' if index==1 else f'_{index}')))
            check_notes(app.panels['pork'],f'swine_deep_small_{section}_{index}')
        app.panels['pork'].research_books[section].select(0)
    for key in ('stocks','enhancement','small'):
        app.show_module(key);app.update()
        panel=app.panels[key]
        for index in range(len(panel.pages.tabs())):
            panel.pages.select(index);app.update()
            records.append(capture(app,f'{key}_small_{index}'))
            check_notes(panel,f'{key}_small_{index}')
    clipped=[row for row in note_geometry if not row['end_visible'] or row['height']<row['requested']]
    if clipped:
        raise RuntimeError('Clipped explanatory text: '+str([(row['page'],row['text'][:40]) for row in clipped]))
    if app.errors:
        raise RuntimeError(str(app.errors))
finally:
    faulthandler.cancel_dump_traceback_later()
    diagnostics.close()
    app.destroy()
    (OUT/'capture_report.json').write_text(json.dumps({'captures':records,'errors':app.errors},ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'note_geometry.json').write_text(json.dumps(note_geometry,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'captures':len(records),'errors':app.errors}))
