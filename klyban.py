import sys
import csv
import json
import datetime
import textwrap
from configparser import ConfigParser

import numpy as np
import pandas as pd
import click
# import tabulate
import rich.console as rconsole
from rich.table import Table as richTable
from rich.text import Text as richText
from rich.panel import Panel as richPanel
from rich.columns import Columns as richColumns
from rich.theme import Theme as richTheme
from rich.layout import Layout as richLayout
from rich.console import Group as richGroup
from rich import box


error_codes = {
    "INVALID_KEY": 100,
    "ID_NOT_FOUND": 101,
    "UNKNOWN_STATUS": 102,
}


def error(name,msg):
    print("ERROR:",msg)
    sys.exit(error_codes[name])


def load_data(context):
    try:
        # Automagically manages standard input if input=="-", thanks to allow_dash=True.
        with click.open_file(context.obj['input'], mode='r') as fd:
            df = pd.read_csv(fd)
            # FIXME data sanity checks: unique index, aligned status, valid dates

    except FileNotFoundError:
        # Create an empty file.
        df = pd.DataFrame(columns=[
            context.obj['id_key'],
            context.obj['status_key'],
            context.obj['title_key'],
            context.obj['details_key'],
            context.obj['tags_key'],
            context.obj['deadline_key'],
            context.obj['touched_key'],
        ])
        df = df.set_index(context.obj['id_key'])
        save_data(context, df)

    else:
        # set index on ID.
        df = df.astype({context.obj['id_key']:int})
        df = df.set_index(context.obj['id_key'])

        # Remove any values consisting of empty spaces or quotes.
        df = df.replace(r'^[\s"\']*$', np.nan, regex=True)

    finally:
        # Virtual "hints" column.
        df['H'] = ''
        if context.obj['debug']:
            print("Loaded:")
            print(df)
        return df


def save_data(context, df):
    if context.obj['debug']:
        print("Save:")
        print(df)
    # FIXME double check that there are actually data.

    # Remove the virtual "hints" column.
    df = df.drop('H', axis = 1)

    # Bring back ID as a regular column.
    df = df.reset_index()

    # Remove any values consisting of empty spaces or quotes.
    df = df.replace(r'^[\s"\']*$', np.nan, regex=True)

    # Automagically manages standard input if input=="-", thanks to allow_dash=True.
    with click.open_file(context.obj['input'], mode='w') as fd:
        df.to_csv(fd, index=False, quoting=csv.QUOTE_NONNUMERIC)


def configure(context, param, filename):
    """Overwrite defaults for options."""
    cfg = ConfigParser()
    cfg.read(filename)
    context.default_map = {}
    for sect in cfg.sections():
        command_path = sect.split('.')
        if command_path[0] != 'options':
            continue
        defaults = context.default_map
        for cmdname in command_path[1:]:
            defaults = defaults.setdefault(cmdname, {})
        defaults.update(cfg[sect])


def check_id(context, param, value):
    """Callback checking if task exists."""
    if value is None: # For optional TID.
        return value
    assert(type(value) == int)
    df = load_data(context)
    if value not in df.index:
        error("ID_NOT_FOUND", "{} `{}` was not found in data `{}`".format(context.obj['id_key'], value, context.obj['input']))
    return value



