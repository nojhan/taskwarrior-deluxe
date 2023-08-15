#!/usr/bin/env python3

import os
import re
import sys
import json
import argparse
import textwrap
import subprocess

import rich
# For some reason this is not imported by the command above.
from rich.console import Console
from rich.columns import Columns

class Widget:
    def __init__(self, order, group = None):
        self.order = order
        self.group = group

class Tasker(Widget):
    def __init__(self, show_only, order, group = None, touched = []):
        super().__init__(order, group)
        self.show_only = show_only
        self.touched = touched

    def __call__(self, task):
        raise NotImplementedError

class Stacker(Widget):
    def __init__(self, tasker, order, group):
        super().__init__(order, group)
        self.tasker = tasker

    def __call__(self, tasks):
        raise NotImplementedError

class Sectioner(Widget):
    def __init__(self, stacker, order, group):
        super().__init__(order, group)
        self.stacker = stacker

    def __call__(self, tasks):
        raise NotImplementedError


class task:
    class Card(Tasker):
        def __init__(self, show_only, order = None, touched = [], wrap_width = 25, tag_icons = "+"):
            super().__init__(show_only, order, group = None, touched = touched)
            self.wrap_width = wrap_width
            self.tag_icons = tag_icons

        def _make(self, task):
            if not self.show_only:
                # Show all existing fields.
                self.show_only = task.keys()

            sid = str(task["id"])
            if ':' in task["description"]:
                short, desc = task["description"].split(":")
                title = rich.text.Text(sid, style='id') + rich.text.Text(":", style="default") + rich.text.Text(short.strip(), style='short_description')
                desc = rich.text.Text("\n".join(textwrap.wrap(desc.strip(), self.wrap_width)), style='long_description')
            elif len(task["description"]) <= self.wrap_width - 8:
                d = task["description"].strip()
                title = rich.text.Text(sid, style='id') + rich.text.Text(":", style="default") + rich.text.Text(d, style='short_description')
                desc = None
            else:
                desc = task["description"]
                desc = rich.text.Text("\n".join(textwrap.wrap(desc.strip(), self.wrap_width)), style='description')
                title = rich.text.Text(sid, style='id')

            segments = []
            for key in self.show_only:
                if key in task.keys() and key not in ["id", "description"]:
                    val = task[key]
                    segment = f"{key}: "
                    if type(val) == str:
                        segments.append(rich.text.Text(segment+val, style=key))
                    elif type(val) == list:
                        # FIXME Columns does not fit.
                        # g = Columns([f"+{t}" for t in val], expand = False)
                        lst = []
                        for t in val:
                           lst.append( \
                               rich.text.Text(self.tag_icons[0], style="tags_ends") + \
                               rich.text.Text(t, style=key) + \
                               rich.text.Text(self.tag_icons[1], style="tags_ends") \
                           )
                        g = rich.console.Group(*lst, fit = True)
                        # g = rich.console.Group(*[rich.text.Text(f"{self.tag_icons[0]}{t}{self.tag_icons[1]}", style=key) for t in val], fit = True)
                        segments.append(g)
                    else:
                        segments.append(rich.text.Text(segment+str(val), style=key))

            # FIXME Columns does not fit.
            # cols = Columns(segments)
            cols = rich.console.Group(*segments, fit = True)
            if desc:
                body = rich.console.Group(desc, cols, fit = True)
            else:
                body = cols

            return title,body

        def __call__(self, task):
            title, body = self._make(task)

            sid = str(task["id"])
            if sid in self.touched:
                panel = rich.panel.Panel(body, title = title,
                    title_align="left", expand = False, padding = (0,1), border_style = 'touched', box = rich.box.DOUBLE_EDGE)
            else:
                panel = rich.panel.Panel(body, title = title,
                    title_align="left", expand = False, padding = (0,1))

            return panel

    class Sheet(Card):
        def __init__(self, show_only, order = None, touched = [], wrap_width = 25, tag_icons = "🏷  ", title_ends=["\n "," "]):
            super().__init__(show_only, order, touched = touched, wrap_width = wrap_width, tag_icons = tag_icons)
            self.title_ends = title_ends

        def __call__(self, task):
            title, body = self._make(task)

            t = rich.text.Text(self.title_ends[0], style="short_description_ends") + \
                title + \
                rich.text.Text(self.title_ends[1], style="short_description_ends")

            sid = str(task["id"])
            if sid in self.touched:
                b = rich.panel.Panel(body, box = rich.box.SIMPLE_HEAD, style='touched')
            else:
                b = rich.panel.Panel(body, box = rich.box.SIMPLE_HEAD, style='description')

            sheet = rich.console.Group(t,b)
            return sheet


    class Raw(Tasker):
        def __init__(self, show_only, order = None, touched = []):
            super().__init__(show_only, order, group = None, touched = touched)

        def __call__(self, task):
            if not self.show_only:
                # Show all existing fields.
                self.show_only = task.keys()

            raw = {}
            for k in self.show_only:
                if k in task:
                    raw[k] = task[k]
                else:
                    raw[k] = None

            return raw

