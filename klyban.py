import sys

import pandas as pd
import click
import tabulate

error_codes = {
    "INVALID_KEY": 100,
    "ID_NOT_FOUND": 101,
    "UNKNOWN_STATUS": 102,
}

def error(id,msg):
    print(msg)
    sys.exit(error_codes[id])

def load_data(context):
    # Automagically manages standard input if input=="-", thanks to allow_dash=True.
    with click.open_file(context.obj['input'], mode='r') as fd:
        df = pd.read_csv(fd)
        # FIXME data sanity checks: unique index, aligned status, valid dates

    df.set_index(context.obj['id_key'])
    return df

def save_data(context, df):
    # Automagically manages standard input if input=="-", thanks to allow_dash=True.
    with click.open_file(context.obj['input'], mode='w') as fd:
        df.to_csv(fd)



# Global group holding global options.
@click.group()
@click.option('-i', '--input', help="CSV data file.", default='.klyban.csv', type=click.Path(writable=True, readable=True, allow_dash=True), show_default=True)
@click.option('--status-key', help="Header key defining the status of tasks.", default='STATUS', type=str, show_default=True)
@click.option('--status-list', help="Comma-separated, ordered list of possible values for the status of tasks.", default='TODO,DOING,HOLD,DONE', type=str, show_default=True)
@click.option('--id-key', help="Header key defining the unique ID of tasks.", default='ID', type=str, show_default=True)
@click.option('--title-key', help="Header key defining the title (short description) of tasks.", default='TITLE', type=str, show_default=True)
@click.option('--details-key', help="Header key defining the details (long description) of tasks.", default='DETAILS', type=str, show_default=True)
@click.option('--tags-key', help="Header key defining the tags associated to tasks.", default='TAG', type=str, show_default=True)
@click.option('--deadline-key', help="Header key defining the deadlines tasks.", default='DEADLINE', type=str, show_default=True)
@click.option('--show-keys', help="Comman-separated, ordered list of fields that should be shown", default='ID,TITLE,DETAILS,DEADLINE,TAG', type=str, show_default=True)
@click.pass_context
def cli(context, input, status_key, status_list, id_key, title_key, details_key, tags_key, deadline_key, show_keys):
    # ensure that context.obj exists and is a dict (in case `cli()` is called
    # by means other than the `if` block below)
    context.ensure_object(dict)
    context.obj['input'] = input

    context.obj['status_key'] = status_key
    context.obj['id_key'] = id_key
    context.obj['title_key'] = title_key
    context.obj['details_key'] = details_key
    context.obj['tags_key'] = tags_key
    context.obj['deadline_key'] = deadline_key

    context.obj['status_list'] = status_list.split(',')
    context.obj['show_keys'] = show_keys.split(',')


@cli.command()
@click.pass_context
def show(context):
    """Show the kanban."""

    df = load_data(context)

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
                print(tabulate.tabulate(t, headers=context.obj['show_keys'], tablefmt="fancy_grid", showindex=False))

@cli.command()
@click.argument('ID')
@click.pass_context
def promote(context, id):
    """Upgrade the status of task `ID` to the next one.

    As configured with --status-list."""

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
        error("UNKNOWN_STATUS","Cannot promote task {}, already at the last status.".format(id))
    else:
        df.loc[df[context.obj['id_key']] == int(id), context.obj['status_key']] = context.obj['status_list'][i+1]

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
