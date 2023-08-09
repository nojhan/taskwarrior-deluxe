import os
import sys
import json
import argparse
import subprocess

import rich
# For some reason this is not imported by the command above.
from rich.console import Console
from rich.columns import Columns

def card(task, show_only = None):
    """Widget being a single task."""

    if not show_only:
        # Show all existing fields.
        show_only = task.keys()

    sid = str(task["id"])
    if ':' in task["description"]:
        short, desc = task["description"].split(":")
        title = ":".join([sid,short.strip()])
    else:
        desc = task["description"]
        title = sid

    segments = [desc.strip()]
    for key in show_only:
        if key in task.keys() and key not in ["id", "description"]:
            segments.append(str(task[key]))

    cols = Columns(segments)

    panel = rich.panel.Panel(cols, title = title,
        title_align="left", expand = True, padding = (0,0))

    return panel


def stack(tasks, show_only = None):
    """Widget being a stack of tasks widgets."""
    stack = rich.table.Table()
    stack.add_column("Tasks")
    for task in tasks:
       stack.add_row( card(task, show_only) )
    return stack

def group_by(tasks, field):
    """Group tasks by field values."""
    groups = {}
    for task in tasks:
        if field in task:
            if task[field] in groups:
                groups[ task[field] ].append(task)
            else:
                groups[ task[field] ] = [task]
    return groups

def sections(tasks, field, values, show_only = None):
    """Widget being a panel of stack widgets."""
    sections = []
    groups = group_by(tasks, field)
    for val in values:
        if val in groups:
            sections.append( rich.panel.Panel(stack(groups[val], show_only), title = val) )
    return rich.console.Group(*sections)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="XXX",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    main = parser.add_argument_group('Main')
    main.add_argument("-s", "--show", metavar="columns", type=str, default="id,priority,status,description,tags", nargs=1,
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

    show_only = asked.show.split(asked.list_separator)

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
        # print(json.dumps(jdata, indent=4))

        console = Console()
        console.rule("taskwarrior-fancy")
        console.print(sections(jdata, "status", ["pending","completed"], show_only))