# Global group holding global options.
@click.group(invoke_without_command=True)
# Core options.
@click.option(
    '-c', '--config',
    type         = click.Path(dir_okay=False),
    default      = '.klyban.conf',
    callback     = configure,
    is_eager     = True,
    expose_value = False,
    help         = 'Read option defaults from the specified configuration file.',
    show_default = True,
)
@click.option('-i', '--input' , help="CSV data file.", default='.klyban.csv', type=click.Path(writable=True, readable=True, allow_dash=True), show_default=True)
# Display options.
@click.option('-h','--show-headers', is_flag=True, help="Show the headers.")
@click.option('-s', '--show-fields'   , default='ID,TITLE,DETAILS,TAGS', type=str , show_default=True, help="Comma-separated, ordered list of fields that should be shown (use 'all' for everything).")
@click.option('-g', '--highlight', type = int, default = None, help="Highlight a specific task.")
@click.option('--highlight-mark', type = str, default = '▶', help="String used to highlight a specific task.")
@click.option('-l', '--layout', type = click.Choice(['vertical-compact', 'vertical-spaced', 'horizontal-compact', 'horizontal-spaced']), default = 'vertical-compact', help="How to display tasks.") # TODO , 'horizontal-compact', 'horizontal-spaced'
@click.option('-t', '--theme', type = click.Choice(['none', 'user', 'BW', 'BY', 'RW', 'nojhan'], case_sensitive=False), default = 'none', help="How to display tasks.")
# Low-level configuration options.
@click.option('--status-key'  , default='STATUS'  , type=str, show_default=True, help="Header key defining the status of tasks.")
@click.option('--show-status' , default='TODO,DOING,HOLD,DONE', type=str, show_default=True, help="Comma-separated, ordered list of possible values for the status of tasks.")
@click.option('--id-key'      , default='ID'      , type=str, show_default=True, help="Header key defining the unique ID of tasks.")
@click.option('--title-key'   , default='TITLE'   , type=str, show_default=True, help="Header key defining the title (short description) of tasks.")
@click.option('--details-key' , default='DETAILS' , type=str, show_default=True, help="Header key defining the details (long description) of tasks.")
@click.option('--tags-key'    , default='TAGS'    , type=str, show_default=True, help="Header key defining the tags associated to tasks.")
@click.option('--deadline-key', default='DEADLINE', type=str, show_default=True, help="Header key defining the deadlines tasks.")
@click.option('--touched-key', default='TOUCHED', type=str, show_default=True, help="Header key defining the deadlines tasks.")
@click.option('--debug', is_flag=True, help="Print debugging information.")
@click.pass_context
def cli(context, **kwargs):

    # print(json.dumps(kwargs, sort_keys=True, indent=4))

    # Ensure that context.obj exists and is a dict.
    context.ensure_object(dict)

    def store(context_key, kw_key = None):
        if not kw_key:
            kw_key = context_key
        context.obj[context_key] = kwargs[kw_key]

    store('input')

    store('debug')

    store('id_key')
    store('status_key')
    store('title_key')
    store('details_key')
    store('tags_key')
    store('deadline_key')
    store('touched_key')

    store('show_headers')
    store('highlight')
    store('highlight_mark')

    store('layout')
    context.obj['layouts'] = {
        'vertical-compact': VerticalCompact,
        'vertical-spaceds': VerticalSpaced,
        'horizontal-compact': HorizontalCompact,
        'horizontal-spaced': HorizontalSpaced,
    }

    context.obj['themes'] = {
        'none': richTheme({
            'H': '',
            'matching': 'italic',
            context.obj['id_key']: '',
            context.obj['status_key']: '',
            context.obj['title_key']: '',
            context.obj['details_key']: '',
            context.obj['tags_key']: '',
            context.obj['deadline_key']: '',
            context.obj['touched_key']: '',
            'row_odd': '',
            'row_even': '',
        }),
        'BW': richTheme({
            'H': 'white',
            'matching': 'italic',
            context.obj['id_key']: 'bold black',
            context.obj['status_key']: 'bold',
            context.obj['title_key']: 'bold white',
            context.obj['details_key']: 'white',
            context.obj['tags_key']: 'italic white',
            context.obj['deadline_key']: 'white',
            context.obj['touched_key']: 'black',
            'row_odd': 'on color(237)',
            'row_even': 'on color(239)',
        }),
        'BY': richTheme({
            'H': 'color(220)',
            'matching': 'italic',
            context.obj['id_key']: 'bold color(39)',
            context.obj['status_key']: 'bold color(227)',
            context.obj['title_key']: 'color(220)',
            context.obj['details_key']: 'color(33)',
            context.obj['tags_key']: 'color(27)',
            context.obj['deadline_key']: 'white',
            context.obj['touched_key']: 'black',
            'row_odd' : 'bold',
            'row_even': '',
        }),
        'RW': richTheme({
            'H': 'red',
            'matching': 'italic',
            context.obj['id_key']: 'bold red',
            context.obj['status_key']: 'bold white',
            context.obj['title_key']: 'bold white',
            context.obj['details_key']: 'white',
            context.obj['tags_key']: 'red',
            context.obj['deadline_key']: 'white',
            context.obj['touched_key']: 'color(240)',
            'row_odd' : '',
            'row_even': '',
        }),
        'nojhan': richTheme({
            'H': '#4E9A06',
            'matching': 'italic on #464141',
            context.obj['id_key']: 'bold color(214)',
            context.obj['status_key']: 'bold italic white',
            context.obj['title_key']: 'bold white',
            context.obj['details_key']: 'white',
            context.obj['tags_key']: 'color(27)',
            context.obj['deadline_key']: 'white',
            context.obj['touched_key']: 'color(240)',
            'row_odd': 'on #262121',
            'row_even' : 'on #2d2929',
        }),
    }
    context.obj['theme'] = context.obj['themes'][kwargs['theme']]

    context.obj['show_status'] = kwargs['show_status'].split(',')
    if kwargs['show_fields'].lower() == "all":
        context.obj['show_fields'] = [
            context.obj['id_key'],
            context.obj['status_key'],
            context.obj['title_key'],
            context.obj['details_key'],
            context.obj['tags_key'],
            context.obj['deadline_key'],
            context.obj['touched_key'],
        ]
    else:
        context.obj['show_fields'] = kwargs['show_fields'].split(',')

    # Always show the 'Hint' column.
    context.obj['show_fields'] = ['H'] + context.obj['show_fields']

    # At the end, always load data, whatever the command will be.
    context.obj['data'] = load_data(context)

    # Finally, if no command: defaults to `show`.
    if not context.invoked_subcommand:
        context.invoke(show)


