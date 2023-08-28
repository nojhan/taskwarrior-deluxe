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
    def __init__(self, config, list_separator = ","):
        self.config = config
        self.list_separator = list_separator

    def swatch_of(self, key, val, prefix = "color."):
        if key:
            key = prefix+key
            value = re.sub(r"\s", "_", val)
            keyval = f"{key}.{value}"
            if key in self.config or keyval in self.config:
                # key and keyval in config.
                if   key in     self.config and keyval     in self.config:
                    # "on" in key and not in keyval.
                    if   "on"     in self.config[key] and "on" not in self.config[keyval]:
                        return f"{self.config[keyval]} {self.config[key]}"
                    # "on" not in key and in keyval.
                    elif "on" not in self.config[key] and "on"     in self.config[keyval]:
                        return f"{self.config[key]} {self.config[keyval]}"
                    else: # "on" not in key and not in keyval or "on" in key and in keyval
                        # Defaults to keyval having precedence if nothing is specified.
                        swatch = self.config[keyval]
                        korder = self.config["rule.precedence.color"].split(self.list_separator)
                        for k in korder: # FIXME reverse korder?
                            if k in keyval:
                                swatch = self.config[keyval]
                                break
                            if k in key:
                                swatch = self.config[key]
                                break
                        return swatch

                elif key in     self.config and keyval not in self.config:
                    return self.config[key]
                elif key not in self.config and keyval     in self.config:
                    return self.config[keyval]
            else: # key and keyval not in self.config.
                return ""
        else: # Not key.
            return ""

    def rtext(self, val, swatch, prefix = "color.", end="\n"):
        return rich.text.Text(val, style=self.swatch_of(swatch, val, prefix), end=end)


class Tasker(Widget):
    def __init__(self, config, show_only, order = None, group = None, touched = []):
        super().__init__(config)
        self.show_only = show_only
        self.touched = touched
        self.sorter = order
        self.grouper = group

    def __call__(self, task):
        raise NotImplementedError

