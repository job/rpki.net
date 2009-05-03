"""
Testbed for figuring out how to write asynchronous HTTPS code.

$Id$

Copyright (C) 2009  Internet Systems Consortium ("ISC")

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
"""

# Command that may be useful for testing server side of this:
#
#    lynx -post_data -mime_header -source http://127.0.0.1:8000/
#
# Testing the client side of this is more entertaining, both because
# we need to be liberal in what we accept and also because servers do
# wildly different things depending both on HTTP version number and
# options signaled by the client and also on internal details in the
# server context (such as whether the content is static or generated
# by CGI).  It's useful to test against static content, but also to
# test against CGI-generated output, eg, the following trivial script:
#
#    print "Content-Type: text/plain; charset=US-ASCII\r"
#    print "\r"
#    for i in xrange(100):
#      print "%08d" % i, "." * 120, "\r"
#
# At least with Apache 2.0, result of running this differs
# significantly depending on whether client signals HTTP 1.0 or 1.1;
# the latter produces chunked output.

import sys, os, time, socket, asyncore, asynchat, traceback, urlparse
import rpki.async, rpki.sundial

debug = True

want_persistent_client = True
want_persistent_server = True

idle_timeout_default   = rpki.sundial.timedelta(seconds = 60)
active_timeout_default = rpki.sundial.timedelta(seconds = 15)

default_http_version = (1, 0)

class http_message(object):

  software_name = "BalmyBandicoot HTTP test code"

  def __init__(self, version = None, body = None, headers = None):
    self.version = version
    self.body = body
    self.headers = headers
    self.normalize_headers()

  def normalize_headers(self, headers = None):
    if headers is None:
      headers = () if self.headers is None else self.headers.items()
      translate_underscore = True
    else:
      translate_underscore = False
    result = {}
    for k,v in headers:
      if translate_underscore:
        k = k.replace("_", "-")
      k = "-".join(s.capitalize() for s in k.split("-"))
      v = v.strip()
      if k in result:
        result[k] += ", " + v
      else:
        result[k] = v
    self.headers = result

  @classmethod
  def parse_from_wire(cls, headers):
    self = cls()
    headers = headers.split("\r\n")
    self.parse_first_line(*headers.pop(0).split(None, 2))
    for i in xrange(len(headers) - 2, -1, -1):
      if headers[i + 1][0].isspace():
        headers[i] += headers[i + 1]
        del headers[i + 1]
    self.normalize_headers([h.split(":", 1) for h in headers])
    return self

  def format(self):
    s = self.format_first_line()
    if self.body is not None:
      assert isinstance(self.body, str)
      self.headers["Content-Length"] = len(self.body)
    for kv in self.headers.iteritems():
      s += "%s: %s\r\n" % kv
    s += "\r\n"
    if self.body is not None:
      s += self.body
    return s

  def __str__(self):
    return self.format()

  def parse_version(self, version):
    if version[:5] != "HTTP/":
      raise RuntimeError, "Couldn't parse version %s" % version
    self.version = tuple(int(i) for i in version[5:].split("."))

  def persistent(self):
    c = self.headers.get("Connection")
    if self.version == (1, 1):
      return c is None or "close" not in c.lower()
    elif self.version == (1, 0):
      return c is not None and "keep-alive" in c.lower()
    else:
      return False

class http_request(http_message):

  def __init__(self, cmd = None, path = None, version = default_http_version, body = None, callback = None, **headers):
    if cmd is not None and cmd != "POST" and body is not None:
      raise RuntimeError
    http_message.__init__(self, version = version, body = body, headers = headers)
    self.cmd = cmd
    self.path = path
    self.callback = callback

  def parse_first_line(self, cmd, path, version):
    self.parse_version(version)
    self.cmd = cmd
    self.path = path

  def format_first_line(self):
    self.headers.setdefault("User-Agent", self.software_name)
    return "%s %s HTTP/%d.%d\r\n" % (self.cmd, self.path, self.version[0], self.version[1])

