"""
Logging facilities for RPKI libraries.

$Id$

Copyright (C) 2009--2010  Internet Systems Consortium ("ISC")

Permission to use, copy, modify, and distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND ISC DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS.  IN NO EVENT SHALL ISC BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE
OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.

Portions copyright (C) 2007--2008  American Registry for Internet Numbers ("ARIN")

Permission to use, copy, modify, and distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND ARIN DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS.  IN NO EVENT SHALL ARIN BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE
OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
"""

import syslog, sys, os, time
import traceback as tb

## @var enable_trace
# Whether call tracing is enabled.

enable_trace = False

## @var use_syslog
# Whether to use syslog

use_syslog = True

tag = ""
pid = 0

def init(ident = "rpki", flags = syslog.LOG_PID, facility = syslog.LOG_DAEMON):
  """
  Initialize logging system.
  """

  if use_syslog:
    return syslog.openlog(ident, flags, facility)
  else:
    global tag, pid
    tag = ident
    pid = os.getpid()

def set_trace(enable):
  """
  Enable or disable call tracing.
  """

  global enable_trace
  enable_trace = enable

class logger(object):
  """
  Closure for logging.
  """

  def __init__(self, priority):
    self.priority = priority

  def __call__(self, message):
    if use_syslog:
      return syslog.syslog(self.priority, message)
    else:
      sys.stderr.write("%s %s[%d]: %s\n" % (time.strftime("%F %T"), tag, pid, message))

error = logger(syslog.LOG_ERR)
warn  = logger(syslog.LOG_WARNING)
note  = logger(syslog.LOG_NOTICE)
info  = logger(syslog.LOG_INFO)
debug = logger(syslog.LOG_DEBUG)

def trace():
  """
  Execution trace -- where are we now, and whence came we here?
  """

  if enable_trace:
    bt = tb.extract_stack(limit = 3)
    return debug("[%s() at %s:%d from %s:%d]" % (bt[1][2], bt[1][0], bt[1][1], bt[0][0], bt[0][1]))

def traceback():
  """
  Consolidated backtrace facility with a bit of extra info.
  """

  assert sys.exc_info() != (None, None, None), "rpki.log.traceback() called without valid trace on stack, this is a programming error"
  bt = tb.extract_stack(limit = 3)
  error("Exception caught in %s() at %s:%d called from %s:%d" % (bt[1][2], bt[1][0], bt[1][1], bt[0][0], bt[0][1]))
  bt = tb.format_exc()
  assert bt is not None, "Apparently I'm still not using the right test for null backtrace"
  for line in bt.splitlines():
    warn(line)