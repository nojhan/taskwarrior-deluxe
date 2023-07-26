import sys

import agate
import click
import tabulate

# Global group holding global options.
@click.group()
@click.option('-i', '--input', help="CSV data file.", default='.klyban.csv', type=click.Path(writable=True, readable=True, allow_dash=True))
@click.option('--status-key', help="Header key defining the status of items.", default='STATUS', type=str)
@click.option('--status-list', help="Comma-separated, ordered list of possible values for the status of items.", default='TODO,DOING,HOLD,DONE', type=str)
@click.pass_context
def cli(context, input, status_key, status_list):
    # ensure that context.obj exists and is a dict (in case `cli()` is called
    # by means other than the `if` block below)
    context.ensure_object(dict)
    context.obj['input'] = input
    context.obj['status_key'] = status_key
    context.obj['status_list'] = status_list.split(',')


@cli.command()
@click.pass_context
def show(context):
    """Show the kanban."""

    # Automagically manages standard input if input=="-", thanks to allow_dash=True.
    with click.open_file(context.obj['input'], mode='r') as fd:
        table = agate.Table.from_csv(fd)

    tables = table.group_by(context.obj['status_key'])
    for k in context.obj['status_list']:
        try:
            table = tables[k]
        except KeyError:
            pass
        else:
            print(table.columns[0][0])
            t = table.exclude(context.obj['status_key'])
            print(tabulate.tabulate(t.columns, headers=t.column_names, tablefmt="fancy_grid"))


@cli.command()
@click.pass_context
def config(context):
    """Show the current configuration."""
    click.echo('Configuration:')
    click.echo(f"Data file: `{context.obj['input']}`")

if __name__ == '__main__':
    cli(obj={})
