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
        def __init__(self, show_only, order = None, touched = [], wrap_width = 25):
            super().__init__(show_only, order, group = None, touched = touched)
            self.wrap_width = wrap_width

        def __call__(self, task):
            if not self.show_only:
                # Show all existing fields.
                self.show_only = task.keys()

            sid = str(task["id"])
            if ':' in task["description"]:
                short, desc = task["description"].split(":")
                title = ":".join([sid,short.strip()])
            else:
                desc = task["description"]
                title = sid

            desc = "\n".join(textwrap.wrap(desc.strip(), self.wrap_width))

            if sid in touched:
                title = "*"+title+"*"

            segments = []
            for key in self.show_only:
                if key in task.keys() and key not in ["id", "description"]:
                    val = task[key]
                    segment = f"{key}: "
                    if type(val) == str:
                        segments.append(segment+t)
                    elif type(val) == list:
                        # FIXME Columns does not fit.
                        # g = Columns([f"+{t}" for t in val], expand = False)
                        g = rich.console.Group(*[f"+{t}" for t in val], fit = True)
                        segments.append(g)
                    else:
                        segments.append(segment+str(val))

            # FIXME Columns does not fit.
            # cols = Columns(segments)
            cols = rich.console.Group(*segments, fit = True)
            grp = rich.console.Group(desc, cols, fit = True)
            panel = rich.panel.Panel(grp, title = title,
                title_align="left", expand = False, padding = (0,1))

            return panel

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

            table = rich.table.Table(box = None, show_header = False, show_lines = True, expand = True)
            table.add_column('H')
            for k in keys:
                table.add_column(k)

            for task in tasks:
                taskers = self.tasker(task)
                if str(task['id']) in self.tasker.touched:
                    row = ['>']
                else:
                    row = ['']

                for k in keys:
                    if k in task:
                        val = taskers[k]
                        if type(val) == str:
                            row.append( val )
                        elif type(val) == list:
                            row.append( " ".join(val) )
                        else:
                            row.append( str(val) )
                    else:
                        row.append("")
                table.add_row(*[str(i) for i in row])
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
                    sections.append( rich.panel.Panel(self.stacker(groups[key]), title = key.upper(), title_align = "left", expand = False))
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
                row.append( rich.panel.Panel(self.stacker(groups[k]), title = k.upper(), title_align = "left", expand = True))

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
        return groups

class group:
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


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="XXX",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("-s", "--show", metavar="columns", type=str, default="id,description,tags", nargs=1,
            help="Ordered list of columns to show.")

    config = parser.add_argument_group('configuration options')
    config.add_argument("-d", "--data", metavar="FILE", type=str, default=".task", nargs=1,
            help="The input data file.")
    config.add_argument("--list-separator", metavar="CHARACTER", type=str, default=",", nargs=1,
            help="Separator used for lists that are passed as options arguments.")

    layouts = parser.add_argument_group('layout options')
    layouts.add_argument('--card-flat-wrap', metavar="NB", type=int, default=25,
            help="Number of character at which to wrap the description of Flat Cards.")

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

    # tasker = task.Card(show_only, touched = touched, wrap_width = asked.card_flat_wrap)
    tasker = task.Raw(show_only, touched = touched)

    # stacker = stack.Vertical(tasker)
    # stacker = stack.Flat(tasker)
    stacker = stack.RawTable(tasker)

    group_by_status = group.Status()
    sort_on_values = sort.OnValues(["pending","started","completed"])
    # sectioner = sections.Vertical(stacker, sort_on_values, group_by_status)
    sectioner = sections.Horizontal(stacker, sort_on_values, group_by_status)

    console = Console()
    console.rule("taskwarrior-fancy")
    console.print(sectioner(jdata))