class http_response(http_message):

  def __init__(self, code = None, reason = None, version = default_http_version, body = None, **headers):
    http_message.__init__(self, version = version, body = body, headers = headers)
    self.code = code
    self.reason = reason

  def parse_first_line(self, version, code, reason):
    self.parse_version(version)
    self.code = int(code)
    self.reason = reason

  def format_first_line(self):
    self.headers.setdefault("Date", time.strftime("%a, %d %b %Y %T GMT"))
    self.headers.setdefault("Server", self.software_name)
    return "HTTP/%d.%d %s %s\r\n" % (self.version[0], self.version[1], self.code, self.reason)

def logger(self, msg):
  if debug:
    print "[%r: %s]" % (self, msg)

class http_stream(asynchat.async_chat):

  log = logger

  idle_timeout = idle_timeout_default
  active_timeout = active_timeout_default

  def __init__(self, conn = None):
    asynchat.async_chat.__init__(self, conn = conn)
    self.buffer = []
    self.timer = rpki.async.timer(self.handle_timeout)
    self.restart()

  def restart(self):
    assert not self.buffer
    self.chunk_handler = None
    self.set_terminator("\r\n\r\n")
    if self.idle_timeout is not None:
      self.timer.set(self.idle_timeout)
    else:
      self.timer.cancel()

  def update_active_timeout(self):
    if self.active_timeout is not None:
      self.timer.set(self.active_timeout)
    else:
      self.timer.cancel()

  def collect_incoming_data(self, data):
    """Buffer the data"""
    self.buffer.append(data)
    self.update_active_timeout()

  def get_buffer(self):
    val = "".join(self.buffer)
    self.buffer = []
    return val

  def found_terminator(self):
    self.update_active_timeout()
    if self.chunk_handler:
      self.chunk_handler()
    elif not isinstance(self.get_terminator(), str):
      self.handle_body()
    else:
      self.log("Got headers")
      self.msg = self.parse_type.parse_from_wire(self.get_buffer())
      if self.msg.version == (1, 1) and "chunked" in self.msg.headers.get("Transfer-Encoding", "").lower():
        self.msg.body = []
        self.chunk_handler = self.chunk_header
        self.set_terminator("\r\n")
      elif "Content-Length" in self.msg.headers:
        self.set_terminator(int(self.msg.headers["Content-Length"]))
      else:
        self.handle_no_content_length()
      
  def chunk_header(self):
    n = int(self.get_buffer().partition(";")[0], 16)
    self.log("Chunk length %s" % n)
    if n:
      self.chunk_handler = self.chunk_body
      self.set_terminator(n)
    else:
      self.msg.body = "".join(self.msg.body)
      self.chunk_handler = self.chunk_discard_trailer

  def chunk_body(self):
    self.log("Chunk body")
    self.msg.body += self.buffer
    self.buffer = []
    self.chunk_handler = self.chunk_discard_crlf
    self.set_terminator("\r\n")

  def chunk_discard_crlf(self):
    self.log("Chunk CRLF")
    s = self.get_buffer()
    assert s == "", "Expected chunk CRLF, got '%s'" % s
    self.chunk_handler = self.chunk_header

  def chunk_discard_trailer(self):
    self.log("Chunk trailer")
    s = self.get_buffer()
    assert s == "", "Expected end of chunk trailers, got '%s'" % s
    self.chunk_handler = None
    self.handle_message()

  def handle_body(self):
    self.msg.body = self.get_buffer()
    self.handle_message()

  def handle_error(self):
    self.log("Error in HTTP stream handler")
    print traceback.format_exc()
    asyncore.close_all()

  def handle_timeout(self):
    self.log("Timeout, closing")
    self.close()

  def handle_close(self):
    asynchat.async_chat.handle_close(self)
    self.timer.cancel()
    self.log("Closed")

