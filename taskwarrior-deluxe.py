#!/usr/bin/env python3

import os
import re
import sys
import json
import queue
import pathlib
import textwrap
import subprocess

import rich
# For some reason this is not imported by the command above.
from rich.console import Console
from rich.columns import Columns

error_codes = {
    "NO_DATA_FILE": 100,
    "CANNOT_INIT": 200,
}


def error(name,msg):
    print("ERROR:",msg)
    sys.exit(error_codes[name])


class Widget:
    pass

class Tasker(Widget):
    def __init__(self, show_only, order = None, group = None, touched = []):
        self.show_only = show_only
        self.touched = touched
        self.sorter = order
        self.grouper = group

    def __call__(self, task):
        raise NotImplementedError

class Stacker(Widget):
    def __init__(self, tasker, sorter = None):
        self.tasker = tasker
        if sorter:
            self.sorter = sorter
        else:
            self.sorter = stack.sort.Noop()

    def __call__(self, tasks):
        raise NotImplementedError

class StackSorter:
    def __init__(self, field, reverse = False):
        self.field = field
        self.reverse = reverse

    def __call__(self, tasks):
       raise NotImplementedError 


class Sectioner(Widget):
    def __init__(self, stacker, order, group):
        self.stacker = stacker
        self.sorter = order
        self.grouper = group

    def order(self, groups):
        if self.sorter:
            return self.sorter()
        else:
            return groups.keys()

    def group(self, tasks):
        if self.grouper:
            return self.grouper(tasks)
        else:
            return {"":tasks}

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
            if ":" in task["description"]:
                short, desc = task["description"].split(":")
                title = rich.text.Text(sid, style="color.id") + rich.text.Text(":", style="default") + rich.text.Text(short.strip(), style="color.description.short")
                desc = rich.text.Text("\n".join(textwrap.wrap(desc.strip(), self.wrap_width)), style="color.description.long")
            elif len(task["description"]) <= self.wrap_width - 8:
                d = task["description"].strip()
                title = rich.text.Text(sid, style="color.id") + rich.text.Text(":", style="default") + rich.text.Text(d, style="color.description.short")
                desc = None
            else:
                desc = task["description"]
                desc = rich.text.Text("\n".join(textwrap.wrap(desc.strip(), self.wrap_width)), style="color.description")
                title = rich.text.Text(sid, style="color.id")

            segments = []
            for key in self.show_only:
                if key in task.keys() and key not in ["id", "description"]:
                    val = task[key]
                    segment = f"{key}: "
                    if type(val) == str:
                        segments.append(rich.text.Text(segment+val, style=f"color.{key}"))
                    elif type(val) == list:
                        # FIXME Columns does not fit.
                        # g = Columns([f"+{t}" for t in val], expand = False)
                        lst = []
                        for t in val:
                           lst.append( \
                               rich.text.Text(self.tag_icons[0], style="color.tags.ends") + \
                               rich.text.Text(t, style=f"color.{key}") + \
                               rich.text.Text(self.tag_icons[1], style="color.tags.ends") \
                           )
                        g = rich.console.Group(*lst, fit = True)
                        # g = rich.console.Group(*[rich.text.Text(f"{self.tag_icons[0]}{t}{self.tag_icons[1]}", style=f"color.{key}") for t in val], fit = True)
                        segments.append(g)
                    else:
                        segments.append(rich.text.Text(segment+str(val), style=f"color.{key}"))

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
                    title_align="left", expand = False, padding = (0,1), border_style = "color.touched", box = rich.box.DOUBLE_EDGE)
            else:
                panel = rich.panel.Panel(body, title = title,
                    title_align="left", expand = False, padding = (0,1))

            return panel

    class Sheet(Card):
        def __init__(self, show_only, order = None, touched = [], wrap_width = 25, tag_icons = "🏷  ", title_ends=["\n",""]):
            super().__init__(show_only, order, touched = touched, wrap_width = wrap_width, tag_icons = tag_icons)
            self.title_ends = title_ends

        def __call__(self, task):
            title, body = self._make(task)

            t = rich.text.Text(self.title_ends[0], style="color.description.short.ends") + \
                title + \
                rich.text.Text(self.title_ends[1], style="color.description.short.ends")

            sid = str(task["id"])
            if sid in self.touched:
                b = rich.panel.Panel(body, box = rich.box.SIMPLE_HEAD, style="color.touched")
            else:
                b = rich.panel.Panel(body, box = rich.box.SIMPLE_HEAD, style="color.description")

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
    class sort:
        class Noop(StackSorter):
            def __init__(self):
                super().__init__(None)

            def __call__(self, tasks):
                return tasks

        class Field(StackSorter):
            def __init__(self, field, reverse = False):
                super().__init__(field, reverse)

            def __call__(self, tasks):
                def field_or_not(task):
                    if self.field in task:
                        return task[self.field]
                    else:
                        return "XXX" # No field comes last.
                return sorted(tasks, key = field_or_not, reverse = self.reverse)

        class Priority(StackSorter):
            def __init__(self, reverse = False):
                super().__init__("priority", reverse)

            def __call__(self, tasks):
                def p_value(task):
                    p_values = {"H": 0, "M": 1, "L": 2, "": 3}
                    if self.field in task:
                        return p_values[task[self.field]]
                    else:
                        return p_values[""]
                return sorted(tasks, key = p_value, reverse = self.reverse)

    class RawTable(Stacker):
        def __init__(self, tasker, sorter = None, tag_icons = ["+",""]):
            super().__init__(tasker, sorter = sorter)
            self.tag_icons = tag_icons

        def __call__(self, tasks):
            keys = self.tasker.show_only

            table = rich.table.Table(box = None, show_header = False, show_lines = True, expand = True, row_styles=["color.row.odd", "color.row.even"])
            table.add_column("H")
            for k in keys:
                table.add_column(k)

            for task in self.sorter(tasks):
                taskers = self.tasker(task)
                if str(task["id"]) in self.tasker.touched:
                    row = [rich.text.Text("▶", style = "color.touched")]
                else:
                    row = [""]

                for k in keys:
                    if k in task:
                        val = taskers[k]
                        ##### String keys #####
                        if type(val) == str:
                            # Description is a special case.
                            if k == "description" and ":" in val:
                                short, desc = val.split(":")
                                # FIXME groups add a newline or hide what follows, no option to avoid it.
                                # row.append( rich.console.Group(
                                #     rich.text.Text(short+":", style="color.description.short", end="\n"),
                                #     rich.text.Text(desc, style="color.description", end="\n")
                                # ))
                                # FIXME style leaks on all texts:
                                # (Note that "default" is a special color for Rich.)
                                row.append( rich.text.Text(short, style="color.description.short", end="") + \
                                            rich.text.Text(":", style="default", end="") + \
                                            rich.text.Text(desc, style="color.description.long", end="") )

                            # Strings, but not description.
                            else:
                                row.append( rich.text.Text(val, style=f"color.{k}") )
                        ##### List keys. #####
                        elif type(val) == list:
                            # Tags are a special case.
                            if k == "tags":
                                tags = rich.text.Text("")
                                for t in val:
                                    # FIXME use Columns if/when it does not expand.
                                    tags += \
                                        rich.text.Text(self.tag_icons[0], style="color.tags.ends") + \
                                        rich.text.Text(t, style=f"color.{k}") + \
                                        rich.text.Text(self.tag_icons[1], style="color.tags.ends") + \
                                        " "
                                row.append( tags )
                            # List, but not tags.
                            else:
                                row.append( rich.text.Text(" ".join(val), style=f"color.{k}") )
                        ##### Other type of keys. #####
                        else:
                            row.append( rich.text.Text(str(val), style=f"color.{k}") )
                    else:
                        row.append("")
                table.add_row(*[t for t in row])
            return table


    class Vertical(Stacker):
        def __init__(self, tasker, sorter = None):
            super().__init__(tasker, sorter = sorter)

        def __call__(self, tasks):
            stack = rich.table.Table(box = None, show_header = False, show_lines = False, expand = True)
            stack.add_column("Tasks")
            for task in self.sorter(tasks):
               stack.add_row( self.tasker(task) )
            return stack

    class Flat(Stacker):
        def __init__(self, tasker, sorter = None):
            super().__init__(tasker, sorter = sorter)

        def __call__(self, tasks):
            stack = []
            for task in self.sorter(tasks):
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
            for key in self.order(groups):
                if key in groups:
                    sections.append( rich.panel.Panel(self.stacker(groups[key]), title = rich.text.Text(str(key).upper(), style=f"color.{key}"), title_align = "left", expand = True))
            return rich.console.Group(*sections)

    class Horizontal(Sectioner):
        def __init__(self, stacker, order, group):
            super().__init__(stacker, order, group)

        def __call__(self, tasks):
            sections = []
            groups = self.group(tasks)
            table = rich.table.Table(box = None, show_header = False, show_lines = False)
            keys = []
            for key in self.order(groups):
                if key in groups:
                    table.add_column(key)
                    keys.append(key)

            row = []
            for k in keys:
                row.append( rich.panel.Panel(self.stacker(groups[k]), title = rich.text.Text(k.upper(), style=f"color.{k}"), title_align = "left", expand = True, border_style="color.title"))

            table.add_row(*row)
            return table