class Layout:
    def __init__(self, context):
        self.context = context

class Vertical(Layout):
    def __init__(self, context, table_box, show_lines, panel_box):
        super().__init__(context)
        self.show_lines = show_lines
        self.table_box = table_box
        self.panel_box = panel_box

    def section_prefix(self, sections):
        pass

    def section_suffix(self, sections):
        pass

    def section(self, section, table, sections):
        # Title styling does not work because of bug #2466 in Rich, fixed after 32d6e99.
        # See https://github.com/Textualize/rich/issues/2466
        title = richText(section, style = self.context.obj['status_key'], overflow = 'ellipsis')
        panel = richPanel(table, title = title, title_align="left", border_style = self.context.obj['status_key'], box = self.panel_box, expand = False, padding = (0,0))
        sections.append(panel)

    def __rich__(self):
        df = self.context.obj['data']

        # Show the kanban tables.
        if df.empty:
            return "No task."

        sections = []

        if self.context.obj['highlight'] is not None:
            df.loc[self.context.obj['highlight'], 'H'] = self.contex.obj['highlight_mark']

        # Group by status.
        tables = df.groupby(self.context.obj['status_key'])
        # Loop over the asked ordered status groups.
        for section in self.context.obj['show_status']: # Ordered.
            if section in tables.groups:
                df = tables.get_group(section)

                # Bring back TID as a regular column.
                df = df.reset_index().fillna("")

                # Always consider the hint column.
                if 'H' not in self.context.obj['show_fields']:
                    self.context.obj['show_fields'] = ['H'] + self.context.obj['show_fields']

                try:
                    # Print asked columns.
                    t = df[self.context.obj['show_fields']]
                except KeyError as e:
                    msg = ""
                    for section in self.context.obj['show_fields']:
                        if section not in df.columns:
                            msg += "cannot show field `{}`, not found in `{}` ".format(section, self.context.obj['input'])
                    error("INVALID_KEY", msg)
                else:
                    if len(df.index) <= 1:
                        show_lines = False
                        table_box = None
                    else:
                        show_lines = self.show_lines
                        table_box = self.table_box

                    table = richTable(show_header = self.context.obj['show_headers'], box = table_box, row_styles = ['row_odd', 'row_even'], show_lines = show_lines, expand = True)

                    for h in self.context.obj['show_fields']:
                        table.add_column(h, style = h)

                    for i,row in t.iterrows():
                        items = (str(row[k]) for k in self.context.obj['show_fields'])
                        if row['H']:
                            row_style = 'matching'
                        else:
                            row_style = None
                        table.add_row(*items, style = row_style)

                    self.section_prefix(sections)
                    self.section(section, table, sections)
                    self.section_suffix(sections)

        return rconsole.Group(*sections)