class Stacker(Widget):
    def __init__(self, config, tasker, sorter = None):
        super().__init__(config)
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
    def __init__(self, config, stacker, order, group):
        super().__init__(config)
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
        def __init__(self, config, show_only, order = None, touched = [], wrap_width = 25):
            super().__init__(config, show_only, order, group = None, touched = touched)
            self.wrap_width = wrap_width
            self.tag_icons = [ self.config["icon.tag.before"], self.config["icon.tag.after"] ]

        def _make(self, task):
            if not self.show_only:
                # Show all existing fields.
                self.show_only = task.keys()

            sid = str(task["id"])
            if ":" in task["description"]:
                short, desc = task["description"].split(":")
                title = self.rtext(sid, "id") + rich.text.Text(":", style="default") + self.rtext(short.strip(), "description.short")
                desc = rtext("\n".join(textwrap.wrap(desc.strip(), self.wrap_width)), "description.long")
            elif len(task["description"]) <= self.wrap_width - 8:
                d = task["description"].strip()
                title = self.rtext(sid, "id") + rich.text.Text(":", style="default") + self.rtext(d, "description.short")
                desc = None
            else:
                desc = task["description"]
                desc = self.rtext("\n".join(textwrap.wrap(desc.strip(), self.wrap_width)),"description")
                title = self.rtext(sid, "id")

            segments = []
            for key in self.show_only:
                if key in task.keys() and key not in ["id", "description"]:
                    val = task[key]
                    segment = f"{key}: "
                    if type(val) == str:
                        segments.append( self.rtext(segment+val, f"{key}") )
                    elif type(val) == list:
                        # FIXME Columns does not fit.
                        # g = Columns([f"+{t}" for t in val], expand = False)
                        lst = []
                        for t in val:
                           lst.append( \
                               self.rtext(self.tag_icons[0], "tags.ends") + \
                               self.rtext(t, f"{key}") + \
                               self.rtext(self.tag_icons[1], "tags.ends") \
                           )
                        g = rich.console.Group(*lst, fit = True)
                        # g = rich.console.Group(*[rich.text.Text(f"{self.tag_icons[0]}{t}{self.tag_icons[1]}", style=f"color.{key}") for t in val], fit = True)
                        segments.append(g)
                    else:
                        segments.append(self.rtext(segment+str(val), f"{key}"))

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
        def __init__(self, config, show_only, order = None, touched = [], wrap_width = 25):
            super().__init__(config, show_only, order, touched = touched, wrap_width = wrap_width)
            self.title_ends = [ self.config["icon.short.before"], self.config["icon.short.after"] ]

        def __call__(self, task):
            title, body = self._make(task)

            t = self.rtext(self.title_ends[0], "description.short.ends") + \
                title + \
                self.rtext(self.title_ends[1], "description.short.ends")

            sid = str(task["id"])
            if sid in self.touched:
                b = rich.panel.Panel(body, box = rich.box.SIMPLE_HEAD, style="color.touched")
            else:
                b = rich.panel.Panel(body, box = rich.box.SIMPLE_HEAD, style="color.description")

            sheet = rich.console.Group(t,b)
            return sheet


    class Raw(Tasker):
        def __init__(self, config, show_only, order = None, touched = []):
            super().__init__(config, show_only, order, group = None, touched = touched)

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
        def __init__(self, config, tasker, sorter = None):
            super().__init__(config, tasker, sorter = sorter)
            self.tag_icons = [ self.config["icon.tag.before"], self.config["icon.tag.after"] ]

        def __call__(self, tasks):
            keys = self.tasker.show_only

            table = rich.table.Table(box = None, show_header = False, show_lines = True, expand = True, row_styles=["color.row.odd", "color.row.even"])
            table.add_column("H")
            for k in keys:
                table.add_column(k)

            for task in self.sorter(tasks):
                taskers = self.tasker(task)
                if str(task["id"]) in self.tasker.touched:
                    row = [self.rtext("▶", "r.touched")]
                else:
                    row = [""]

                for k in keys:
                    if k in task:
                        val = taskers[k]
                        ##### String keys #####
                        if type(val) == str:
                            # Description is a special case.
                            if k == "description" and ":" in val:
                                # Split description in "short: long".
                                short, desc = val.split(":")
                                # FIXME groups add a newline or hide what follows, no option to avoid it.
                                # row.append( rich.console.Group(
                                #     rich.text.Text(short+":", style="color.description.short", end="\n"),
                                #     rich.text.Text(desc, style="color.description", end="\n")
                                # ))
                                # FIXME style leaks on all texts:
                                # (Note that "default" is a special color for Rich.)
                                row.append( self.rtext(short, "description.short", end="") + \
                                            rich.text.Text(":", style="default", end="") + \
                                            self.rtext(desc, "description.long", end="") )

                            # Strings, but not description.
                            else:
                                row.append( self.rtext(val, f"{k}") )
                        ##### List keys. #####
                        elif type(val) == list:
                            # Tags are a special case.
                            if k == "tags":
                                tags = rich.text.Text("")
                                for t in val:
                                    # FIXME use Columns if/when it does not expand.
                                    tags += \
                                        self.rtext(self.tag_icons[0], "tags.ends") + \
                                        self.rtext(t, f"{k}") + \
                                        self.rtext(self.tag_icons[1], "tags.ends") + \
                                        " "
                                row.append( tags )
                            # List, but not tags.
                            else:
                                row.append( self.rtext(" ".join(val), f"{k}") )
                        ##### Other type of keys. #####
                        else:
                            row.append( self.rtext(str(val), f"{k}") )
                    else:
                        row.append("")
                table.add_row(*[t for t in row])
            return table


    class Vertical(Stacker):
        def __init__(self, config, tasker, sorter = None):
            super().__init__(config, tasker, sorter = sorter)

        def __call__(self, tasks):
            stack = rich.table.Table(box = None, show_header = False, show_lines = False, expand = True)
            stack.add_column("Tasks")
            for task in self.sorter(tasks):
               stack.add_row( self.tasker(task) )
            return stack

    class Flat(Stacker):
        def __init__(self, config, tasker, sorter = None):
            super().__init__(config, tasker, sorter = sorter)

        def __call__(self, tasks):
            stack = []
            for task in self.sorter(tasks):
               stack.append( self.tasker(task) )
            cols = rich.columns.Columns(stack)
            return cols

