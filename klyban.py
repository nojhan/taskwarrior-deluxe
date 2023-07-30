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
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich.columns import Columns
from rich.theme import Theme
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
@click.option('-H','--show-headers', is_flag=True, help="Show the headers.")
@click.option('-S', '--show-keys'   , default='ID,TITLE,DETAILS,TAGS', type=str , show_default=True, help="Comma-separated, ordered list of fields that should be shown (use 'all' for everything).")
@click.option('-G', '--highlight', type = int, default = None, help="Highlight a specific task.")
@click.option('-L', '--layout', type = click.Choice(['vertical-compact']), default = 'vertical-compact', help="How to display tasks.") # TODO , 'vertical-fancy', 'horizontal-compact', 'horizontal-fancy'
@click.option('-T', '--theme', type = click.Choice(['none', 'user', 'wb', 'blues', 'reds', 'greens'], case_sensitive=False), default = 'none', help="How to display tasks.")
# Low-level configuration options.
@click.option('--status-key'  , default='STATUS'  , type=str, show_default=True, help="Header key defining the status of tasks.")
@click.option('--status-list' , default='TODO,DOING,HOLD,DONE', type=str, show_default=True, help="Comma-separated, ordered list of possible values for the status of tasks.")
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

    context.obj['input'] = kwargs['input']

    context.obj['id_key'] = kwargs['id_key']
    context.obj['status_key'] = kwargs['status_key']
    context.obj['title_key'] = kwargs['title_key']
    context.obj['details_key'] = kwargs['details_key']
    context.obj['tags_key'] = kwargs['tags_key']
    context.obj['deadline_key'] = kwargs['deadline_key']
    context.obj['touched_key'] = kwargs['touched_key']

    context.obj['show_headers'] = kwargs['show_headers']
    context.obj['highlight'] = kwargs['highlight']
    context.obj['layout'] = kwargs['layout']
    context.obj['layouts'] = {
        'vertical-compact': VerticalCompact,
    }
    context.obj['themes'] = {
        'none': Theme({
            'H': '',
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
        'wb': Theme({
            'H': '',
            context.obj['id_key']: 'white',
            context.obj['status_key']: '',
            context.obj['title_key']: 'bold white',
            context.obj['details_key']: '',
            context.obj['tags_key']: 'italic',
            context.obj['deadline_key']: '',
            context.obj['touched_key']: 'color(240)',
            'row_odd': 'on color(234)',
            'row_even': 'on color(235)',
        })
    }
    context.obj['theme'] = context.obj['themes'][kwargs['theme']]

    context.obj['status_list'] = kwargs['status_list'].split(',')
    if kwargs['show_keys'].lower() == "all":
        context.obj['show_keys'] = [
            context.obj['id_key'],
            context.obj['status_key'],
            context.obj['title_key'],
            context.obj['details_key'],
            context.obj['tags_key'],
            context.obj['deadline_key'],
            context.obj['touched_key'],
        ]
    else:
        context.obj['show_keys'] = kwargs['show_keys'].split(',')

    # Always show the 'Hint' column.
    context.obj['show_keys'] = ['H'] + context.obj['show_keys']

    context.obj['debug'] = kwargs['debug']

    # At the end, always load data, whatever the command will be.
    context.obj['data'] = load_data(context)

    # Finally, if no command: defaults to `show`.
    if not context.invoked_subcommand:
        context.invoke(show)


class Layout:
    def __init__(self, context):
        self.context = context

class VerticalCompact(Layout):
    def __rich__(self):
        df = self.context.obj['data']

        # Show the kanban tables.
        if df.empty:
            return "No task."

        panels = []

        # Group by status.
        tables = df.groupby(self.context.obj['status_key'])
        # Loop over the asked ordered status groups.
        for section in self.context.obj['status_list']: # Ordered.
            if section in tables.groups:
                df = tables.get_group(section)
                # Bring back TID as a regular column.
                df = df.reset_index().fillna("")
                try:
                    # Print asked columns.
                    t = df[self.context.obj['show_keys']]
                except KeyError as e:
                    msg = ""
                    for section in self.context.obj['show_keys']:
                        if section not in df.columns:
                            msg += "cannot show field `{}`, not found in `{}` ".format(section, self.context.obj['input'])
                    error("INVALID_KEY", msg)
                else:
                    table = Table(show_header = self.context.obj['show_headers'], box = None, row_styles = ['row_odd', 'row_even'], expand = True)
                    for h in self.context.obj['show_keys']:
                        table.add_column(h, style = h)
                    for i,row in t.iterrows():
                        items = (str(row[k]) for k in self.context.obj['show_keys'])
                        table.add_row(*items)
                    panel = Panel.fit(table, title = section, title_align="left")
                    panels.append(panel)

        return rconsole.Group(*panels)


@cli.command()
@click.argument('TID', required=False, type=int, is_eager=True, callback=check_id)
@click.pass_context
def show(context, tid):
    """Show a task card (if ID is passed) or the whole the kanban (else)."""

    # Because commands invoked before may alter the table,
    # we need to reload the data.
    df = load_data(context)

    if tid is None:

        if context.obj['highlight'] is not None:
            df.loc[context.obj['highlight'], 'H'] = ':arrow_forward:'

        layout = context.obj['layouts'][context.obj['layout']](context)
        console = rconsole.Console(theme = context.obj['theme'])
        console.print(layout)


    else: # tid is not None.
        # Show a task card.
        row = df.loc[tid]

        console = rconsole.Console()

        table = Table(box = None, show_header = False)
        table.add_column("Task")

        def add_row_text(table, key, icon = ''):
            if context.obj[key] in context.obj['show_keys']:
                if str(row[context.obj[key]]) != "nan": # FIXME WTF?
                    table.add_row(icon + row[context.obj[key]])
                else:
                    return

        def add_row_list(table, key = context.obj['tags_key'], icon = ''):
            if context.obj[key] in context.obj['show_keys']:
                if str(row[context.obj[key]]) != "nan": # FIXME WTF?
                    tags = [icon+t for t in row[context.obj[key]].split(',')]
                    columns = Columns(tags, expand = False)
                    table.add_row(columns)
                else:
                    return

        add_row_text(table, 'details_key')
        add_row_list(table, 'tags_key', '🏷 ')
        add_row_text(table, 'deadline_key', '🗓')
        add_row_text(table, 'touched_key', ':calendar-text:')

        # Label content.
        l = []
        if context.obj['id_key'] in context.obj['show_keys']:
            l.append(str(tid))
        if context.obj['title_key'] in context.obj['show_keys']:
            l.append(row[context.obj['title_key']])
        label = ": ".join(l)

        panel = Panel.fit(table, title = label, title_align="left")
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
@click.option('-y', '--yes', is_flag=True, expose_value=False, callback=check_yes, prompt="Permanently delete task from records?")
@click.pass_context
def delete(context, tid):
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

    if new_status not in context.obj['status_list']:
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

    Use status names configured with --status-list."""

    change_status(context, tid, status)

    context.obj['highlight'] = tid
    context.invoke(show)


@cli.command()
@click.argument('TID', required=True, type=int, is_eager=True, callback=check_id)
@click.pass_context
def promote(context, tid):
    """Upgrade the status of a task to the next one.

    Use status names configured with --status-list."""

    df = context.obj['data']

    row = df.loc[tid]
    if row.empty:
        error("ID_NOT_FOUND", "{} = {} not found in `{}`".format(context.obj['id_key'], tid, context.obj['input']))

    i=0
    for i in range(len(context.obj['status_list'])):
        if row[context.obj['status_key']] == context.obj['status_list'][i]:
            break
        else:
            i += 1
    if i >= len(context.obj['status_list'])-1:
        error("UNKNOWN_STATUS", "Cannot promote task {}, already at the last status.".format(tid))
    else:
        change_status(context, tid, context.obj['status_list'][i+1])

    context.obj['highlight'] = tid
    context.invoke(show)


@cli.command()
@click.argument('TID', required=True, type=int, is_eager=True, callback=check_id)
@click.pass_context
def demote(context, tid):
    """Downgrade the status of a task to the previous one.

    Use status names configured with --status-list."""

    df = context.obj['data']

    row = df.loc[tid]
    if row.empty:
        error("ID_NOT_FOUND", "{} = {} not found in `{}`".format(context.obj['id_key'], tid, context.obj['input']))

    i=0
    for i in range(len(context.obj['status_list'])):
        if row[context.obj['status_key']] == context.obj['status_list'][i]:
            break
        else:
            i += 1
    if i == 0:
        error("UNKNOWN_STATUS", "Cannot demote task {}, already at the first status.".format(tid))
    else:
        change_status(context, tid, context.obj['status_list'][i-1])

    context.obj['highlight'] = tid
    context.invoke(show)


@cli.command()
@click.pass_context
def config(context):
    """Show the current configuration."""
    click.echo('Configuration:')
    click.echo(f"Data file: `{context.obj['input']}`")


if __name__ == '__main__':
    cli(obj={})
