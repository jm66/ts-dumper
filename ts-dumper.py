#!/usr/bin/env python
"""Dump transcripts from Transkribus.eu to single files."""
import datetime
import logging
import logging.handlers
import os
import sys
from pathlib import Path
from subprocess import PIPE, Popen
from typing import Dict, Optional

import urllib3

PACKAGE_NAME = "ts-dumper"
__version__ = "0.0.2-dev0"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

REQUIREMENTS = [
    'xmltodict==0.14.2',
    'requests==2.32.3',
    'click==8.1.8',
    'click-log==0.4.0',
    'lxml==5.3.0',
    'rich==13.9.4',
]

try:
    import click
    from lxml import etree
    import requests
    import xmltodict
    import click_log
    from rich.progress import (
        Progress,
        BarColumn,
        SpinnerColumn,
        TextColumn,
        TimeRemainingColumn,
    )
    from rich import print as cprint
except ImportError:
    for package in REQUIREMENTS:
        args = [sys.executable, "-m", "pip", "install", "--quiet", package]
        env = os.environ.copy()
        print(f'Installing {package}')
        process = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE, env=env)
        _, stderr = process.communicate()
        if process.returncode != 0:
            print(f'Error trying to install requirement {package}: {stderr}')
            sys.exit(1)
    print(f'Successfully installed: {", ".join(REQUIREMENTS)}.')
    print(f'Please, execute the script again.')
    sys.exit(0)

_LOGGER = logging.getLogger(__name__)
click_log.basic_config(_LOGGER)

# Syslog
handler = logging.handlers.SysLogHandler(
    facility=logging.handlers.SysLogHandler.LOG_DAEMON
)
_LOGGER.addHandler(handler)

TRANSKRIBUS_BASE = 'https://transkribus.eu/TrpServer'
TRANSKRIBUS_REST = f'{TRANSKRIBUS_BASE}/rest'
TRANSKRIBUS_LOGIN = f'{TRANSKRIBUS_REST}/auth/login'


def _xmlParseDoc(xml_bytes):
    return etree.XML(xml_bytes.encode('utf-8'))


def _xmlParse__xpathEval_getContent(xml_bytes, xml_expression):
    domDoc = _xmlParseDoc(xml_bytes)
    return domDoc.xpath(xml_expression)


def auth_login(username: str, password: str) -> Optional[str]:
    """Login to transkribus api and return headers or none."""
    data = {'user': username, 'pw': password}
    rv = requests.post(TRANSKRIBUS_LOGIN, data=data)
    rv.raise_for_status()
    session_id = _xmlParse__xpathEval_getContent(rv.text, "//sessionId/text()")
    if session_id:
        session_id = session_id[0]
        return session_id
    else:
        return None


def get_text_from_transcript(headers, url):
    """Get text from transcript."""
    rv = requests.get(url, headers=headers)
    tmp = xmltodict.parse(rv.content.decode())
    pg = tmp['PcGts']['Page']
    if 'TextRegion' in pg:
        tr = pg['TextRegion']
        if 'TextEquiv' in tr:
            if tr['TextEquiv']['Unicode'] is not None:
                return tr['TextEquiv']['Unicode']
    return None


def get_collection_from_name(name, headers) -> Optional[Dict]:
    """Get collection from name."""
    rv = requests.get(f'{TRANSKRIBUS_REST}/collections', headers=headers)
    rv.raise_for_status()
    collections = rv.json()['trpCollection']
    collection = list(filter(lambda x: x['colName'] == name, collections))
    if collection:
        return collection[0]
    return None


