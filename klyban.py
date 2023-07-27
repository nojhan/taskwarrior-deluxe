import sys
import csv
import json
import datetime
from configparser import ConfigParser

import pandas as pd
import click
import tabulate

error_codes = {
    "INVALID_KEY": 100,
    "ID_NOT_FOUND": 101,
    "UNKNOWN_STATUS": 102,
}


def error(id,msg):
    print("ERROR:",msg)
    sys.exit(error_codes[id])


def load_data(context):
    try:
        # Automagically manages standard input if input=="-", thanks to allow_dash=True.
        with click.open_file(context.obj['input'], mode='r') as fd:
            df = pd.read_csv(fd)
            # FIXME data sanity checks: unique index, aligned status, valid dates

    except FileNotFoundError:
        df = pd.DataFrame(columns=[
            context.obj['id_key'],
            context.obj['status_key'],
            context.obj['title_key'],
            context.obj['details_key'],
            context.obj['tags_key'],
            context.obj['deadline_key'],
            context.obj['touched_key'],
        ])
        save_data(context, df)

    df.set_index(context.obj['id_key'])
    return df


def save_data(context, df):
    # FIXME double check that there are actually data.
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


# Global group holding global options.
@click.group()
@click.option(
    '-c', '--config',
    type         = click.Path(dir_okay=False),
    default      = '.klyban.conf',
    callback     = configure,
    is_eager     = True,
    expose_value = False,
    help         = 'Read option defaults from the specified configuration file',
    show_default = True,
)
@click.option('-i', '--input' , help="CSV data file.", default='.klyban.csv', type=click.Path(writable=True, readable=True, allow_dash=True), show_default=True)
@click.option('--status-key'  , default='STATUS'  , type=str, show_default=True, help="Header key defining the status of tasks.")
@click.option('--status-list' , default='TODO,DOING,HOLD,DONE', type=str, show_default=True, help="Comma-separated, ordered list of possible values for the status of tasks.")
@click.option('--id-key'      , default='ID'      , type=str, show_default=True, help="Header key defining the unique ID of tasks.")
@click.option('--title-key'   , default='TITLE'   , type=str, show_default=True, help="Header key defining the title (short description) of tasks.")
@click.option('--details-key' , default='DETAILS' , type=str, show_default=True, help="Header key defining the details (long description) of tasks.")
@click.option('--tags-key'    , default='TAGS'    , type=str, show_default=True, help="Header key defining the tags associated to tasks.")
@click.option('--deadline-key', default='DEADLINE', type=str, show_default=True, help="Header key defining the deadlines tasks.")
@click.option('--touched-key', default='TOUCHED', type=str, show_default=True, help="Header key defining the deadlines tasks.")
@click.option('--show-keys'   , default='ID,TITLE,DETAILS,DEADLINE,TAGS', type=str , show_default=True, help="Comma-separated, ordered list of fields that should be shown")
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

    context.obj['status_list'] = kwargs['status_list'].split(',')
    context.obj['show_keys'] = kwargs['show_keys'].split(',')


@cli.command()
@click.pass_context
def show(context):
    """Show the kanban."""

    df = load_data(context)
    if df.empty:
        print("No task.")
        return

    tables = df.groupby(context.obj['status_key'])
    for k in context.obj['status_list']: # Ordered.
        if k in tables.groups:
            df = tables.get_group(k)
            # STATUS
            print(k)
            try:
                t = df[context.obj['show_keys']]
            except KeyError as e:
                msg = ""
                for k in context.obj['show_keys']:
                    if k not in df.columns:
                        msg += "cannot show field `{}`, not found in `{}` ".format(k, context.obj['input'])
                error("INVALID_KEY", msg)
            else:
                print(tabulate.tabulate(t.fillna(""), headers=context.obj['show_keys'], tablefmt="fancy_grid", showindex=False))