class http_server(http_stream):

  parse_type = http_request

  def __init__(self, conn, handlers):
    self.handlers = handlers
    http_stream.__init__(self, conn)
    self.expect_close = not want_persistent_server

  def handle_no_content_length(self):
    self.handle_message()

  def find_handler(self, path):
    """Helper method to search self.handlers."""
    for s, h in self.handlers:
      if path.startswith(s):
        return h
    return None

  def handle_message(self):
    if not self.msg.persistent():
      self.expect_close = True
    print "Query:"
    print self.msg
    print
    handler = self.find_handler(self.msg.path)
    error = None
    if False and self.msg.cmd != "POST":
      error = 501, "No handler for method %s" % self.msg.cmd
    elif False and self.headers["Content-Type"] != rpki_content_type:
      error = 415, "No handler for Content-Type %s" % self.headers["Content-Type"]
    elif handler is None:
      error = 404, "No handler for URL %s" % self.msg.path
    if error is None:
      handler(self.msg, self.send_message)
    else:
      self.send_error(*error)

  def send_error(self, code, reason):
    self.handle_message_message(http_response(code = code, reason = reason))

  def send_message(self, msg):
    msg.headers["Connection"] = "Close" if self.expect_close else "Keep-Alive"
    print "Reply:"
    print msg
    print
    self.push(msg.format())
    if self.expect_close:
      self.log("Closing")
      self.timer.cancel()
      self.close_when_done()
    else:      
      self.log("Listening for next message")
      self.restart()

class http_listener(asyncore.dispatcher):

  log = logger

  def __init__(self, handlers, port = 80, host = ""):
    asyncore.dispatcher.__init__(self)
    self.handlers = handlers
    self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
    self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    self.bind((host, port))
    self.listen(5)
    self.log("Listening on (host, port) %r, handlers %r" % ((host, port), handlers))

  def handle_accept(self):
    self.log("Accepting connection")
    server = http_server(conn = self.accept()[0], handlers = self.handlers)

  def handle_error(self):
    self.log("Error in HTTP listener")
    print traceback.format_exc()
    asyncore.close_all()

# Might need to know whether outbound data is fully sent, as part of
# this state thing.  If so, calling .writable() ought to do the trick,
# so long as it has no side effects (need to check asynchat.py for
# that).
#
# I don't think there's anything we can do about crossed-in-mail
# problem where we finish sending query just as server sends us
# an unsolicited message.  One would like to think that the HTTP
# specification rules this out, but no bets.

class http_client(http_stream):

  parse_type = http_response

  def __init__(self, manager, hostport):
    self.log("Creating new connection to %s" % repr(hostport))
    http_stream.__init__(self)
    self.manager = manager
    self.hostport = hostport
    self.state = "idle"
    self.expect_close = not want_persistent_client
    self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
    self.connect(hostport)

  def handle_no_content_length(self):
    self.set_terminator(None)

  def send_request(self, msg):
    self.log("Sending request")
    assert self.state == "idle"
    assert msg is not None
    self.state = "request-sent"
    msg.headers["Connection"] = "Close" if self.expect_close else "Keep-Alive"
    self.push(msg.format())
    self.restart()

  def handle_message(self):
    if not self.msg.persistent():
      self.expect_close = True
    self.log("Message received, state %s" % self.state)
    msg = None
    if self.state == "request-sent":
      msg = self.manager.done_with_request(self.hostport)
      print "Query:"
      print msg
      print
    elif self.state == "idle":
      self.log("Received unsolicited message")
    elif self.state == "closing":
      assert not self.msg.body
      self.log("Ignoring empty response received while closing")
      return
    else:
      raise RuntimeError, "[%r: Unexpected state]" % self
    print "Reply:"
    print self.msg
    print
    self.state = "idle"
    if msg != None:
      msg.callback(self.msg)
    msg = self.manager.next_request(self.hostport, not self.expect_close)
    if msg is not None:
      self.log("Got a new message to send from my queue")
      self.send_request(msg)
    else:
      self.log("Closing")
      self.state = "closing"
      self.close_when_done()

  def handle_connect(self):
    self.log("Connected")
    msg = self.manager.next_request(self.hostport, True)
    self.send_request(msg)

  def handle_close(self):
    http_stream.handle_close(self)
    if self.get_terminator() is None:
      self.handle_body()