class VerticalCompact(Vertical):
    def __init__(self, context):
        super().__init__(context, table_box = None, show_lines = False, panel_box = box.ROUNDED)
    # FIXME find a way to use console.rule instead of richPanel in self.section

class VerticalSpaced(Vertical):
    def __init__(self, context):
        super().__init__(context, table_box = box.HORIZONTALS, show_lines = True, panel_box = box.HEAVY_EDGE)

    def section_prefix(self, sections):
        sections.append("\n")

class Horizontal(Layout):
    def __init__(self, context, table_box, show_lines, panel_box):
        super().__init__(context)
        self.show_lines = show_lines
        self.table_box = table_box
        self.panel_box = panel_box

class HorizontalCompact(Horizontal):
    def __init__(self, context):
        super().__init__(context, table_box = None, show_lines = False, panel_box = box.ROUNDED)

    def __rich__(self):
        df = self.context.obj['data']

        # Show the kanban tables.
        if df.empty:
            return "No task."

        sections = []

        if self.context.obj['highlight'] is not None:
            df.loc[self.context.obj['highlight'], 'H'] = self.contex.obj['highlight_mark']

        # Group by status.
        tables = df.groupby(self.context.obj['status_key'])
        # Loop over the asked ordered status groups.
        for section in self.context.obj['show_status']: # Ordered.
            if section in tables.groups:
                df = tables.get_group(section)

                # Bring back TID as a regular column.
                df = df.reset_index().fillna("")

                # Always consider the hint column.
                if 'H' not in self.context.obj['show_fields']:
                    self.context.obj['show_fields'] = ['H'] + self.context.obj['show_fields']

                console = rconsole.Console()

                try:
                    # Print asked columns.
                    t = df[self.context.obj['show_fields']]
                except KeyError as e:
                    msg = ""
                    for section in self.context.obj['show_fields']:
                        if section not in df.columns:
                            msg += "cannot show field `{}`, not found in `{}` ".format(section, self.context.obj['input'])
                    error("INVALID_KEY", msg)
                else:
                    if len(df.index) <= 1:
                        show_lines = False
                        table_box = None
                    else:
                        show_lines = self.show_lines
                        table_box = self.table_box

                    table = richTable(show_header = self.context.obj['show_headers'], box = table_box, row_styles = ['row_odd', 'row_even'], show_lines = show_lines, expand = True)

                    for h in self.context.obj['show_fields']:
                        table.add_column(h, style = h)

                    for i,row in t.iterrows():
                        items = (str(row[k]) for k in self.context.obj['show_fields'])
                        if row['H']:
                            row_style = 'matching'
                        else:
                            row_style = None
                        table.add_row(*items, style = row_style)

                    title = richText(section, style = self.context.obj['status_key'], overflow = 'ellipsis')
                    panel = richPanel(table, title = title, title_align="left", border_style = self.context.obj['status_key'], box = self.panel_box, expand = True, padding = (0,0))

                    sections.append(richLayout(panel, name = section))

        layout = richLayout()
        layout.split_row(*sections)

        # FIXME ugly hack: pre-render the englobing panel, then count the number of "non empty" lines.
        fakepan = richPanel(layout, box = box.SIMPLE, border_style = 'none', padding = (0,0))
        console = rconsole.Console(theme = self.context.obj['theme'], no_color = True)
        with console.capture() as capture:
            console.print(fakepan)
        lines = capture.get().split('\n')
        nb_lines = 0
        for line in lines:
            letters = set(line)
            if letters != set({'m', '[', '\x1b', '│', '1', '3', '0', ' ', ';'}):
                nb_lines += 1

        # FIXME get rid of the space padding added by the panel, even without border.
        superpan = richPanel(layout, height = nb_lines, box = box.SIMPLE, border_style = 'none', padding = (0,0))
        return superpan