class stack:
    class RawTable(Stacker):
        def __init__(self, tasker):
            super().__init__(tasker, order = None, group = None)

        def __call__(self, tasks):
            keys = self.tasker.show_only

            table = rich.table.Table(box = None, show_header = False, show_lines = True, expand = True, row_styles=['row_odd', 'row_even'])
            table.add_column('H')
            for k in keys:
                table.add_column(k)

            for task in tasks:
                taskers = self.tasker(task)
                if str(task['id']) in self.tasker.touched:
                    row = [rich.text.Text('▶', style = 'touched')]
                else:
                    row = ['']

                for k in keys:
                    if k in task:
                        val = taskers[k]
                        if type(val) == str:
                            if k == 'description' and ':' in val:
                                short, desc = val.split(':')
                                # FIXME groups add a newline or hide what follows, no option to avoid it.
                                # row.append( rich.console.Group(
                                #     rich.text.Text(short+':', style='short_description', end='\n'),
                                #     rich.text.Text(desc, style='description', end='\n')
                                # ))
                                # FIXME style leaks on all texts:
                                row.append( rich.text.Text(short, style='short_description', end='') + \
                                            rich.text.Text(':', style='default', end='') + \
                                            rich.text.Text(desc, style='long_description', end='') )
                            else:
                                row.append( rich.text.Text(val, style=k) )
                        elif type(val) == list:
                            # FIXME use Columns if does not expand.
                            row.append( rich.text.Text(" ".join(val), style=k) )
                        else:
                            row.append( rich.text.Text(str(val), style=k) )
                    else:
                        row.append("")
                table.add_row(*[t for t in row])
            return table


    class Vertical(Stacker):
        def __init__(self, tasker):
            super().__init__(tasker, order = None, group = None)

        def __call__(self, tasks):
            stack = rich.table.Table(box = None, show_header = False, show_lines = False, expand = True)
            stack.add_column("Tasks")
            for task in tasks:
               stack.add_row( self.tasker(task) )
            return stack

    class Flat(Stacker):
        def __init__(self, tasker):
            super().__init__(tasker, order = None, group = None)

        def __call__(self, tasks):
            stack = []
            for task in tasks:
               stack.append( self.tasker(task) )
            cols = rich.columns.Columns(stack)
            return cols

class sections:
    class Vertical(Sectioner):
        def __init__(self, stacker, order, group):
            super().__init__(stacker, order, group)

        def __call__(self, tasks):
            sections = []
            groups = self.group(tasks)
            for key in self.order():
                if key in groups:
                    sections.append( rich.panel.Panel(self.stacker(groups[key]), title = rich.text.Text(key.upper(), style=key), title_align = "left", expand = False))
            return rich.console.Group(*sections)

    class Horizontal(Sectioner):
        def __init__(self, stacker, order, group):
            super().__init__(stacker, order, group)

        def __call__(self, tasks):
            sections = []
            groups = self.group(tasks)
            table = rich.table.Table(box = None, show_header = False, show_lines = False)
            keys = []
            for key in self.order():
                if key in groups:
                    table.add_column(key)
                    keys.append(key)

            row = []
            for k in keys:
                row.append( rich.panel.Panel(self.stacker(groups[k]), title = rich.text.Text(k.upper(), style=k), title_align = "left", expand = True, border_style="title"))

            table.add_row(*row)
            return table

class SectionSorter:
    def __call__(self):
        raise NotImplementedError

class sort:
    class Tasks:
        def make(self, tasks, field, reverse = False):
            return sorted(tasks, key = lambda t: t[field], reverse = reverse)

    class OnValues(SectionSorter):
        def __init__(self, values):
            self.values = values

        def __call__(self):
            return self.values

