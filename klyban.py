import sys

import agate
import click

# Global group holding global options.
@click.group()
@click.option('-i', '--input', default='.klyban.csv', type=click.Path(writable=True, readable=True, allow_dash=True))
@click.pass_context
def cli(context,input):
    # ensure that context.obj exists and is a dict (in case `cli()` is called
    # by means other than the `if` block below)
    context.ensure_object(dict)
    context.obj['input'] = input


@cli.command()
@click.pass_context
def show(context):
    with click.open_file(context.obj['input'], mode='r') as fd:
        table = agate.Table.from_csv(fd)

    table.print_table(output = sys.stdout)

@cli.command()
@click.pass_context
def config(context):
    click.echo('Configuration:')
    click.echo(f"Data file: `{context.obj['input']}`")

if __name__ == '__main__':
    cli(obj={})