class SectionSorter:
    def __call__(self):
        raise NotImplementedError

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
    class sort:
        class OnValues(SectionSorter):
            def __init__(self, values):
                if values:
                    self.values = values
                else:
                    print("WARNING: no values.")
                    self.values = []

            def __call__(self):
                return self.values

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


def call_taskwarrior(args:list[str] = ["export"], taskfile = ".task") -> str:
    # Local file.
    env = os.environ.copy()
    env["TASKDATA"] = taskfile

    cmd = ["task"] + args
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
        return out.decode("utf-8")


def get_data(taskfile, filter = None):
    if not filter:
        filter = []
    out = call_taskwarrior(filter+["export"], taskfile)
    try:
        jdata = json.loads(out)
    except json.decoder.JSONDecodeError as exc:
        print("ERROR:", exc.returncode, exc.output)
    else:
        return jdata


def parse_touched(out):
    return re.findall("(?:Modifying|Created|Starting|Stopping)+ task ([0-9]+)", out)


def get_swatches(name = None):
    swatches = {

        "none": {
            "color.touched": "",
            "color.id": "",
            "color.title": "",
            "color.description": "",
            "color.description.short": "",
            "color.description.short.ends": "",
            "color.description.long": "",
            "color.entry": "",
            "color.end": "",
            "color.modified": "",
            "color.started": "",
            "color.status": "",
            "color.uuid": "",
            "color.tags": "",
            "color.tags.ends": "",
            "color.urgency": "",
            "color.row.odd": "",
            "color.row.even" : "",
            "color.priority": "",
        },

        "nojhan": {
            "color.touched": "#4E9A06",
            "color.id": "color(214)",
            "color.title": "",
            "color.description": "color(231)",
            "color.description.short": "color(231)",
            "color.description.short.ends": "",
            "color.description.long": "default",
            "color.entry": "",
            "color.end": "",
            "color.modified": "color(240)",
            "color.started": "",
            "color.status": "bold italic white",
            "color.uuid": "",
            "color.tags": "color(33)",
            "color.tags.ends": "color(26)",
            "color.urgency": "color(219)",
            "color.row.odd": "on #262121",
            "color.row.even" : "on #2d2929",
            "color.priority": "color(105)",
        },

        "chalky": {
            "color.touched": "color(0) on color(15)",
            "color.id": "bold color(160) on white",
            "color.title": "",
            "color.description": "black on white",
            "color.description.short": "bold black on white",
            "color.description.short.ends": "white",
            "color.description.long": "black on white",
            "color.entry": "",
            "color.end": "",
            "color.modified": "color(240)",
            "color.started": "",
            "color.status": "bold italic white",
            "color.uuid": "",
            "color.tags": "color(166) on white",
            "color.tags.ends": "white",
            "color.urgency": "color(219)",
            "color.row.odd": "",
            "color.row.even" : "",
            "color.priority": "",
        },

        "carbon": {
            "color.touched": "color(15) on color(0)",
            "color.id": "bold color(196) on color(236)",
            "color.title": "",
            "color.description": "white on color(236)",
            "color.description.short": "bold white on color(236)",
            "color.description.short.ends": "color(236)",
            "color.description.long": "white on color(236)",
            "color.entry": "",
            "color.end": "",
            "color.modified": "",
            "color.started": "",
            "color.status": "bold italic white",
            "color.uuid": "",
            "color.tags": "bold black on color(88)",
            "color.tags.ends": "color(88)",
            "color.urgency": "color(219)",
            "color.row.odd": "",
            "color.row.even" : "",
            "color.priority": "",
        },

    }
    if name:
        return swatches[name]
    else:
        return swatches