class HorizontalSpaced(Horizontal):
    def __init__(self, context):
        super().__init__(context, table_box = None, show_lines = False, panel_box = box.ROUNDED)

    def __rich__(self):
        df = self.context.obj['data']

        # Show the kanban tables.
        if df.empty:
            return "No task."

        sections = []

        if self.context.obj['highlight'] is not None:
            df.loc[self.context.obj['highlight'], 'H'] = self.contex.obj['highlight_mark']

        # Group by status.
        tables = df.groupby(self.context.obj['status_key'])
        # Loop over the asked ordered status groups.
        for section in self.context.obj['show_status']: # Ordered.
            if section in tables.groups:
                df = tables.get_group(section)

                # Bring back TID as a regular column.
                df = df.reset_index().fillna("")

                # Always consider the hint column.
                if 'H' not in self.context.obj['show_fields']:
                    self.context.obj['show_fields'] = ['H'] + self.context.obj['show_fields']

                console = rconsole.Console()

                try:
                    # Print asked columns.
                    t = df[self.context.obj['show_fields']]
                except KeyError as e:
                    msg = ""
                    for section in self.context.obj['show_fields']:
                        if section not in df.columns:
                            msg += "cannot show field `{}`, not found in `{}` ".format(section, self.context.obj['input'])
                    error("INVALID_KEY", msg)
                else:
                    if len(df.index) <= 1:
                        show_lines = False
                        table_box = None
                    else:
                        show_lines = self.show_lines
                        table_box = self.table_box

                    table = richTable(show_header = False, box = None, show_lines = False, expand = True, row_styles = ['row_odd', 'row_even'])
                    table.add_column('')

                    # One task_table per task.
                    for i,task in t.iterrows():

                        task_table = richTable(show_header = self.context.obj['show_headers'], box = table_box, show_lines = show_lines, expand = True, padding = (0,0))

                        # One column.
                        task_table.add_column('')

                        nb_title_keys = 0
                        for h in self.context.obj['show_fields']:
                            if h in ['H', self.context.obj['id_key'], self.context.obj['title_key']]:
                                nb_title_keys += 1

                        task_title = []
                        for h in self.context.obj['show_fields']:
                            item = str(task[h])

                            if h == 'H':
                                task_title.append(richText(task['H'], style = 'H'))
                                if len(task_title) == nb_title_keys:
                                    task_table.add_row(task_title[0]+task_title[1]+' '+task_title[2], style = h)
                                    task_title = []
                                continue
                            elif h == self.context.obj['id_key']:
                                task_title.append(richText(item, style = h))
                                if len(task_title) == nb_title_keys:
                                    task_table.add_row(task_title[0]+task_title[1]+' '+task_title[2], style = h)
                                    task_title = []
                                continue
                            elif h == self.context.obj['title_key']:
                                task_title.append(richText(item, style = h))
                                if len(task_title) == nb_title_keys:
                                    task_table.add_row(task_title[0]+task_title[1]+' '+task_title[2], style = h)
                                    task_title = []
                                continue

                            if len(task_title) == nb_title_keys:
                                task_table.add_row(task_title[0]+task_title[1]+' '+task_title[2], style = h)
                                task_title = []
                            else:
                                task_table.add_row(item, style = h)

                        # Add one final row for spacing,
                        # using a non-breakable space to bypass fakepan row filtering.
                        task_table.add_row(' ')

                        if task['H']:
                            row_style = 'matching'
                        else:
                            row_style = None
                        table.add_row(task_table, style = row_style)

                    title = richText(section, style = self.context.obj['status_key'], overflow = 'ellipsis')
                    panel = richPanel(table, title = title, title_align="left", border_style = self.context.obj['status_key'], box = self.panel_box, expand = True, padding = (0,0))

                    sections.append(richLayout(panel, name = section))

        layout = richLayout()
        layout.split_row(*sections)

        # FIXME ugly hack: pre-render the englobing panel, then count the number of "non empty" lines.
        fakepan = richPanel(layout, box = box.SIMPLE, border_style = 'none', padding = (0,0))
        console = rconsole.Console(theme = self.context.obj['theme'], no_color = True)
        with console.capture() as capture:
            console.print(fakepan)
        lines = capture.get().split('\n')
        nb_lines = 0
        for line in lines:
            letters = set(line)
            if letters != set({'m', '[', '\x1b', '│', '1', '3', '0', ' ', ';'}):
                nb_lines += 1

        # FIXME get rid of the space padding added by the panel, even without border.
        superpan = richPanel(layout, height = nb_lines, box = box.SIMPLE, border_style = 'none', padding = (0,0))
        return superpan


