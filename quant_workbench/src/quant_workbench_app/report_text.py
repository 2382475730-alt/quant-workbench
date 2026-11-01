"""Readable Markdown in native Tk, scoped to report views."""
from pathlib import Path
import re
import tkinter.font as tkfont
import webbrowser
from .ui_presentation import color_text, change_column, number_value, change_color, UP_COLOR, DOWN_COLOR


def set_report_text(widget, content, source=None):
    widget.configure(state='normal')
    widget.delete('1.0', 'end')
    for tag in widget.tag_names():
        if tag.startswith('report_'):
            widget.tag_delete(tag)
    widget.tag_configure('report_h1', font=('Microsoft YaHei', 15, 'bold'), spacing1=10, spacing3=12)
    widget.tag_configure('report_h2', font=('Microsoft YaHei', 12, 'bold'), spacing1=12, spacing3=8)
    widget.tag_configure('report_h3', font=('Microsoft YaHei', 11, 'bold'), spacing1=10, spacing3=6)
    widget.tag_configure('report_bold', font=('Microsoft YaHei', 10, 'bold'))
    widget.tag_configure('report_code', font=('Consolas', 10), background='#edf2f6', spacing1=3, spacing3=3)
    widget.tag_configure('report_metric_up', foreground=UP_COLOR)
    widget.tag_configure('report_metric_down', foreground=DOWN_COLOR)
    link_count = 0

    def inline(value, tags=()):
        nonlocal link_count
        pattern = r'(!?)\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*|`([^`]+)`'
        position = 0
        for match in re.finditer(pattern, value):
            widget.insert('end', value[position:match.start()], tags)
            image, label, url, bold, code = match.groups()
            if url:
                if source and not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', url) and not url.startswith('#'):
                    url = (Path(source).parent / url).resolve().as_uri()
                tag = f'report_link_{link_count}'; link_count += 1
                widget.tag_configure(tag, foreground='#23688c', underline=True)
                widget.tag_bind(tag, '<Button-1>', lambda _, target=url: webbrowser.open(target))
                widget.tag_bind(tag, '<Enter>', lambda _: widget.configure(cursor='hand2'))
                widget.tag_bind(tag, '<Leave>', lambda _: widget.configure(cursor='xterm'))
                widget.insert('end', ('图表：' if image else '') + label, (*tags, tag))
            elif bold:
                widget.insert('end', bold, (*tags, 'report_bold'))
            else:
                widget.insert('end', code, (*tags, 'report_code'))
            position = match.end()
        widget.insert('end', value[position:], tags)

    lines = content.splitlines()
    i = 0
    table_count = 0
    code_block = False
    font = tkfont.Font(font=widget.cget('font'))
    while i < len(lines):
        line = lines[i]
        if line.startswith('```'):
            code_block = not code_block
        elif code_block:
            widget.insert('end', line + '\n', ('report_code',))
        elif line.lstrip().startswith('|'):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith('|'):
                cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', cell) for cell in cells):
                    rows.append(cells)
                i += 1
            positions = []
            offset = 0
            for col in range(max(map(len, rows), default=0)):
                offset += max((font.measure(r[col]) for r in rows if len(r) > col), default=60) + 30
                positions.append(offset)
            tag = f'report_table_{table_count}'; table_count += 1
            widget.tag_configure(tag, tabs=tuple(positions), wrap='none', spacing1=5, spacing3=5)
            header = f'report_table_header_{table_count}'
            widget.tag_configure(header, font=('Microsoft YaHei', 10, 'bold'), background='#edf2f6')
            for row_index, cells in enumerate(rows):
                tags = (tag, header) if row_index == 0 else (tag,)
                for col_index, cell in enumerate(cells):
                    if col_index: widget.insert('end', '\t', tags)
                    start = widget.index('end-1c')
                    inline(cell, tags)
                    if row_index and col_index < len(rows[0]) and change_column(rows[0][col_index]):
                        value = number_value(cell)
                        if value is not None and value:
                            if '回撤' in rows[0][col_index]: value = -abs(value)
                            widget.tag_add('report_metric_up' if change_color(value) == UP_COLOR else 'report_metric_down', start, 'end-1c')
                widget.insert('end', '\n', tags)
            continue
        elif match := re.match(r'^(#{1,6})\s+(.+)', line):
            inline(match[2], (f'report_h{min(3, len(match[1]))}',))
            widget.insert('end', '\n')
        else:
            line = re.sub(r'^\s*- ', '• ', line)
            inline(line)
            widget.insert('end', '\n')
        i += 1
    color_text(widget)
    widget.configure(state='disabled')
    widget.yview_moveto(0)
