# -*- coding: utf-8 -*-
# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause
from __future__ import absolute_import, division, print_function, unicode_literals

import logging
from os.path import dirname
import re
import sys

from ._vendor.auxlib.decorators import memoize
from ._vendor.auxlib.compat import Utf8NamedTemporaryFile
from .common.compat import on_win

from .common.path import win_path_to_unix
from .common.url import path_to_url
from os.path import abspath, join
from os import environ

log = logging.getLogger(__name__)

# in conda/exports.py
memoized = memoize


def path_identity(path):
    """Used as a dummy path converter where no conversion necessary"""
    return path


def unix_path_to_win(path, root_prefix=""):
    """Convert a path or :-separated string of paths into a Windows representation

    Does not add cygdrive.  If you need that, set root_prefix to "/cygdrive"
    """
    if len(path) > 1 and (";" in path or (path[1] == ":" and path.count(":") == 1)):
        # already a windows path
        return path.replace("/", "\\")
    path_re = root_prefix + r'(/[a-zA-Z]/(?:(?![:\s]/)[^:*?"<>])*)'

    def _translation(found_path):
        group = found_path.group(0)
        return "{0}:{1}".format(group[len(root_prefix)+1],
                                group[len(root_prefix)+2:].replace("/", "\\"))
    translation = re.sub(path_re, _translation, path)
    translation = re.sub(":([a-zA-Z]):\\\\",
                         lambda match: ";" + match.group(0)[1] + ":\\",
                         translation)
    return translation


# curry cygwin functions
def win_path_to_cygwin(path):
    return win_path_to_unix(path, "/cygdrive")


def cygwin_path_to_win(path):
    return unix_path_to_win(path, "/cygdrive")


def translate_stream(stream, translator):
    return "\n".join(translator(line) for line in stream.split("\n"))


def human_bytes(n):
    """
    Return the number of bytes n in more human readable form.

    Examples:
        >>> human_bytes(42)
        '42 B'
        >>> human_bytes(1042)
        '1 KB'
        >>> human_bytes(10004242)
        '9.5 MB'
        >>> human_bytes(100000004242)
        '93.13 GB'
    """
    if n < 1024:
        return '%d B' % n
    k = n/1024
    if k < 1024:
        return '%d KB' % round(k)
    m = k/1024
    if m < 1024:
        return '%.1f MB' % m
    g = m/1024
    return '%.2f GB' % g


# TODO: this should be done in a more extensible way
#     (like files for each shell, with some registration mechanism.)

# defaults for unix shells.  Note: missing "exe" entry, which should be set to
#    either an executable on PATH, or a full path to an executable for a shell
unix_shell_base = dict(
                       binpath="/bin/",  # mind the trailing slash.
                       echo="echo",
                       env_script_suffix=".sh",
                       nul='2>/dev/null',
                       path_from=path_identity,
                       path_to=path_identity,
                       pathsep=":",
                       printdefaultenv='echo $CONDA_DEFAULT_ENV',
                       printpath="echo $PATH",
                       printps1='echo $CONDA_PROMPT_MODIFIER',
                       promptvar='PS1',
                       sep="/",
                       set_var='export ',
                       shell_args=["-l", "-c"],
                       shell_suffix="",
                       slash_convert=("\\", "/"),
                       source_setup="source",
                       test_echo_extra="",
                       var_format="${}",
)

msys2_shell_base = dict(
                        unix_shell_base,
                        path_from=unix_path_to_win,
                        path_to=win_path_to_unix,
                        binpath="/bin/",  # mind the trailing slash.
                        printpath="python -c \"import os; print(';'.join(os.environ['PATH'].split(';')[1:]))\" | cygpath --path -f -",  # NOQA
)