@click.command()
@click_log.simple_verbosity_option(_LOGGER)
@click.version_option(
    version=__version__, message='%(prog)s v%(version)s',
)
@click.option(
    '--collection-name',
    type=click.STRING,
    required=True,
    help='Collection name',
    default='Cadmania',
)
@click.option(
    '--username',
    type=click.STRING,
    required=True,
    help='Transkribus username.',
)
@click.option(
    "--password",
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    help='Transkribus username password.',
)
@click.option(
    '--target-dir',
    type=click.Path(),
    required=True,
    help='Target directory where files will be written.',
)
@click.option(
    '-x',
    'showexceptions',
    is_flag=True,
    default=False,
    envvar='VSS_EM_EXC',
    help="Print back traces when exception occurs.",
    show_envvar=True,
)
def cli(
    collection_name: str,
    username: str,
    password: str,
    target_dir: Path,
    showexceptions,
):
    """Run main cli."""
    welcome_msg = f'Running {PACKAGE_NAME} v{__version__}. '
    _LOGGER.info(welcome_msg)
    progress_bar_elements = [
        "{task.description} [progress.remaining]{task.completed}/{task.total}",
        SpinnerColumn(),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
    ]
    base_path = Path(target_dir)
    if not base_path.exists():
        _LOGGER.warning(f'{base_path} does not exist. Creating.')
        base_path.mkdir()
    session_id = auth_login(username, password)
    headers = {'Cookie': f'JSESSIONID={session_id}'}
    _LOGGER.info(f'Got session ID={session_id}')
    _LOGGER.info(f'Getting collection ID from name {collection_name}')
    collection = get_collection_from_name(
        name=collection_name, headers=headers
    )
    if collection is None:
        raise Exception(f'Could not find collection {collection_name}')
    else:
        collection_id = collection['colId']
        collection_desc = collection['description']
        _LOGGER.info(
            f'Found {collection_name} ({collection_id}) '
            f'description={collection_desc} '
        )
    # get docs from collections
    headers.update({'Accept': 'application/json'})
    rv = requests.get(
        f'{TRANSKRIBUS_REST}/collections/{collection_id}/list', headers=headers
    )
    docs = rv.json()
    _LOGGER.info(
        f'Got {len(docs)} documents from Collection Id {collection_id}'
    )
    # pull doc pages
    docs_pages = {}
    with Progress(*progress_bar_elements) as progress:
        task = progress.add_task(f'Getting Pages per doc', total=len(docs),)
        for doc in docs:
            doc_id = doc['docId']
            doc_title = doc["title"]
            rv = requests.get(
                f'{TRANSKRIBUS_REST}/collections/{collection_id}/'
                f'{doc_id}/fulldoc',
                headers=headers,
            )
            doc_dict = rv.json()
            pages = doc_dict['pageList']['pages']
            # _LOGGER.info([len(p['tsList']['transcripts']) for p in pages])
            _LOGGER.debug(
                f'DocId={doc_id} title={doc_title} found pages={len(pages)}'
            )
            docs_pages[doc['docId']] = {'doc': doc, 'pages': pages}
            progress.advance(task)
    # iterate through items
    with Progress(*progress_bar_elements) as progress:
        task = progress.add_task(
            f'[green]Getting latest Transcripts from document pages',
            total=len(docs_pages.keys()),
        )
        for doc_id, obj in docs_pages.items():
            pages = obj['pages']
            task2 = progress.add_task(
                f'[cyan]Getting transcript from {doc_id}', total=len(pages)
            )
            for page in pages:
                try:
                    transcripts = page['tsList']['transcripts']
                    image_file_name = page["imgFileName"]
                    text_file_name = f'{Path(image_file_name).stem}.txt'
                    meta_file_name = f'{Path(image_file_name).stem}-meta.txt'
                    text_file_path = base_path.joinpath(text_file_name)
                    meta_file_path = base_path.joinpath(meta_file_name)
                    _LOGGER.debug(f'{image_file_name} + {meta_file_path}-> {len(transcripts)}')
                    max_ts = max([t['timestamp'] for t in transcripts])
                    max_ts_dt = datetime.datetime.fromtimestamp(max_ts / 1e3)
                    _LOGGER.debug(f'Getting ts {max_ts_dt}')
                    latest = list(
                        filter(lambda x: max_ts == x['timestamp'], transcripts)
                    )
                    text = get_text_from_transcript(headers, latest[0]['url'])
                    if text is None:
                        o_latest = list(
                            filter(
                                lambda x: latest[0]['timestamp']
                                != x['timestamp'],
                                transcripts,
                            )
                        )
                        text = get_text_from_transcript(
                            headers, o_latest[0]['url']
                        )
                    if text is None:
                        text = ''
                    progress.console.print(
                        f'Writing {text_file_path} '
                        f'with {len(text)} characters.'
                    )
                    text_file_path.write_text(text)
                    if latest:
                        meta = [
                            f'status:\t{latest[0].get("status", "N/A")}',
                            f'userName:\t{latest[0].get("userName", "N/A")}',
                            f'nrOfLines:\t{latest[0].get("nrOfLines", 0)}'
                        ]
                        meta_file_path.write_text('\n'.join(meta))
                except Exception as ex:
                    cprint(
                        f'[bold red]Error[/bold red] '
                        f'Processing {page}: {str(ex)} '
                    )
                progress.advance(task2)
            progress.advance(task)


def run() -> None:
    """Run entry point.

    Wraps click for full control over exception handling in Click.
    """
    # A hack to see if exception details should be printed.
    exceptionflags = ['-x']
    verbose = [c for c in exceptionflags if c in sys.argv]

    try:
        # Could use cli.invoke here to use the just created context
        # but then shell completion will not work. Thus calling
        # standalone mode to keep that working.
        result = cli.main(standalone_mode=False)
        if isinstance(result, int):
            sys.exit(result)

    # Exception handling below is done to use _LOGGER
    # and mimic as close as possible what click would
    # do normally in its main()
    except click.ClickException as ex:
        ex.show()  # let Click handle its own errors
        sys.exit(ex.exit_code)
    except click.Abort:
        _LOGGER.critical("Aborted!")
        sys.exit(1)
    except Exception as ex:  # pylint: disable=broad-except
        if verbose:
            _LOGGER.exception(ex)
        else:
            _LOGGER.error("%s: %s", type(ex).__name__, ex)
            _LOGGER.info(
                "Run with %s to see full exception information.",
                " or ".join(exceptionflags),
            )
        sys.exit(1)


if __name__ == "__main__":
    run()