class sections:
    class Vertical(Sectioner):
        def __init__(self, config, stacker, order, group):
            super().__init__(config, stacker, order, group)

        def __call__(self, tasks):
            sections = []
            groups = self.group(tasks)
            for key in self.order(groups):
                if key in groups:
                    if self.grouper.field:
                        swatch = f"{self.grouper.field}.{key}"
                    else:
                        swatch = f"{key}"
                    val = str(key).upper()
                    sections.append( rich.panel.Panel(self.stacker(groups[key]), title = self.rtext(val, swatch), title_align = "left", expand = True, border_style = self.swatch_of(swatch, val)))
            return rich.console.Group(*sections)

    class Horizontal(Sectioner):
        def __init__(self, config, stacker, order, group):
            super().__init__(config, stacker, order, group)

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
                row.append( rich.panel.Panel(self.stacker(groups[k]), title = self.rtext(k.upper(), f"{k}"), title_align = "left", expand = True, border_style="color.title"))

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


def get_swatch(config):
    swatch = {
        "color.touched" : "",
        "color.id" : "",
        "color.title" : "",
        "color.description" : "",
        "color.description.short" : "",
        "color.description.short.ends" : "",
        "color.description.long" : "",
        "color.entry" : "",
        "color.end" : "",
        "color.modified" : "",
        "color.started" : "",
        "color.status" : "",
        "color.uuid" : "",
        "color.tags" : "",
        "color.tags.ends" : "",
        "color.urgency" : "",
        "color.row.odd" : "",
        "color.row.even" : "",
        "color.priority" : "",
    }
    for k in config:
        if k in swatch:
            swatch[k] = config[k]
    return swatch


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

    # rgb123abc -> #123abc (not TW but allowed in TWD)
    color = re.sub(r"rgb([\da-f]{6})", r"#\1", color)

    # rgb123 -> #336699
    # Mapping from TW's own 256 colors to true 16M color space.
    # TW use a triplet of integers in [0-5] to give a more user-friendly
    # way to pick an ANSI color in the 256-colors space.
    # Rich allows true color, so we can just map each RGB component
    # of TW to its hex equivalent in the classical 16M-colors space.
    for col5 in re.finditer(r"rgb[0-5]{3}", color):
        col256 = "#"
        for c5 in re.finditerl(r"[0-5]", col5):
            i5 = int(c5)
            i256 = round(i5/5*256)
            c256 = hex(i256).replace("0x","")
            col256 += c256
        color.replace(col5, col256)

    return color

# We cannot use tomllib because strings are not quoted.
# We cannot use configparser because there is no section and because of the "include" command.
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
                    # Recursively add/replace with the included config.
                    config.update( parse_config(os.path.expanduser(path.strip()), config) )
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
        "report.list.columns": "id,priority,description,tags",
        "rule.precedence.color": "",

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

    swatch = rich.theme.Theme(get_swatch(config))
    layouts = get_layouts()

    ##### Tasks #####
    if config["layout.task"] == "Card":
        tasker = layouts["task"]["Card"](config, show_only, touched = touched, wrap_width = int(config["widget.card.wrap"]))
    elif config["layout.task"] == "Sheet":
        tasker = layouts["task"]["Sheet"](config, show_only, touched = touched, wrap_width = int(config["widget.card.wrap"]))
    else:
        tasker = layouts["task"][config["layout.task"]](config, show_only, touched = touched)

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
        stacker = layouts["stack"]["RawTable"](config, tasker, sorter = sorter)
    else:
        stacker = layouts["stack"][config["layout.stack"]](config, tasker, sorter = sorter)

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
        subsectioner = layouts["sections"][config["layout.subsections"]](config, stacker, g_subsort_on, subgroup_by)
        sectioner = layouts["sections"][config["layout.sections"]](config, subsectioner, g_sort_on, group_by)
    else:
        sectioner = layouts["sections"][config["layout.sections"]](config, stacker, g_sort_on, group_by)

    console = Console(theme = swatch)
    # console.rule("taskwarrior-deluxe")
    console.print(sectioner(jdata))