if on_win:
    shells = {
        # "powershell.exe": dict(
        #    echo="echo",
        #    test_echo_extra=" .",
        #    var_format="${var}",
        #    binpath="/bin/",  # mind the trailing slash.
        #    source_setup="source",
        #    nul='2>/dev/null',
        #    set_var='export ',
        #    shell_suffix=".ps",
        #    env_script_suffix=".ps",
        #    printps1='echo $PS1',
        #    printdefaultenv='echo $CONDA_DEFAULT_ENV',
        #    printpath="echo %PATH%",
        #    exe="powershell.exe",
        #    path_from=path_identity,
        #    path_to=path_identity,
        #    slash_convert = ("/", "\\"),
        # ),
        "cmd.exe": dict(
            echo="@echo",
            var_format="%{}%",
            binpath="\\Scripts\\",  # mind the trailing slash.
            source_setup="call",
            test_echo_extra="",
            nul='1>NUL 2>&1',
            set_var='set ',
            shell_suffix=".bat",
            env_script_suffix=".bat",
            printps1="@echo %PROMPT%",
            promptvar="PROMPT",
            # parens mismatched intentionally.  See http://stackoverflow.com/questions/20691060/how-do-i-echo-a-blank-empty-line-to-the-console-from-a-windows-batch-file # NOQA
            printdefaultenv='IF NOT "%CONDA_DEFAULT_ENV%" == "" (\n'
                            'echo %CONDA_DEFAULT_ENV% ) ELSE (\n'
                            'echo()',
            printpath="@echo %PATH%",
            exe="cmd.exe",
            shell_args=["/d", "/c"],
            path_from=path_identity,
            path_to=path_identity,
            slash_convert=("/", "\\"),
            sep="\\",
            pathsep=";",
        ),
        "cygwin": dict(
            unix_shell_base,
            exe="bash.exe",
            binpath="/Scripts/",  # mind the trailing slash.
            path_from=cygwin_path_to_win,
            path_to=win_path_to_cygwin
        ),
        # bash is whichever bash is on PATH.  If using Cygwin, you should use the cygwin
        #    entry instead.  The only major difference is that it handle's cygwin's /cygdrive
        #    filesystem root.
        "bash.exe": dict(
            msys2_shell_base, exe="bash.exe",
        ),
        "bash": dict(
            msys2_shell_base, exe="bash",
        ),
        "sh.exe": dict(
            msys2_shell_base, exe="sh.exe",
        ),
        "zsh.exe": dict(
            msys2_shell_base, exe="zsh.exe",
        ),
        "zsh": dict(
            msys2_shell_base, exe="zsh",
        ),
    }

else:
    shells = {
        "bash": dict(
            unix_shell_base, exe="bash",
        ),
        "dash": dict(
            unix_shell_base, exe="dash",
            source_setup=".",
        ),
        "zsh": dict(
            unix_shell_base, exe="zsh",
        ),
        "fish": dict(
            unix_shell_base, exe="fish",
            pathsep=" ",
        ),
    }


# ##########################################
# put back because of conda build
# ##########################################

urlpath = url_path = path_to_url


def md5_file(path):  # pragma: no cover
    from .gateways.disk.read import compute_md5sum
    return compute_md5sum(path)


def hashsum_file(path, mode='md5'):  # pragma: no cover
    import hashlib
    h = hashlib.new(mode)
    with open(path, 'rb') as fi:
        while True:
            chunk = fi.read(262144)  # process chunks of 256KB
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

from subprocess import list2cmdline

@memoize
def sys_prefix_unfollowed():
    """Since conda is installed into non-root environments as a symlink only
    and because sys.prefix follows symlinks, this function can be used to
    get the 'unfollowed' sys.prefix.

    This value is usually the same as the prefix of the environment into
    which conda has been symlinked. An example of when this is necessary
    is when conda looks for external sub-commands in find_commands.py
    """
    try:
        frame = next(iter(sys._current_frames().values()))
        while frame.f_back:
            frame = frame.f_back
        code = frame.f_code
        filename = code.co_filename
        unfollowed = dirname(dirname(filename))
    except Exception:
        return sys.prefix
    return unfollowed