class Grouper:
    """Group tasks by field values."""
    def __init__(self, field):
        self.field = field

    def __call__(self, tasks):
        groups = {}
        for task in tasks:
            if self.field in task:
                if task[self.field] in groups:
                    groups[ task[self.field] ].append(task)
                else:
                    groups[ task[self.field] ] = [task]
            else:
                if "" in groups:
                    groups[ "" ].append( task )
                else:
                    groups[ "" ] = [task]
        return groups

class group:
    class Field(Grouper):
        pass

    class Status(Grouper):
        def __init__(self):
            super().__init__("status")

        def __call__(self, tasks):
            groups = {}
            for task in tasks:
                if "start" in task:
                    if "started" in groups:
                        groups["started"].append(task)
                    else:
                        groups["started"] = [task]
                elif self.field in task:
                    if task[self.field] in groups:
                        groups[ task[self.field] ].append(task)
                    else:
                        groups[ task[self.field] ] = [task]

            return groups


def call_taskwarrior(args:list[str] = ['export']) -> str:
    # Local file.
    env = os.environ.copy()
    env["TASKDATA"] = asked.data

    cmd = ['task'] + args
    try:
        p = subprocess.Popen( " ".join(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            env=env,
        )
        out, err = p.communicate()

    except subprocess.CalledProcessError as exc:
        print("ERROR:", exc.returncode, exc.output, err)
        sys.exit(exc.returncode)
    else:
        return out.decode('utf-8')


def get_data():
    out = call_taskwarrior(['export'])
    try:
        jdata = json.loads(out)
    except json.decoder.JSONDecodeError as exc:
        print("ERROR:", exc.returncode, exc.output)
    else:
        return jdata


def parse_touched(out):
    return re.findall('[ModifyingCreated]+ task ([0-9]+)', out)


def get_swatches(name = None):
    swatches = {

        "none": {
            'touched': '',
            'id': '',
            'title': '',
            'description': '',
            'short_description': '',
            'short_description_ends': '',
            'long_description': '',
            'entry': '',
            'modified': '',
            'started': '',
            'status': '',
            'uuid': '',
            'tags': '',
            'tags': '',
            'urgency': '',
            'row_odd': '',
            'row_even' : '',
        },

        "nojhan": {
            'touched': '#4E9A06',
            'id': 'color(214)',
            'title': '',
            'description': 'color(231)',
            'short_description': 'color(231)',
            'short_description_ends': '',
            'long_description': 'default',
            'entry': '',
            'modified': 'color(240)',
            'started': '',
            'status': 'bold italic white',
            'uuid': '',
            'tags': 'color(33)',
            'tags': 'color(33)',
            'urgency': 'color(219)',
            'row_odd': 'on #262121',
            'row_even' : 'on #2d2929',
        },

        "chalky": {
            'touched': 'color(0) on color(15)',
            'id': 'bold color(160) on white',
            'title': '',
            'description': 'black on white',
            'short_description': 'bold black on white',
            'short_description_ends': 'white',
            'long_description': 'black on white',
            'entry': '',
            'modified': 'color(240)',
            'started': '',
            'status': 'bold italic white',
            'uuid': '',
            'tags': 'color(166) on white',
            'tags_ends': 'white',
            'urgency': 'color(219)',
            'row_odd': '',
            'row_even' : '',
        },

        "carbon": {
            'touched': 'color(15) on color(0)',
            'id': 'bold color(196) on color(236)',
            'title': '',
            'description': 'white on color(236)',
            'short_description': 'bold white on color(236)',
            'short_description_ends': 'color(236)',
            'long_description': 'white on color(236)',
            'entry': '',
            'modified': '',
            'started': '',
            'status': 'bold italic white',
            'uuid': '',
            'tags': 'bold black on color(88)',
            'tags_ends': 'color(88)',
            'urgency': 'color(219)',
            'row_odd': '',
            'row_even' : '',
        },

    }
    if name:
        return swatches[name]
    else:
        return swatches


def get_icons(name=None):

    icons = {

        'none' : {
            'tag': ['', ''],
            'short': ['', ''],
        },

        'ascii' : {
            'tag': ['+', ''],
            'short': ['', ''],
        },

        'emojis' : {
            'tag': ['🏷  ', ''],
            'short': ['\n ', ' '],
        },

        'power' : {
            'tag': ['', ''],
            'short': ['\n ', ' '],
        },

    }
    if name:
        return icons[name]
    else:
        return icons

def get_layouts(kind = None, name = None):
    # FIXME use introspection to extract that automatically.
    available = {
        "task": {
            "Raw": task.Raw,
            "Card": task.Card,
            "Sheet": task.Sheet,
        },
        "stack": {
            "RawTable": stack.RawTable,
            "Vertical": stack.Vertical,
            "Flat": stack.Flat,
        },
        "sections": {
            "Vertical": sections.Vertical,
            "Horizontal": sections.Horizontal,
        },
    }
    if kind and name:
        return available[kind][name]
    elif kind:
        return available[kind]
    elif not kind and not name:
        return available
    else:
        raise KeyError("cannot get layouts with 'name' only")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="XXX",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("-s", "--show", metavar="columns", type=str, default="id,priority,description,tags", nargs=1,
            help="Ordered list of columns to show.")


    config_grp = parser.add_argument_group('configuration options')

    config_grp.add_argument("-d", "--data", metavar="FILE", type=str, default=".task", nargs=1,
            help="The input data file.")

    config_grp.add_argument("--list-separator", metavar="CHARACTER", type=str, default=",", nargs=1,
            help="Separator used for lists that are passed as options arguments.")


    layouts_grp = parser.add_argument_group('layout options')

    layouts_grp.add_argument('-t', '--layout-task', metavar='NAME', type=str, default='Raw',
            choices = get_layouts('task').keys(), help="Layout managing tasks.")
    layouts_grp.add_argument('-k', '--layout-stack', metavar='NAME', type=str, default='RawTable',
            choices = get_layouts('stack').keys(), help="Layout managing stacks.")
    layouts_grp.add_argument('-c', '--layout-sections', metavar='NAME', type=str, default='Horizontal',
            choices = get_layouts('sections').keys(), help="Layout managing sections.")
    layouts_grp.add_argument('-C', '--layout-subsections', metavar='NAME', type=str, default=None,
            choices = get_layouts('sections').keys(), help="Layout managing sub-sections.")

    layouts_grp.add_argument('-T', '--swatch', metavar='NAME', type=str, default='none',
            choices = get_swatches().keys(), help="Color chart.")

    layouts_grp.add_argument('-I', '--icons', metavar='NAME', type=str, default='none',
            choices = get_icons().keys(), help="Additional decorative characters.")

    layouts_grp.add_argument('--card-wrap', metavar="NB", type=int, default=25,
            help="Number of character at which to wrap the description of Cards tasks.")

    # Capture whatever remains.
    parser.add_argument('cmd', nargs="*")

    asked = parser.parse_args()

    # First pass arguments to taskwarrior and let it do its magic.
    out = call_taskwarrior(asked.cmd)
    if "Description" not in out:
        print(out.strip())
    touched = parse_touched(out)
    # print("Touched:",touched)

    # Then get the resulting data.
    jdata = get_data()
    # print(json.dumps(jdata, indent=4))

    showed = asked.show.split(asked.list_separator)
    if not showed:
        show_only = None
    else:
        show_only = showed

    swatch = rich.theme.Theme(get_swatches(asked.swatch))
    layouts = get_layouts()

    if asked.layout_task == "Card":
        tasker = layouts['task']['Card'](show_only, touched = touched, wrap_width = asked.card_wrap, tag_icons = get_icons(asked.icons)['tag'])
    elif asked.layout_task == "Sheet":
        icons = get_icons(asked.icons)
        tasker = layouts['task']['Sheet'](show_only, touched = touched, wrap_width = asked.card_wrap, tag_icons = icons['tag'], title_ends = icons['short'])
    else:
        tasker = layouts['task'][asked.layout_task](show_only, touched = touched)

    stacker = layouts['stack'][asked.layout_stack](tasker)

    group_by_status = group.Status()
    group_by_priority = group.Field("priority")
    sort_on_status_values = sort.OnValues(["pending","started","completed"])
    sort_on_priority_values = sort.OnValues(["H","M","L",""])

    if asked.layout_subsections:
        subsectioner = layouts['sections'][asked.layout_subsections](stacker, sort_on_priority_values, group_by_priority)
        sectioner = layouts['sections'][asked.layout_sections](subsectioner, sort_on_status_values, group_by_status)
    else:
        sectioner = layouts['sections'][asked.layout_sections](stacker, sort_on_status_values, group_by_status)

    console = Console(theme = swatch)
    # console.rule("taskwarrior-deluxe")
    console.print(sectioner(jdata))