@cli.command()
@click.argument('TID', required=False, type=int, is_eager=True, callback=check_id)
@click.pass_context
def show(context, tid):
    """Show a task card (if ID is passed) or the whole the kanban (else)."""

    # Because commands invoked before may alter the table,
    # we need to reload the data.
    df = load_data(context)

    if tid is None:

        layout = context.obj['layouts'][context.obj['layout']](context)
        console = rconsole.Console(theme = context.obj['theme'])
        console.print(layout)


    else: # tid is not None.
        # Show a task card.
        row = df.loc[tid]

        console = rconsole.Console(theme = context.obj['theme'])

        table = richTable(box = None, show_header = False, expand = False, row_styles = ['row_odd', 'row_even'])
        table.add_column("Task")

        def add_row_text(table, key, icon = ''):
            if context.obj[key] in context.obj['show_fields']:
                if str(row[context.obj[key]]) != "nan": # FIXME WTF?
                    table.add_row(icon + row[context.obj[key]], style = context.obj[key])
                else:
                    return

        def add_row_list(table, key = context.obj['tags_key'], icon = ''):
            if context.obj[key] in context.obj['show_fields']:
                if str(row[context.obj[key]]) != "nan": # FIXME WTF?
                    tags = [icon+t for t in row[context.obj[key]].split(',')]
                    columns = richColumns(tags, expand = False)
                    table.add_row(columns, style = context.obj[key])
                else:
                    return

        add_row_text(table, 'status_key')
        add_row_text(table, 'details_key')
        add_row_list(table, 'tags_key', '🏷 ')
        add_row_text(table, 'deadline_key', '🗓')
        add_row_text(table, 'touched_key', ':calendar-text:')

        # Label content.
        label = richText()
        if context.obj['id_key'] in context.obj['show_fields']:
            label += richText(str(tid)+":", style = context.obj['id_key'])
        if context.obj['title_key'] in context.obj['show_fields']:
            label += richText(" "+row[context.obj['title_key']], style = context.obj['title_key'])

        panel = richPanel(table, title = label, title_align="left", expand = False, padding = (0,0))
        console.print(panel)