def quote_for_shell(arguments, shell=None):
    if not shell:
        shell = 'cmd.exe' if on_win else 'bash'
    if shell == 'cmd.exe':
        return list2cmdline(arguments)
    else:
        # If any multiline argument gets mixed with any other argument (which is true if we've
        # arrived in this function) then we just quote it. This assumes something like:
        # ['python', '-c', 'a\nmultiline\nprogram\n']
        # It may make sense to allow specifying a replacement character for '\n' too? e.g. ';'
        quoted = []
        # This could all be replaced with some regex wizardry but that is less readable and
        # for code like this, readability is very important.
        for arg in arguments:
            quote = None
            if '"' in arg:
                quote = "'"
            elif "'" in arg:
                quote = '"'
            elif (not ' ' in arg and not '\n' in arg):
                quote = ''
            else:
                quote = '"'
            quoted.append(quote + arg + quote)
        return ' '.join(quoted)


def wrap_subprocess_call(on_win, root_prefix, prefix, dev_mode, debug_wrapper_scripts, arguments):
    tmp_prefix = abspath(join(prefix, '.tmp'))
    script_caller = None
    multiline = False
    if len(arguments)==1 and '\n' in arguments[0]:
        multiline = True
    if on_win:
        comspec = environ[str('COMSPEC')]
        conda_bat = environ.get("CONDA_BAT", abspath(join(root_prefix, 'condabin', 'conda.bat')))
        with Utf8NamedTemporaryFile(mode='w', prefix=tmp_prefix,
                                    suffix='.bat', delete=False) as fh:
            fh.write("@FOR /F \"tokens=100\" %%F IN ('chcp') DO @SET CONDA_OLD_CHCP=%%F\n")
            fh.write('@chcp 65001>NUL\n')
            fh.write('@CALL \"{0}\" activate \"{1}\"\n'.format(conda_bat, prefix).encode('utf-8'))
            # while helpful for debugging, this gets in the way of running wrapped commands where
            #    we care about the output.
            # fh.write('echo "PATH: %PATH%\n')
            if multiline:
                # No point silencing the first line. If that's what's wanted then
                # it needs doing for each line and the caller may as well do that.
                fh.write(u"{0}\n".format(arguments[0]))
            else:
                fh.write("@{0}\n".format(quote_for_shell(arguments)))
            fh.write('@chcp %CONDA_OLD_CHCP%>NUL\n')
            script_caller = fh.name
        command_args = [comspec, '/d', '/c', script_caller]
    else:
        shell_path = 'sh' if 'bsd' in sys.platform else 'bash'
        # During tests, we sometimes like to have a temp env with e.g. an old python in it
        # and have it run tests against the very latest development sources. For that to
        # work we need extra smarts here, we want it to be instead:
        if dev_mode:
            conda_exe = [abspath(join(root_prefix, 'bin', 'python')), '-m', 'conda']
        else:
            conda_exe = [environ.get("CONDA_EXE", abspath(join(root_prefix, 'bin', 'conda')))]
        with Utf8NamedTemporaryFile(mode='w', prefix=tmp_prefix, delete=False) as fh:
            hook_quoted = quote_for_shell(conda_exe + ['shell.posix', 'hook'])
            if debug_wrapper_scripts:
                fh.write(u">&2 echo '*** environment before ***'\n"
                         u">&2 env\n")
                fh.write(u">&2 echo \"$({0})\"\n"
                         .format(hook_quoted))
            fh.write(u"eval \"$({0})\"\n"
                     .format(hook_quoted))
            fh.write(u"conda activate {0}\n".format(quote_for_shell((prefix,))))
            if debug_wrapper_scripts:
                fh.write(u">&2 echo '*** environment after ***'\n"
                         u">&2 env\n")
            if multiline:
                # The ' '.join() is pointless since mutliline is only True when there's 1 arg
                # still, if that were to change this would prevent breakage.
                fh.write(u"{0}\n".format(' '.join(arguments)))
            elif len(arguments)==1:

                fh.write(u"{0}\n".format(arguments))
            else:
                fh.write(u"{0}\n".format(quote_for_shell(arguments)))
            script_caller = fh.name
        command_args = [shell_path, "-x", script_caller]

    return script_caller, command_args