def get_icons(name=None):

    icons = {

        "none" : {
            "tag": ["", ""],
            "short": ["", ""],
        },

        "ascii" : {
            "tag": ["+", ""],
            "short": ["", ""],
        },

        "emojis" : {
            "tag": ["🏷️ ", ""],
            "short": ["\n", " "],
        },

        "power" : {
            "tag": ["", ""],
            "short": ["\n", " "],
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
        raise KeyError("cannot get layouts with `name` only")


def tw_to_rich(color):
    # color123 -> color(123)
    color = re.sub(r"color([0-9]{0,3})", r"color(\1)", color)
    # rgb123 -> #123 and rgb123abc -> #123abc
    color = re.sub(r"rgb(([\da-f]{3}){1,2})", r"#\1", color)
    # rgb123 -> rgb112233
    color = re.sub(r"#([\da-f])([\da-f])([\da-f])", r"#\1\1\2\2\3\3", color)
    return color

# We cannot use tomllib because strings are not quoted.
# We cannot use configparser because there is no section and because of the "include" command.
# FIXME handle possible values when possible.
def parse_config(filename, current):
    config = current
    with open(filename, "r") as fd:
        for i,line in enumerate(fd.readlines()):
            if line.strip() and line.strip()[0] != "#": # Starting comment.
                if "=" in line:
                    key,value = line.split("=")
                    if "#" in value: # Ending comments.
                        value = value.split("#")[0]
                    if "color" in key: # Colors conversion.
                        value = tw_to_rich(value.strip())
                        if ".uda." in key:
                            key = re.sub(r"color\.uda\.", r"color.", key)
                    config[key.strip()] = value.strip()
                elif "include" in line:
                    _,path = line.split()
                    config["includes"].append(path.strip())
                else:
                    print(f"Cannot parse line {i} of config file `{filename}`, I'll ignore it.")
    return config


def as_bool(s):
    if s.lower() in ["true", "yes", "y", "1"]:
        return True
    elif s.lower() in ["false", "no", "nope", "n", "0"]:
        return False
    else:
        raise ValueError(f"Cannot interpret `{s}` as a boolean.")


def upsearch(filename, at = pathlib.Path.cwd()):
    current = at
    root = pathlib.Path(current.root)

    while current != root:
        found = current / filename
        if found.exists():
            return found
        current = current.parent

    return None


def find_config(fname, current):
    config = current

    # First, system.
    p = pathlib.Path("/etc/taskwarrior") / pathlib.Path(fname)
    if p.exists():
        config = parse_config(p, config)

    # Second, user.
    p = pathlib.Path(os.path.expanduser("~")) / pathlib.Path(fname)
    if p.exists():
        config = parse_config(p, config)

    # Third, upper dirs.
    # LIFO queue allows to fill from current dir,
    # then read from upper dir.
    updirs = queue.LifoQueue()
    here = pathlib.Path.cwd()
    f = upsearch(fname, here)
    while f:
        updirs.put(f)
        f = upsearch(fname, f.parent.parent)

    while not updirs.empty():
        f = updirs.get()
        config = parse_config(f, config)

    return config


def find_tasks(fname, current, config):
    tfile = upsearch(fname, current)
    if tfile:
        return tfile
    elif "data.location" in config:
        return config["data.location"]
    else:
        return None


def parse_filter(cmd):
    tw_commands = [
        "active", "all", "annotate", "append", "blocked", "blocking", "burndown", "burndown", "burndown", "completed",
        "count", "delete", "denotate", "done", "duplicate", "edit", "export", "ghistory", "ghistory", "ghistory", "ghistory",
        "history", "history", "history", "history", "ids", "information", "list", "long", "ls", "minimal",
        "modify", "newest", "next", "oldest", "overdue", "prepend", "projects", "purge", "ready", "recurring", "start",
        "stats", "stop", "summary", "tags", "timesheet", "unblocked", "uuids", "waiting",
    ]
    for i,w in enumerate(cmd):
        if w in tw_commands:
            filter = cmd[:i]
            return filter
    return None

if __name__ == "__main__":

    default_conf = {
        # taskwarrior
        "report.list.columns":"id,priority,description,tags",

        # taskwarrior-deluxe
        "layout.task": "Raw",
        "layout.stack": "RawTable",
        "layout.stack.sort": "urgency",
        "layout.stack.sort.reverse": "false", # urgency and priority are numeric.
        "layout.subsections": "",
        "layout.subsections.group": "",
        "layout.subsections.group.show": "",
        "layout.sections": "Horizontal",
        "layout.sections.group": "status",
        "layout.sections.group.show": "",
        "design.swatch": "none",
        "design.icons": "none",
        "widget.card.wrap": "25",
        "list.filtered": "false",
    }

    # First, taskwarrior"s config...
    config = find_config(".taskrc", default_conf)
    # ... overwritten by TWD config.
    config = find_config(".twdrc", config)

    # for k in config:
    #     print(k,"=",config[k])

    taskfile = find_tasks(".task", pathlib.Path.cwd(), config)
    if not taskfile:
        error("NO_DATA_FILE", "Cannot find a data file here, in a parent directory, or configured.")

    cmd = sys.argv[1:]

    if len(cmd) == 1 and cmd[0] == "init":
        try:
            os.mkdir(".task")
        except Exception as err:
            error("CANNOT_INIT", f"Cannot init task database here: {err}")
        else:
            print("Empty taskwarrior database initialized in", pathlib.Path.cwd())
            sys.exit(0)

    # First pass arguments to taskwarrior and let it do its magic.
    out = call_taskwarrior(cmd, taskfile)
    if "Description" not in out:
        print(out.strip())
    touched = parse_touched(out)

    # Then call again to get the resulting data.
    if as_bool(config["list.filtered"]):
        filter = parse_filter(cmd)
        jdata = get_data(taskfile, filter)
    else:
        jdata = get_data(taskfile, filter = None)
    # print(json.dumps(jdata, indent=4))

    list_separator = ","
    showed = config["report.list.columns"].split(list_separator)
    if not showed:
        show_only = None
    else:
        show_only = showed

    swatch = rich.theme.Theme(get_swatches(config["design.swatch"]))
    layouts = get_layouts()

    ##### Tasks #####
    if config["layout.task"] == "Card":
        tasker = layouts["task"]["Card"](show_only, touched = touched, wrap_width = int(config["widget.card.wrap"]), tag_icons = get_icons(config["design.icons"])["tag"])
    elif config["layout.task"] == "Sheet":
        icons = get_icons(config["design.icons"])
        tasker = layouts["task"]["Sheet"](show_only, touched = touched, wrap_width = int(config["widget.card.wrap"]), tag_icons = icons["tag"], title_ends = icons["short"])
    else:
        tasker = layouts["task"][config["layout.task"]](show_only, touched = touched)

    ##### Stack #####
    if config["layout.stack.sort"]:
        if config["layout.stack.sort"] == "priority":
            sorter = stack.sort.Priority(as_bool(config["layout.stack.sort.reverse"]))
        elif config["layout.stack.sort"] == "urgency":
            sorter = stack.sort.Priority(as_bool(config["layout.stack.sort.reverse"]))
        else:
            sorter = stack.sort.Field(config["layout.stack.sort"], reverse = as_bool(config["layout.stack.sort.reverse"]))
    else:
        sorter = None

    if config["layout.stack"] == "RawTable":
        stacker = layouts["stack"]["RawTable"](tasker, sorter = sorter, tag_icons = get_icons(config["design.icons"])["tag"])
    else:
        stacker = layouts["stack"][config["layout.stack"]](tasker, sorter = sorter)

    ##### Sections #####
    if config["layout.sections.group"]:
        values = config["layout.sections.group.show"].split(list_separator)
        if values == [""]:
            values = []
        if config["layout.sections.group"].lower() == "status":
            group_by = group.Status()
            if not values:
                values = ["pending","started","completed"]
            g_sort_on = group.sort.OnValues( values )
        elif config["layout.sections.group"].lower() == "priority":
            group_by = group.Field("priority")
            if not values:
                values = ["H","M","L",""]
            g_sort_on = group.sort.OnValues( values )
        else:
            group_by = group.Field(config["layout.sections.group"])
            g_sort_on = None
    else:
        group_by = group.Status()
        g_sort_on = group.sort.OnValues(["pending","started","completed"])

    ##### Subsections #####
    if config["layout.subsections.group"]:
        values = config["layout.subsections.group.show"].split(list_separator)
        if values == [""]:
            values = []
        if config["layout.subsections.group"].lower() == "status":
            subgroup_by = group.Status()
            if not values:
                values = ["pending","started","completed"]
            g_sort_on = group.sort.OnValues( values )
        if config["layout.subsections.group"].lower() == "priority":
            subgroup_by = group.Field("priority")
            if not values:
                values = ["H","M","L",""]
            g_subsort_on = group.sort.OnValues( values )
        else:
            subgroup_by = group.Field(config["layout.subsections.group"])
            g_subsort_on = None
    else:
        subgroup_by = None
        g_subsort_on = None

    if config["layout.subsections"] and config["layout.subsections.group"]:
        subsectioner = layouts["sections"][config["layout.subsections"]](stacker, g_subsort_on, subgroup_by)
        sectioner = layouts["sections"][config["layout.sections"]](subsectioner, g_sort_on, group_by)
    else:
        sectioner = layouts["sections"][config["layout.sections"]](stacker, g_sort_on, group_by)

    console = Console(theme = swatch)
    # console.rule("taskwarrior-deluxe")
    console.print(sectioner(jdata))

