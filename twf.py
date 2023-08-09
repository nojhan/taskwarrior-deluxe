import os
import sys
import json
import argparse
import subprocess

import rich
# For some reason this is not imported by the command above.
from rich.console import Console
from rich.columns import Columns

# class make:
#     def carder(card, **kwargs):
#         def f(task):
#             return card(task, **kwargs)
#         return f

#     def stacker(stack, **kwargs):
#         def f(tasks):
#             return stack(tasks, **kwargs)
#         return f

#     def sectioner(section, **kwargs):
#         def f(tasks, field, values):
#             return section(tasks, field, values, **kwargs)
#         return f

class Widget:
    def __init__(self, order, group = None):
        self.order = order
        self.group = group

class Tasker(Widget):
    def __init__(self, show_only, order, group = None):
        super().__init__(order, group)
        self.show_only = show_only

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


class Card(Tasker):
    def __init__(self, show_only, order = None):
        super().__init__(show_only, order, group = None)

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

        segments = []
        for key in self.show_only:
            if key in task.keys() and key not in ["id", "description"]:
                val = task[key]
                segment = f"{key}: "
                if type(val) == str:
                    segments.append(segment+t)
                elif type(val) == list:
                    g = Columns([f"+{t}" for t in val])
                    segments.append(g)
                else:
                    segments.append(segment+str(val))

        cols = Columns(segments)
        grp = rich.console.Group(desc.strip(), cols)
        panel = rich.panel.Panel(grp, title = title,
            title_align="left", expand = False, padding = (0,1))

        return panel

class VerticalStack(Stacker):
    def __init__(self, tasker):
        super().__init__(tasker, order = None, group = None)

    def __call__(self, tasks):
        stack = rich.table.Table()
        stack.add_column("Tasks")
        for task in tasks:
           stack.add_row( self.tasker(task) )
        return stack

class VerticalSections(Sectioner):
    def __init__(self, stacker, order, group):
        super().__init__(stacker, order, group)

    def __call__(self, tasks):
        sections = []
        groups = self.group(tasks)
        for val in self.order():
            if val in groups:
                sections.append( rich.panel.Panel(self.stacker(groups[val]), title = val) )
        return rich.console.Group(*sections)

class SectionSorter:
    def __call__(self):
        raise NotImplementedError

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

class TasksSorter:
    def make(self, tasks, field, reverse = False):
        return sorted(tasks, key = lambda t: t[field], reverse = reverse)


# class layout:
#     def __init__(self, carder, stacker, sectioner)
#         self.carder = carder
#         self.stacker = stacker
#         self.sectioner = sectioner

#     def __call__(self, sec_group, sec_sort, sub_group, sub_sort):
#         self.section(self.stack(), 

# def group_by(tasks, field):
#     """Group tasks by field values."""
#     groups = {}
#     for task in tasks:
#         if field in task:
#             if task[field] in groups:
#                 groups[ task[field] ].append(task)
#             else:
#                 groups[ task[field] ] = [task]
#     return groups

# def sort_by(tasks, field = "urgency", reverse = False):
#     return sorted(tasks, key = lambda t: t[field], reverse = reverse)

##### Widgets #####

# class packed:
#     def card(task, in_widget = None, show_only = None):
#         """Widget being a single task."""

#         if not show_only:
#             # Show all existing fields.
#             show_only = task.keys()

#         sid = str(task["id"])
#         if ':' in task["description"]:
#             short, desc = task["description"].split(":")
#             title = ":".join([sid,short.strip()])
#         else:
#             desc = task["description"]
#             title = sid

#         segments = []
#         for key in show_only:
#             if key in task.keys() and key not in ["id", "description"]:
#                 val = task[key]
#                 segment = f"{key}: "
#                 if type(val) == str:
#                     segments.append(segment+t)
#                 elif type(val) == list:
#                     g = Columns([f"+{t}" for t in val])
#                     segments.append(g)
#                 else:
#                     segments.append(segment+str(val))

#         cols = Columns(segments)
#         grp = rich.console.Group(desc.strip(), cols)
#         panel = rich.panel.Panel(grp, title = title,
#             title_align="left", expand = False, padding = (0,1))

#         return panel


#     def stack(tasks, in_widget = None, show_only = None):
#         """Widget being a stack of tasks widgets."""
#         stack = rich.table.Table()
#         stack.add_column("Tasks")
#         for task in tasks:
#            stack.add_row( card(task, in_widget, show_only) )
#         return stack


#     def sections(tasks, field, values, in_widget = None, show_only = None):
#         """Widget being a panel of stack widgets."""
#         sections = []
#         groups = group_by(tasks, field)
#         for val in values:
#             if val in groups:
#                 sections.append( rich.panel.Panel(stack(groups[val], in_widget, show_only), title = val) )
#         return rich.console.Group(*sections)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="XXX",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    main = parser.add_argument_group('Main')
    main.add_argument("-s", "--show", metavar="columns", type=str, default="id,urgency,description,tags", nargs=1,
            help="Ordered list of columns to show.")

    config = parser.add_argument_group('Config')
    config.add_argument("-d", "--data", metavar="FILE", type=str, default=".task", nargs=1,
            help="The input data file.")
    config.add_argument("--list-separator", metavar="CHARACTER", type=str, default=",", nargs=1,
            help="Separator used for lists that are passed as options arguments.")

    asked = parser.parse_args()

    env = os.environ.copy()
    env["TASKDATA"] = asked.data

    cmd = ['task', 'export']

    showed = asked.show.split(asked.list_separator)
    if not showed:
        show_only = None
    else:
        show_only = showed

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
        jdata = json.loads(out)
        print(json.dumps(jdata, indent=4))

        tasker = Card(show_only)
        stacker = VerticalStack(tasker)
        group_by_status = Grouper("status")
        sort_on_values = OnValues(["pending","completed"])
        sectioner = VerticalSections(stacker, sort_on_values, group_by_status)

        console = Console()
        console.rule("taskwarrior-fancy")
        console.print(sectioner(jdata))

