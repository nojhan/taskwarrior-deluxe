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
import rich.console as richconsole
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
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
        if context.obj['debug']:
            print("Loaded:")
            print(df)
        return df


def save_data(context, df):
    if context.obj['debug']:
        print("Save:")
        print(df)
    # FIXME double check that there are actually data.

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

    context.obj['show_headers'] = kwargs['show_headers']

    context.obj['id_key'] = kwargs['id_key']
    context.obj['status_key'] = kwargs['status_key']
    context.obj['title_key'] = kwargs['title_key']
    context.obj['details_key'] = kwargs['details_key']
    context.obj['tags_key'] = kwargs['tags_key']
    context.obj['deadline_key'] = kwargs['deadline_key']
    context.obj['touched_key'] = kwargs['touched_key']

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

    context.obj['debug'] = kwargs['debug']

    # At the end, always load data, whatever the command will be.
    context.obj['data'] = load_data(context)

    # If no command: defaults to `show`.
    if not context.invoked_subcommand:
        context.invoke(show)


@cli.command()
@click.argument('TID', required=False, type=int, is_eager=True, callback=check_id)
@click.pass_context
def show(context, tid):
    """Show a task card (if ID is passed) or the whole the kanban (else)."""

    if tid is None:
        # Show the kanban tables.
        df = context.obj['data']
        if df.empty:
            print("No task.")
            return

        # Group by status.
        tables = df.groupby(context.obj['status_key'])
        # Loop over the asked ordered status groups.
        for section in context.obj['status_list']: # Ordered.
            if section in tables.groups:
                df = tables.get_group(section)
                # Bring back TID as a regular column.
                df = df.reset_index().fillna("")
                try:
                    # Print asked columns.
                    t = df[context.obj['show_keys']]
                except KeyError as e:
                    msg = ""
                    for section in context.obj['show_keys']:
                        if section not in df.columns:
                            msg += "cannot show field `{}`, not found in `{}` ".format(section, context.obj['input'])
                    error("INVALID_KEY", msg)
                else:
                    console = richconsole.Console()
                    # table = Table(show_header = context.obj['show_headers'], row_styles=["color(39)","color(33)"], box = None)
                    table = Table(show_header = context.obj['show_headers'], box = None)
                    for h in context.obj['show_keys']:
                        table.add_column(h)
                    for i,row in t.iterrows():
                        items = (str(row[k]) for k in context.obj['show_keys'])
                        table.add_row(*items)
                    # console.print(table)
                    # panel = Panel.fit(table, title = section, title_align="left", border_style="bold blue")
                    panel = Panel.fit(table, title = section, title_align="left")
                    console.print(panel)


    else: # tid is not None.
        # Show a task card.
        df = context.obj['data']
        row = df.loc[tid]

        t_label  = ["╔", "═", "╗"]
        t_top    = ["╟", "─", "╩", "═", "╗"]
        t_body   = ["║", " ", "║"]
        t_sep    = ["╟", "─", "╢"]
        t_bottom = ["╚", "═", "╝"]

        width = len(datetime.datetime.now().isoformat())

        # Label content.
        l = []
        if context.obj['id_key'] in context.obj['show_keys']:
            l.append(str(tid))
        if context.obj['title_key'] in context.obj['show_keys']:
            l.append(row[context.obj['title_key']])
        lbl = ":".join(l)
        label = textwrap.shorten(lbl, width=width, placeholder="…")

        # Label format.
        card  = t_label[0] + t_label[1]*len(label) + t_label[2] + "\n"
        card += t_body[0] + label + t_body[2] + "\n"
        card += t_top[0] + t_top[1]*len(label) + t_top[2] + t_top[3]*(width-len(label)-1) + t_top[4] + "\n"

        if context.obj['details_key'] in context.obj['show_keys']:
            if str(row[context.obj['details_key']]) != "nan": # FIXME WTF?
                d = row[context.obj['details_key']]
            else:
                d = ''
            details = textwrap.wrap(d, width)
            for line in details:
                card += t_body[0] + line + t_body[1]*(width-len(line)) + t_body[2] + "\n"

        if context.obj['tags_key'] in context.obj['show_keys']:
            card += t_sep[0] + t_sep[1]*width + t_sep[2] + "\n"
            if str(row[context.obj['tags_key']]) != "nan": # FIXME WTF?
                t = row[context.obj['tags_key']]
            else:
                t = ''
            tags = textwrap.wrap(t, width)
            for line in tags:
                card += t_body[0] + line + t_body[1]*(width-len(line)) + t_body[2] + "\n"

        if context.obj['deadline_key'] in context.obj['show_keys']:
            card += t_sep[0] + t_sep[1]*width + t_sep[2] + "\n"
            if str(row[context.obj['deadline_key']]) != "nan": # FIXME WTF?
                t = row[context.obj['deadline_key']]
            else:
                t = ''
            deadline = textwrap.wrap(t, width)
            for line in deadline:
                card += t_body[0] + line + t_body[1]*(width-len(line)) + t_body[2] + "\n"

        if context.obj['touched_key'] in context.obj['show_keys']:
            card += t_sep[0] + t_sep[1]*width + t_sep[2] + "\n"
            if str(row[context.obj['touched_key']]) != "nan": # FIXME WTF?
                t = row[context.obj['touched_key']]
            else:
                t = ''
            touched = textwrap.wrap(t, width)
            for line in touched:
                card += t_body[0] + line + t_body[1]*(width-len(line)) + t_body[2] + "\n"

        card += t_bottom[0] + t_bottom[1]*width + t_bottom[2] # No newline.
        print(card)


@cli.command()
@click.argument('TITLE', required=True, nargs=-1)
@click.option('-d', '--details' , type=str, default=None, prompt=True)
@click.option('-t', '--tags'    , type=str, default=None, prompt=True)
@click.option('-a', '--deadline', type=str, default=None, prompt=True)
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
        if row[context.obj['status_key']][1] == context.obj['status_list'][i]:
            break
        else:
            i += 1
    if i >= len(context.obj['status_list'])-1:
        error("UNKNOWN_STATUS", "Cannot promote task {}, already at the last status.".format(tid))
    else:
        change_status(context, tid, context.obj['status_list'][i+1])

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
        if row[context.obj['status_key']][1] == context.obj['status_list'][i]:
            break
        else:
            i += 1
    if i == 0:
        error("UNKNOWN_STATUS", "Cannot demote task {}, already at the first status.".format(tid))
    else:
        change_status(context, tid, context.obj['status_list'][i-1])

    context.invoke(show)


@cli.command()
@click.pass_context
def config(context):
    """Show the current configuration."""
    click.echo('Configuration:')
    click.echo(f"Data file: `{context.obj['input']}`")


if __name__ == '__main__':
    cli(obj={})