@cli.command()
@click.argument('TITLE', required=True, nargs=-1)
@click.option('-d', '--details' , type=str, prompt=True)
@click.option('-t', '--tags'    , type=str, prompt=True)
@click.option('-a', '--deadline', type=str, prompt=True)
@click.option('-s', '--status'  , type=str, default='TODO')
@click.pass_context
def add(context, title, status, details, tags, deadline):
    """Add a new task."""
    df = context.obj['data']
    if df.index.empty:
        next_id = 0
    else:
        next_id = df.index.max() + 1

    df.loc[next_id] = pd.Series({
        context.obj['status_key']: status,
        context.obj['title_key']: " ".join(title),
        context.obj['details_key']: details,
        context.obj['tags_key']: tags,
        context.obj['deadline_key']: deadline,
        context.obj['touched_key']: datetime.datetime.now().isoformat(),
    })

    save_data(context,df)

    context.obj['highlight'] = next_id
    context.invoke(show)


def default_from_existing(key):
    class OptionDefaultFromContext(click.Option):
        def get_default(self, context):
            tid = context.params['tid']
            df = context.obj['data']
            assert(tid in df.index)
            row = df.loc[tid]
            value = row[context.obj[key]]
            if str(value) != "nan": # FIXME WTF?
                self.default = value
            else:
                self.default = ""
            return super(OptionDefaultFromContext, self).get_default(context)
    return OptionDefaultFromContext

@cli.command()
@click.argument('TID', required=True, type=int, is_eager=True, callback=check_id)
@click.option('-t', '--title'   , type=str, prompt=True, cls = default_from_existing('title_key'))
@click.option('-s', '--status'  , type=str, prompt=True, cls = default_from_existing('status_key'))
@click.option('-d', '--details' , type=str, prompt=True, cls = default_from_existing('details_key'))
@click.option('-t', '--tags'    , type=str, prompt=True, cls = default_from_existing('tags_key'))
@click.option('-a', '--deadline', type=str, prompt=True, cls = default_from_existing('deadline_key'))
@click.pass_context
def edit(context, tid, title, status, details, tags, deadline):
    """Add a new task."""
    df = context.obj['data']
    assert(tid in df.index)
    df.loc[tid] = pd.Series({
            context.obj['status_key']: status,
            context.obj['title_key']: title,
            context.obj['details_key']: details,
            context.obj['tags_key']: tags,
            context.obj['deadline_key']: deadline,
            context.obj['touched_key']: datetime.datetime.now().isoformat(),
        })
    save_data(context,df)

    context.obj['highlight'] = tid
    context.invoke(show)


def check_yes(context, param, value):
    """Callback cheking for explicit user consent."""
    if not value:
        context.abort()
    return value

@cli.command()
@click.argument('TID', required=True, type=int, is_eager=True, callback=check_id)
@click.option('-y', '--yes', is_flag=True, expose_value=False, callback=check_yes, prompt="Permanently remove task from records?")
@click.pass_context
def remove(context, tid):
    """Delete a task."""
    df = context.obj['data']
    df = df.drop(index=tid)
    save_data(context, df)

    context.invoke(show)


def change_status(context, tid, new_status):
    """Edit the status of a task."""
    df = context.obj['data']

    row = df.loc[tid]
    if row.empty:
        error("ID_NOT_FOUND", "{} = {} not found in `{}`".format(context.obj['id_key'], tid, context.obj['input']))

    if new_status not in context.obj['show_status']:
        error("UNKNOWN_STATUS", "Unknown status `{}`".format(new_status))
    else:
        df.loc[tid, context.obj['status_key']] = new_status
        df.loc[tid, context.obj['touched_key']] = datetime.datetime.now().isoformat()

    save_data(context, df)

@cli.command()
@click.argument('TID', required=True, type=int, is_eager=True, callback=check_id)
@click.argument('STATUS', required=True, type=str)
@click.pass_context
def status(context, tid, status):
    """Explicitely change the status of a task.

    Use status names configured with --show-status."""

    change_status(context, tid, status)

    context.obj['highlight'] = tid
    context.invoke(show)