@cli.command()
@click.argument('TITLE', required=True, nargs=-1)
@click.option('-d', '--details' , type=str, default="", prompt=True)
@click.option('-t', '--tags'    , type=str, default="", prompt=True)
@click.option('-a', '--deadline', type=str, default="", prompt=True)
@click.option('-s', '--status'  , type=str, default='TODO')
@click.pass_context
def add(context, title, status, details, tags, deadline):
    """Add a new task."""
    df = load_data(context)
    next_id = df[context.obj['id_key']].max() + 1
    df.loc[next_id] = {
        context.obj['id_key']:next_id,
        context.obj['status_key']: status,
        context.obj['title_key']: " ".join(title),
        context.obj['details_key']: details,
        context.obj['tags_key']: tags,
        context.obj['deadline_key']: deadline,
        context.obj['touched_key']: datetime.datetime.now().isoformat(),
    }
    save_data(context,df)

    context.invoke(show)


def check_id(context, param, value):
    """Eager callback, checking ID before edit's options prompting."""
    df = load_data(context)
    if id not in df.index:
        error("ID_NOT_FOUND", "{} `{}` was not found in data `{}`".format(context.obj['id_key'], value, context.obj['input']))

@cli.command()
@click.argument('ID', required=True, type=int, is_eager=True, callback=check_id)
@click.option('-t', '--title'   , type=str, prompt=True)
@click.option('-s', '--status'  , type=str, prompt=True)
@click.option('-d', '--details' , type=str, prompt=True, default="")
@click.option('-t', '--tags'    , type=str, prompt=True, default="")
@click.option('-a', '--deadline', type=str, prompt=True, default="")
# FIXME populate the defaults with actual existing data.
@click.pass_context
def edit(context, id, title, status, details, tags, deadline):
    """Add a new task."""
    df = load_data(context)

    df.loc[id] = {
        context.obj['id_key']: id,
        context.obj['status_key']: status,
        context.obj['title_key']: " ".join(title),
        context.obj['details_key']: details,
        context.obj['tags_key']: tags,
        context.obj['deadline_key']: deadline,
        context.obj['touched_key']: datetime.datetime.now().isoformat(),
    }
    save_data(context,df)

    context.invoke(show)


@cli.command()
@click.argument('ID', required=True)
@click.pass_context
def promote(context, id):
    """Upgrade the status of task `ID` to the next one.

    Use status names configured with --status-list."""

    df = load_data(context)

    row = df.loc[ df[context.obj['id_key']] == int(id) ]
    if row.empty:
        error("ID_NOT_FOUND", "{} = {} not found in `{}`".format(context.obj['id_key'], id, context.obj['input']))

    i=0
    for i in range(len(context.obj['status_list'])):
        if row[context.obj['status_key']][1] == context.obj['status_list'][i]:
            break
        else:
            i += 1
    if i >= len(context.obj['status_list'])-1:
        error("UNKNOWN_STATUS", "Cannot promote task {}, already at the last status.".format(id))
    else:
        df.loc[df[context.obj['id_key']] == int(id), context.obj['status_key']] = context.obj['status_list'][i+1]
        df.loc[df[context.obj['id_key']] == int(id), context.obj['touched_key']] = datetime.datetime.now().isoformat()

    save_data(context, df)

    context.invoke(show)


@cli.command()
@click.argument('ID', required=True)
@click.pass_context
def demote(context, id):
    """Downgrade the status of task `ID` to the previous one.

    Use status names configured with --status-list."""

    df = load_data(context)

    row = df.loc[ df[context.obj['id_key']] == int(id) ]
    if row.empty:
        error("ID_NOT_FOUND", "{} = {} not found in `{}`".format(context.obj['id_key'], id, context.obj['input']))

    i=0
    for i in range(len(context.obj['status_list'])):
        if row[context.obj['status_key']][1] == context.obj['status_list'][i]:
            break
        else:
            i += 1
    if i == 0:
        error("UNKNOWN_STATUS", "Cannot demote task {}, already at the first status.".format(id))
    else:
        df.loc[df[context.obj['id_key']] == int(id), context.obj['status_key']] = context.obj['status_list'][i-1]
        df.loc[df[context.obj['id_key']] == int(id), context.obj['touched_key']] = datetime.datetime.now().isoformat()

    save_data(context, df)

    context.invoke(show)


@cli.command()
@click.pass_context
def config(context):
    """Show the current configuration."""
    click.echo('Configuration:')
    click.echo(f"Data file: `{context.obj['input']}`")


if __name__ == '__main__':
    cli(obj={})
