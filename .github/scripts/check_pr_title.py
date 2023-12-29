import os
import sys


KNOWN_PREFIXES = (
    'SEC: ',
    'BUG: ',
    'ENH: ',
    'DEP: ',
    'PI: ',
    'ROB: ',
    'DOC: ',
    'TST: ',
    'DEV: ',
    'STY: ',
    'MAINT: ',
)
PR_TITLE = os.getenv('PR_TITLE', '')

if not PR_TITLE.startswith(KNOWN_PREFIXES) or not PR_TITLE.split(': ', maxsplit=1)[1]:
    sys.stderr.write(
        'Please set an appropriate PR title: '
        'https://pypdf.readthedocs.io/en/latest/dev/intro.html#commit-messages\n',
    )
    sys.stderr.write(
        'If you do not know which one to choose or if multiple apply, make a best guess. '
        'Nobody will complain if it does not quite fit :-)\n',
    )
    sys.exit(1)
else:
    print('PR title appears to be valid.')