class http_manager(object):

  log = logger

  # Hmm, these parallel dicts are almost certainly a hint that we need
  # an http_queue class or some such, then the manager can become a
  # simple map of destinations to queues, or something like that.

  def __init__(self):
    self.clients = {}
    self.queues  = {}

  def query(self, url, callback, body = None):
    u = urlparse.urlparse(url)
    assert u.scheme == "http" and u.username is None and u.password is None and u.params == "" and u.query == "" and u.fragment == ""
    request = http_request(cmd = "POST", path = u.path, body = body, callback = callback,
                           Host = u.hostname, Content_Type = "text/plain")
    hostport = (u.hostname or "localhost", u.port or 80)
    assert (hostport in self.queues) == (hostport in self.clients)
    if hostport not in self.queues:
      self.queues[hostport] = []
    self.queues[hostport].append(request)
    if hostport not in self.clients:
      self.clients[hostport] = http_client(self, hostport)
      
  # Messages have to stay in queue here in case client fails and we
  # need to retry with another client.  What a mess.

  def done_with_request(self, hostport):
    req = self.queues[hostport].pop(0)
    self.log("Dequeuing request %r" % req)
    return req

  def next_request(self, hostport, usable):
    queue = self.queues.get(hostport)
    if not queue:
      self.log("Queue is empty")
      return None
    self.log("Queue: %r" % queue)
    if usable:
      self.log("Queue not empty and connection usable")
      return queue[0]
    else:
      self.log("Queue not empty but connection not usable, spawning")
      self.clients[hostport] = http_client(self, hostport)
      self.log("Spawned connection %r" % self.clients[hostport])
      return None

# server: reuse rest-style dispatcher from current https code.
# 
# 	add downcall to set result: don't do this presently, because
# 	can't, but want it in new code.  so break async_http
# 	http_server.handle_message() into two method, one handles
# 	upcall to app dispatch, other is downcall to send result;
# 	latter probably used as bound method passed as callback to
# 	app.
# 
# 	dunno if client method hack (below) would work for server.
# 	maybe.  if so it would be a method of the request message
# 	which would need to include a handle on the server stream.
# 
# client: need callback; right now demo code just consumes result
# 	directly (by printing it), for real use we need to give result
# 	to somebody.  hand them the query message too, for matchup?
# 	we're pulling it off queue as part of response processing
# 	anyway, might be useful to make it available.  or even make
# 	the callback for the result be a method of the query message,
# 	which has the cute property that we can have multiple methods,
# 	eg one for callback, one for errback.


def client(msg, url, timeout = 300, callback = None):
  pass

import signal

def server(handlers, port, host ="", catch_signals = (signal.SIGINT, signal.SIGTERM)):
  if not isinstance(handlers, (tuple, list)):
    handlers = (("/", handlers),)
  try:
    def raiseExitNow(signum, frame):
      print "[Signal received, shutting down]"
      raise asyncore.ExitNow
    old_signal_handlers = tuple((sig, signal.signal(sig, raiseExitNow)) for sig in catch_signals)
    listener = http_listener(port = 8000, handlers = handlers)
    rpki.async.event_loop()
  except asyncore.ExitNow:
    pass
  finally:
    for sig, handler in old_signal_handlers:
      signal.signal(sig, handler)

if len(sys.argv) == 1:

  def handler(query_message, reply_callback):
    reply_callback(http_response(
      code              = 200,
      reason            = "OK",
      body              = str(query_message),
      Cache_Control     = "no-cache,no-store",
      Content_Type      = "text/plain"))

  def other_handler(query_message, reply_callback):
    reply_callback(http_response(
      code              = 200,
      reason            = "OK",
      body              = "Ok, you found it.\r\n\r\n" + str(query_message),
      Cache_Control     = "no-cache,no-store",
      Content_Type      = "text/plain"))

  server(port = 8000, handlers = (("/wombat", other_handler), ("/", handler)))

else:

  def got_it(msg):
    print "Got response:"
    print msg
    print

  manager = http_manager()
  for url in sys.argv[1:]:
    manager.query(url = url, callback = got_it, body = "Hi, I'm trying to talk to URL %s" % url)

  rpki.async.event_loop()