@cli.command()
@click.argument('TID', required=True, type=int, is_eager=True, callback=check_id)
@click.pass_context
def promote(context, tid):
    """Upgrade the status of a task to the next one.

    Use status names configured with --show-status."""

    df = context.obj['data']

    row = df.loc[tid]
    if row.empty:
        error("ID_NOT_FOUND", "{} = {} not found in `{}`".format(context.obj['id_key'], tid, context.obj['input']))

    i=0
    for i in range(len(context.obj['show_status'])):
        if row[context.obj['status_key']] == context.obj['show_status'][i]:
            break
        else:
            i += 1
    if i >= len(context.obj['show_status'])-1:
        error("UNKNOWN_STATUS", "Cannot promote task {}, already at the last status.".format(tid))
    else:
        change_status(context, tid, context.obj['show_status'][i+1])

    context.obj['highlight'] = tid
    context.invoke(show)


@cli.command()
@click.argument('TID', required=True, type=int, is_eager=True, callback=check_id)
@click.pass_context
def demote(context, tid):
    """Downgrade the status of a task to the previous one.

    Use status names configured with --show-status."""

    df = context.obj['data']

    row = df.loc[tid]
    if row.empty:
        error("ID_NOT_FOUND", "{} = {} not found in `{}`".format(context.obj['id_key'], tid, context.obj['input']))

    i=0
    for i in range(len(context.obj['show_status'])):
        if row[context.obj['status_key']] == context.obj['show_status'][i]:
            break
        else:
            i += 1
    if i == 0:
        error("UNKNOWN_STATUS", "Cannot demote task {}, already at the first status.".format(tid))
    else:
        change_status(context, tid, context.obj['show_status'][i-1])

    context.obj['highlight'] = tid
    context.invoke(show)


@cli.command()
@click.pass_context
def config(context):
    """Show the current configuration."""
    click.echo('Configuration:')
    click.echo(f"Data file: `{context.obj['input']}`")


@cli.command()
@click.argument('REGEX', required=True, type=str)
@click.option('-a', '--all' , is_flag = True, type = bool, default = False, help="Search even in hidden fields.")
@click.pass_context
def filter(context, regex, all):
    """Only show the tasks for which showed columns do contains a string matching the given regexp.

    Example: klyban filter '[Aa]nd'"""

    df = context.obj['data']

    # Bring back TID as a regular *string* column.
    df = df.reset_index().fillna("").astype('string')

    # Filter mask.
    if all:
        mask = np.column_stack([ df[col].str.contains(regex, na=False) for col in df ] )
    else:
        mask = np.column_stack([ df[col].str.contains(regex, na=False) for col in df[context.obj['show_fields']] ] )

    # Update in context for `show` to see.
    context.obj['data'] = df.loc[mask.any(axis=1)]

    context.invoke(show)


@cli.command()
@click.argument('REGEX', required=True, type=str)
@click.option('-m', '--mark', type = str, default = '▶', help="String used to highlight matching tasks.")
@click.option('-a', '--all' , is_flag = True, type = bool, default = False, help="Search even in hidden fields.")
@click.pass_context
def find(context, regex, mark, all):
    """Point out tasks containing a string matching the given regexp in any of the showed columns.

    Example: klyban find '[Aa]nd'"""

    df = context.obj['data']

    # Bring back TID as a regular *string* column.
    df = df.reset_index().fillna("").astype('string')

    # Filter mask.
    if all:
        mask = np.column_stack([ df[col].str.contains(regex, na=False) for col in df ] )
    else:
        mask = np.column_stack([ df[col].str.contains(regex, na=False) for col in df[context.obj['show_fields']] ] )

    # Mark out matching tasks.
    df.loc[mask.any(axis=1), 'H'] = mark

    # Update in context for `show` to see.
    context.obj['data'] = df

    context.invoke(show)


if __name__ == '__main__':
    cli(obj={})
