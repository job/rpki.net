"""
Router origin-authentication rpki-router protocol implementation.  See
draft-ymbk-rpki-rtr-protocol in fine Internet-Draft repositories near
you.

Run the program with the --help argument for usage information, or see
documentation for the *_main() functions.

NB: At present this supports an old version of the protocol, because
the router implementation that currently tests against it also
implements that old version.  One of these days we'll fix that.


$Id$

Copyright (C) 2009-2010  Internet Systems Consortium ("ISC")

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

import sys, os, struct, time, glob, socket, fcntl, signal, syslog
import asyncore, asynchat, subprocess, traceback, getopt
import rpki.x509, rpki.ipaddrs, rpki.sundial, rpki.config
import rpki.async

class read_buffer(object):
  """
  Wrapper around synchronous/asynchronous read state.
  """

  def __init__(self):
    self.buffer = ""

  def update(self, need, callback):
    """
    Update count of needed bytes and callback, then dispatch to callback.
    """
    self.need = need
    self.callback = callback
    return self.callback(self)

  def available(self):
    """
    How much data do we have available in this buffer?
    """
    return len(self.buffer)

  def needed(self):
    """
    How much more data does this buffer need to become ready?
    """
    return self.need - self.available()

  def ready(self):
    """
    Is this buffer ready to read yet?
    """
    return self.available() >= self.need

  def get(self, n):
    """
    Hand some data to the caller.
    """
    b = self.buffer[:n]
    self.buffer = self.buffer[n:]
    return b

  def put(self, b):
    """
    Accumulate some data.
    """
    self.buffer += b

  def retry(self):
    """
    Try dispatching to the callback again.
    """
    return self.callback(self)

class pdu(object):
  """
  Object representing a generic PDU in the rpki-router protocol.
  Real PDUs are subclasses of this class.
  """

  version = 0                           # Protocol version

  _pdu = None                           # Cached when first generated

  common_header_struct = struct.Struct("!BB")

  def __cmp__(self, other):
    return cmp(self.to_pdu(), other.to_pdu())

  def check(self):
    """
    Check attributes to make sure they're within range.
    """
    pass

  @classmethod
  def read_pdu(cls, reader):
    return reader.update(need = cls.common_header_struct.size, callback = cls.got_common_header)

  @classmethod
  def got_common_header(cls, reader):
    if not reader.ready():
      return None
    assert reader.available() >= cls.common_header_struct.size
    version, pdu_type = cls.common_header_struct.unpack(reader.buffer[:cls.common_header_struct.size])
    assert version == cls.version, "PDU version is %d, expected %d" % (version, cls.version)
    self = cls.pdu_map[pdu_type]()
    return reader.update(need = self.header_struct.size, callback = self.got_header)

  def consume(self, client):
    """
    Handle results in test client.  Default behavior is just to print
    out the PDU.
    """
    log(self)

  def send_file(self, server, filename):
    """
    Send a content of a file as a cache response.  Caller should catch IOError.
    """
    f = open(filename, "rb")
    server.push_pdu(cache_response())
    server.push_file(f)
    server.push_pdu(end_of_data(serial = server.current_serial))

  def send_nodata(self, server):
    """
    Send a nodata error.
    """
    server.push_pdu(error_report(errno = error_report.codes["No Data Available"], errpdu = self))

class pdu_with_serial(pdu):
  """
  Base class for PDUs consisting of just a serial number.
  """

  header_struct = struct.Struct("!BBHL")

  def __init__(self, serial = None):
    if serial is not None:
      if isinstance(serial, str):
        serial = int(serial)
      assert isinstance(serial, int)
      self.serial = serial

  def __str__(self):
    return "[%s, serial #%s]" % (self.__class__.__name__, self.serial)

  def to_pdu(self):
    """
    Generate the wire format PDU for this prefix.
    """
    if self._pdu is None:
      self._pdu = self.header_struct.pack(self.version, self.pdu_type, 0, self.serial)
    return self._pdu

  def got_header(self, reader):
    if not reader.ready():
      return None
    b = reader.get(self.header_struct.size)
    version, pdu_type, zero, self.serial = self.header_struct.unpack(b)
    assert zero == 0
    assert b == self.to_pdu()
    return self

class pdu_empty(pdu):
  """
  Base class for empty PDUs.
  """

  header_struct = struct.Struct("!BBH")

  def __str__(self):
    return "[%s]" % self.__class__.__name__

  def to_pdu(self):
    """
    Generate the wire format PDU for this prefix.
    """
    if self._pdu is None:
      self._pdu = self.header_struct.pack(self.version, self.pdu_type, 0)
    return self._pdu

  def got_header(self, reader):
    if not reader.ready():
      return None
    b = reader.get(self.header_struct.size)
    version, pdu_type, zero = self.header_struct.unpack(b)
    assert zero == 0
    assert b == self.to_pdu()
    return self

class serial_notify(pdu_with_serial):
  """
  Serial Notify PDU.
  """

  pdu_type = 0

  def consume(self, client):
    """
    Respond to a serial_notify message with either a serial_query or
    reset_query, depending on what we already know.
    """
    log(self)
    if client.current_serial is None:
      client.push_pdu(reset_query())
    elif self.serial != client.current_serial:
      client.push_pdu(serial_query(serial = client.current_serial))
    else:
      log("[Notify did not change serial number, ignoring]")

class serial_query(pdu_with_serial):
  """
  Serial Query PDU.
  """

  pdu_type = 1

  def serve(self, server):
    """
    Received a serial query, send incremental transfer in response.
    If client is already up to date, just send an empty incremental
    transfer.
    """
    log(self)
    if server.get_serial() is None:
      self.send_nodata(server)
    elif int(server.current_serial) == self.serial:
      log("[Client is already current, sending empty IXFR]")
      server.push_pdu(cache_response())
      server.push_pdu(end_of_data(serial = server.current_serial))
    else:
      try:
        self.send_file(server, "%s.ix.%s" % (server.current_serial, self.serial))
      except IOError:
        server.push_pdu(cache_reset())

class reset_query(pdu_empty):
  """
  Reset Query PDU.
  """

  pdu_type = 2

  def serve(self, server):
    """
    Received a reset query, send full current state in response.
    """
    log(self)
    if server.get_serial() is None:
      self.send_nodata(server)
    else:
      try:
        fn = "%s.ax" % server.current_serial
        self.send_file(server, fn)
      except IOError:
        server.push_pdu(error_report(errno = error_report.codes["Internal Error"], errpdu = self, errmsg = "Couldn't open %s" % fn))

class cache_response(pdu_empty):
  """
  Incremental Response PDU.
  """

  pdu_type = 3

class end_of_data(pdu_with_serial):
  """
  End of Data PDU.
  """

  pdu_type = 7

  def consume(self, client):
    """
    Handle end_of_data response.
    """
    log(self)
    client.current_serial = self.serial

class cache_reset(pdu_empty):
  """
  Cache reset PDU.
  """

  pdu_type = 8

  def consume(self, client):
    """
    Handle cache_reset response, by issuing a reset_query.
    """
    log(self)
    client.push_pdu(reset_query())

class prefix(pdu):
  """
  Object representing one prefix.  This corresponds closely to one PDU
  in the rpki-router protocol, so closely that we use lexical ordering
  of the wire format of the PDU as the ordering for this class.
  """

  source = 0                            # Source (0 == RPKI)

  header_struct = struct.Struct("!BBHBBBB")
  asnum_struct = struct.Struct("!L")

  @classmethod
  def from_asn1(cls, asnum, t):
    """
    Read a prefix from a ROA in the tuple format used by our ASN.1
    decoder.
    """
    assert len(t[0]) <= cls.addr_type.bits
    x = 0L
    for y in t[0]:
      x = (x << 1) | y
    x <<= (cls.addr_type.bits - len(t[0]))
    self = cls()
    self.asn = asnum
    self.prefix = cls.addr_type(x)
    self.prefixlen = len(t[0])
    self.max_prefixlen = self.prefixlen if t[1] is None else t[1]
    self.color = 0
    self.announce = 1
    self.check()
    return self

  def __str__(self):
    plm = "%s/%s-%s" % (self.prefix, self.prefixlen, self.max_prefixlen)
    return "%s %8s  %-32s %s" % ("+" if self.announce else "-", self.asn, plm, ":".join(("%02X" % ord(b) for b in self.to_pdu())))

  def show(self):
    print "# Class:       ", self.__class__.__name__
    print "# ASN:         ", self.asn
    print "# Prefix:      ", self.prefix
    print "# Prefixlen:   ", self.prefixlen
    print "# MaxPrefixlen:", self.max_prefixlen
    print "# Color:       ", self.color
    print "# Announce:    ", self.announce

  def check(self):
    """
    Check attributes to make sure they're within range.
    """
    assert self.announce in (0, 1)
    assert self.prefixlen >= 0 and self.prefixlen <= self.addr_type.bits
    assert self.max_prefixlen >= self.prefixlen and self.max_prefixlen <= self.addr_type.bits
    assert len(self.to_pdu()) == 12 + self.addr_type.bits / 8, "Expected %d byte PDU, got %d" % (12 + self.addr_type.bits / 8, len(self.to_pdu()))

  def to_pdu(self, announce = None):
    """
    Generate the wire format PDU for this prefix.
    """
    if announce is not None:
      assert announce in (0, 1)
    elif self._pdu is not None:
      return self._pdu
    pdu = (self.header_struct.pack(self.version, self.pdu_type, self.color,
                                   announce if announce is not None else self.announce,
                                   self.prefixlen, self.max_prefixlen, self.source) +
           self.prefix.to_bytes() +
           self.asnum_struct.pack(self.asn))
    if announce is None:
      assert self._pdu is None
      self._pdu = pdu
    return pdu

  def got_header(self, reader):
    return reader.update(need = self.header_struct.size + self.addr_type.bits / 8 + self.asnum_struct.size, callback = self.got_pdu)

  def got_pdu(self, reader):
    if not reader.ready():
      return None
    b1 = reader.get(self.header_struct.size)
    b2 = reader.get(self.addr_type.bits / 8)
    b3 = reader.get(self.asnum_struct.size)
    version, pdu_type, self.color, self.announce, self.prefixlen, self.max_prefixlen, source = self.header_struct.unpack(b1)
    assert source == self.source
    self.prefix = self.addr_type.from_bytes(b2)
    self.asn = self.asnum_struct.unpack(b3)[0]
    assert b1 + b2 + b3 == self.to_pdu()
    return self

class ipv4_prefix(prefix):
  """
  IPv4 flavor of a prefix.
  """
  pdu_type = 4
  addr_type = rpki.ipaddrs.v4addr

class ipv6_prefix(prefix):
  """
  IPv6 flavor of a prefix.
  """
  pdu_type = 6
  addr_type = rpki.ipaddrs.v6addr

class error_report(pdu):
  """
  Error Report PDU.
  """

  pdu_type = 10

  header_struct = struct.Struct("!BBHHH")

  msgs = {
    1 : "Internal Error",
    2 : "No Data Available" }

  codes = dict((v, k) for k, v in msgs.items())

  def __init__(self, errno = None, errpdu = None, errmsg = None):
    assert errno is None or errno in self.msgs
    self.errno = errno
    self.errpdu = errpdu
    self.errmsg = errmsg if errmsg is not None or errno is None else self.msgs[errno]

  def __str__(self):
    return "Error #%s: %s" % (self.errno, self.errmsg)

  def to_pdu(self):
    """
    Generate the wire format PDU for this prefix.
    """
    if self._pdu is None:
      assert isinstance(self.errno, int)
      assert not isinstance(self.errpdu, error_report)
      p = self.errpdu
      if p is None:
        p = ""
      elif isinstance(p, pdu):
        p = p.to_pdu()
      assert isinstance(p, str)
      self._pdu = self.header_struct.pack(self.version, self.pdu_type, self.errno, len(p), len(self.errmsg))
      self._pdu += p
      self._pdu += self.errmsg.encode("utf8")
    return self._pdu

  def got_header(self, reader):
    if not reader.ready():
      return None
    version, pdu_type, self.errno, self.pdulen, self.errlen = self.header_struct.unpack(reader.buffer[:self.header_struct.size])
    return reader.update(need = self.header_struct.size + self.pdulen + self.errlen, callback = self.got_pdu)

  def got_pdu(self, reader):
    if not reader.ready():
      return None
    b = reader.get(self.header_struct.size)
    self.errpdu = reader.get(self.pdulen)
    self.errmsg = reader.get(self.errlen).decode("utf8")
    assert b + self.errpdu + self.errmsg.encode("utf8") == self.to_pdu()
    return self

prefix.afi_map = { "\x00\x01" : ipv4_prefix, "\x00\x02" : ipv6_prefix }

pdu.pdu_map = dict((p.pdu_type, p) for p in (ipv4_prefix, ipv6_prefix, serial_notify, serial_query, reset_query,
                                             cache_response, end_of_data, cache_reset, error_report))

class prefix_set(list):
  """
  Object representing a set of prefixes, that is, one versioned and
  (theoretically) consistant set of prefixes extracted from rcynic's
  output.
  """

  @classmethod
  def _load_file(cls, filename):
    """
    Low-level method to read prefix_set from a file.
    """
    self = cls()
    f = open(filename, "rb")
    r = read_buffer()
    while True:
      p = pdu.read_pdu(r)
      while p is None:
        b = f.read(r.needed())
        if b == "":
          assert r.available() == 0
          return self
        r.put(b)
        p = r.retry()
      self.append(p)

class axfr_set(prefix_set):
  """
  Object representing a complete set of prefixes, that is, one
  versioned and (theoretically) consistant set of prefixes extracted
  from rcynic's output, all with the announce field set.
  """

  @classmethod
  def parse_rcynic(cls, rcynic_dir):
    """
    Parse ROAS fetched (and validated!) by rcynic to create a new
    axfr_set.
    """
    self = cls()
    self.serial = rpki.sundial.now().totimestamp()
    for root, dirs, files in os.walk(rcynic_dir):
      for f in files:
        if f.endswith(".roa"):
          roa = rpki.x509.ROA(DER_file = os.path.join(root, f)).extract().get()
          assert roa[0] == 0, "ROA version is %d, expected 0" % roa[0]
          asnum = roa[1]
          for afi, addrs in roa[2]:
            for addr in addrs:
              self.append(prefix.afi_map[afi].from_asn1(asnum, addr))
    self.sort()
    for i in xrange(len(self) - 2, -1, -1):
      if self[i] == self[i + 1]:
        del self[i + 1]
    return self

  @classmethod
  def load(cls, filename):
    """
    Load an axfr_set from a file, parse filename to obtain serial.
    """
    fn1, fn2 = os.path.basename(filename).split(".")
    assert fn1.isdigit() and fn2 == "ax"
    self = cls._load_file(filename)
    self.serial = int(fn1)
    return self

  def filename(self):
    """
    Generate filename for this axfr_set.
    """
    return "%d.ax" % self.serial

  def save_axfr(self):
    """
    Write axfr__set to file with magic filename.
    """
    f = open(self.filename(), "wb")
    for p in self:
      f.write(p.to_pdu())
    f.close()

  def mark_current(self):
    """
    Mark the current serial number as current.
    """
    tmpfn = "current.%d.tmp" % os.getpid()
    try:
      f = open(tmpfn, "w")
      f.write("%d\n" % self.serial)
      f.close()
      os.rename(tmpfn, "current")
    except:
      os.unlink(tmpfn)
      raise

  def save_ixfr(self, other):
    """
    Comparing this axfr_set with an older one and write the resulting
    ixfr_set to file with magic filename.  Since we store prefix_sets
    in sorted order, computing the difference is a trivial linear
    comparison.
    """
    f = open("%d.ix.%d" % (self.serial, other.serial), "wb")
    old = other[:]
    new = self[:]
    while old and new:
      if old[0] < new[0]:
        f.write(old.pop(0).to_pdu(announce = 0))
      elif old[0] > new[0]:
        f.write(new.pop(0).to_pdu(announce = 1))
      else:
        del old[0]
        del new[0]
    while old:
      f.write(old.pop(0).to_pdu(announce = 0))
    while new:
      f.write(new.pop(0).to_pdu(announce = 1))
    f.close()

  def show(self):
    """
    Print this axfr_set.
    """
    print "# AXFR %d (%s)" % (self.serial, rpki.sundial.datetime.utcfromtimestamp(self.serial))
    for p in self:
      print p

class ixfr_set(prefix_set):
  """
  Object representing an incremental set of prefixes, that is, the
  differences between one versioned and (theoretically) consistant set
  of prefixes extracted from rcynic's output and another, with the
  announce fields set or cleared as necessary to indicate the changes.
  """

  @classmethod
  def load(cls, filename):
    """
    Load an ixfr_set from a file, parse filename to obtain serials.
    """
    fn1, fn2, fn3 = os.path.basename(filename).split(".")
    assert fn1.isdigit() and fn2 == "ix" and fn3.isdigit()
    self = cls._load_file(filename)
    self.from_serial = int(fn3)
    self.to_serial = int(fn1)
    return self

  def filename(self):
    """
    Generate filename for this ixfr_set.
    """
    return "%d.ix.%d" % (self.to_serial, self.from_serial)

  def show(self):
    """
    Print this ixfr_set.
    """
    print "# IXFR %d (%s) -> %d (%s)" % (self.from_serial, rpki.sundial.datetime.utcfromtimestamp(self.from_serial),
                                         self.to_serial, rpki.sundial.datetime.utcfromtimestamp(self.to_serial))
    for p in self:
      print p

class file_producer(object):
  """
  File-based producer object for asynchat.
  """

  def __init__(self, handle, buffersize):
    self.handle = handle
    self.buffersize = buffersize

  def more(self):
    return self.handle.read(self.buffersize)

class pdu_channel(asynchat.async_chat):
  """
  asynchat subclass that understands our PDUs.  This just handles
  network I/O.  Specific engines (client, server) should be subclasses
  of this with methods that do something useful with the resulting
  PDUs.
  """

  def __init__(self, conn = None):
    asynchat.async_chat.__init__(self, conn)
    self.reader = read_buffer()

  def start_new_pdu(self):
    """
    Start read of a new PDU.
    """
    p = pdu.read_pdu(self.reader)
    while p is not None:
      self.deliver_pdu(p)
      p = pdu.read_pdu(self.reader)
    assert not self.reader.ready()
    self.set_terminator(self.reader.needed())

  def collect_incoming_data(self, data):
    """
    Collect data into the read buffer.
    """
    self.reader.put(data)
    
  def found_terminator(self):
    """
    Got requested data, see if we now have a PDU.  If so, pass it
    along, then restart cycle for a new PDU.
    """
    p = self.reader.retry()
    if p is None:
      self.set_terminator(self.reader.needed())
    else:
      self.deliver_pdu(p)
      self.start_new_pdu()

  def push_pdu(self, pdu):
    """
    Write PDU to stream.
    """
    self.push(pdu.to_pdu())

  def push_file(self, f):
    """
    Write content of a file to stream.
    """
    self.push_with_producer(file_producer(f, self.ac_out_buffer_size))

  def log(self, msg):
    """
    Intercept asyncore's logging.
    """
    log(msg)

  def log_info(self, msg, tag = "info"):
    """
    Intercept asynchat's logging.
    """
    log("asynchat: %s: %s" % (tag, msg))

  def handle_error(self):
    """
    Handle errors caught by asyncore main loop.
    """
    log(traceback.format_exc())
    log("Exiting after unhandled exception")
    asyncore.close_all()

  def init_file_dispatcher(self, fd):
    """
    Kludge to plug asyncore.file_dispatcher into asynchat.  Call from
    subclass's __init__() method, after calling
    pdu_channel.__init__(), and don't read this on a full stomach.
    """
    self.connected = True
    self._fileno = fd
    self.socket = asyncore.file_wrapper(fd)
    self.add_channel()
    flags = fcntl.fcntl(fd, fcntl.F_GETFL, 0)
    flags = flags | os.O_NONBLOCK
    fcntl.fcntl(fd, fcntl.F_SETFL, flags)

class server_write_channel(pdu_channel):
  """
  Kludge to deal with ssh's habit of sometimes (compile time option)
  invoking us with two unidirectional pipes instead of one
  bidirectional socketpair.  All the server logic is in the
  server_channel class, this class just deals with sending the
  server's output to a different file descriptor.
  """

  def __init__(self):
    """
    Set up stdout.
    """
    pdu_channel.__init__(self)
    self.init_file_dispatcher(sys.stdout.fileno())

  def readable(self):
    """
    This channel is never readable.
    """
    return False

class server_channel(pdu_channel):
  """
  Server protocol engine, handles upcalls from pdu_channel to
  implement protocol logic.
  """

  def __init__(self):
    """
    Set up stdin and stdout as connection and start listening for
    first PDU.
    """
    pdu_channel.__init__(self)
    self.init_file_dispatcher(sys.stdin.fileno())
    self.writer = server_write_channel()
    self.get_serial()
    self.start_new_pdu()

  def writable(self):
    """
    This channel is never writable.
    """
    return False

  def push(self, data):
    """
    Redirect to writer channel.
    """
    return self.writer.push(data)

  def push_with_producer(self, producer):
    """
    Redirect to writer channel.
    """
    return self.writer.push_with_producer(producer)

  def push_pdu(self, pdu):
    """
    Redirect to writer channel.
    """
    return self.writer.push_pdu(pdu)

  def push_file(self, f):
    """
    Redirect to writer channel.
    """
    return self.writer.push_file(f)

  def deliver_pdu(self, pdu):
    """
    Handle received PDU.
    """
    pdu.serve(self)

  def handle_close(self):
    """
    Intercept close event so we can shut down other sockets.
    """
    asynchat.async_chat.handle_close(self)
    asyncore.close_all()

  def get_serial(self):
    """
    Read, cache, and return current serial number, or None if we can't
    find the serial number file.  The latter condition should never
    happen, but maybe we got started in server mode while the cronjob
    mode instance is still building its database.
    """
    try:
      f = open("current", "r")
      self.current_serial = f.read().strip()
      assert self.current_serial.isdigit()
      f.close()
    except IOError:
      self.current_serial = None
    return self.current_serial

  def check_serial(self):
    """
    Check for a new serial number.
    """
    old_serial = self.current_serial
    return old_serial != self.get_serial()

  def notify(self, data = None):
    """
    Cronjob instance kicked us, send a notify message.
    """
    if self.check_serial():
      self.push_pdu(serial_notify(serial = self.current_serial))
    else:
      log("Cronjob kicked me without a valid current serial number")

class client_channel(pdu_channel):
  """
  Client protocol engine, handles upcalls from pdu_channel.
  """

  current_serial = None

  timer = None

  def __init__(self, sock, proc, killsig):
    self.killsig = killsig
    self.proc = proc
    pdu_channel.__init__(self, conn = sock)
    self.start_new_pdu()

  @classmethod
  def ssh(cls, host, port):
    """
    Set up ssh connection and start listening for first PDU.
    """
    args = ("ssh", "-p", port, "-s", host, "rpki-rtr")
    log("[Running ssh: %s]" % " ".join(args))
    s = socket.socketpair()
    return cls(sock = s[1],
               proc = subprocess.Popen(args, executable = "/usr/bin/ssh", stdin = s[0], stdout = s[0], close_fds = True),
               killsig = signal.SIGKILL)

  @classmethod
  def tcp(cls, host, port):
    """
    Set up TCP connection and start listening for first PDU.
    """
    log("[Starting raw TCP connection to %s:%s]" % (host, port))
    s = socket.socket()
    s.connect((host, int(port)))
    return cls(sock = s, proc = None, killsig = None)

  @classmethod
  def loopback(cls):
    """
    Set up loopback connection and start listening for first PDU.
    """
    s = socket.socketpair()
    log("[Using direct subprocess kludge for testing]")
    return cls(sock = s[1],
               proc = subprocess.Popen(("/usr/local/bin/python", "rtr-origin.py", "--server"), stdin = s[0], stdout = s[0], close_fds = True),
               killsig = signal.SIGINT)

  def deliver_pdu(self, pdu):
    """
    Handle received PDU.
    """
    pdu.consume(self)

  def push_pdu(self, pdu):
    """
    Log outbound PDU then write it to stream.
    """
    log(pdu)
    pdu_channel.push_pdu(self, pdu)

  def cleanup(self):
    """
    Force clean up this client's child process.  If everything goes
    well, child will have exited already before this method is called,
    but we may need to whack it with a stick if something breaks.
    """
    if self.timer is not None:
      self.timer.cancel()
    if self.proc is not None and self.proc.returncode is None:
      try:
        os.kill(self.proc.pid, self.killsig)
      except OSError:
        pass

  def handle_close(self):
    """
    Intercept close event so we can log it, then shut down.
    """
    log("Server closed channel")
    rpki.async.exit_event_loop()

class kickme_channel(asyncore.dispatcher):
  """
  asyncore dispatcher for the PF_UNIX socket that cronjob mode uses to
  kick servers when it's time to send notify PDUs to clients.
  """

  def __init__(self, server):
    asyncore.dispatcher.__init__(self)
    self.server = server
    self.sockname = "%s.%d" % (kickme_base, os.getpid())
    self.create_socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
      self.bind(self.sockname)
      os.chmod(self.sockname, 0660)
    except socket.error, e:
      log("Couldn't bind() kickme socket: %r" % e)
      self.close()
    except OSError, e:
      log("Couldn't chmod() kickme socket: %r" % e)

  def writable(self):
    """
    This socket is read-only, never writable.
    """
    return False

  def handle_connect(self):
    """
    Ignore connect events (not very useful on datagram socket).
    """
    pass

  def handle_read(self):
    """
    Handle receipt of a datagram.
    """
    data = self.recv(512)
    self.server.notify(data)

  def cleanup(self):
    """
    Clean up this dispatcher's socket.
    """
    self.close()
    try:
      os.unlink(self.sockname)
    except:
      pass

  def log(self, msg):
    """
    Intercept asyncore's logging.
    """
    log(msg)

  def log_info(self, msg, tag = "info"):
    """
    Intercept asyncore's logging.
    """
    log("asyncore: %s: %s" % (tag, msg))

  def handle_error(self):
    """
    Handle errors caught by asyncore main loop.
    """
    log(traceback.format_exc())
    log("Exiting after unhandled exception")
    asyncore.close_all()

def cronjob_main(argv):
  """
  Run this mode right after rcynic to do the real work of groveling
  through the ROAs that rcynic collects and translating that data into
  the form used in the rpki-router protocol.  This mode prepares both
  full dumps (AXFR) and incremental dumps against a specific prior
  version (IXFR).  [Terminology here borrowed from DNS, as is much of
  the protocol design.]  Finally, this mode kicks any active servers,
  so that they can notify their clients that a new version is
  available.

  Run this in the directory where you want to write its output files,
  which should also be the directory in which you run this program in
  --server mode.

  This mode takes one argument on the command line, which specifies
  the directory name of rcynic's authenticated output tree (normally
  $somewhere/rcynic-data/authenticated/).
  """

  if len(argv) != 1:
    usage("Expected one argument, got %r" % (argv,))

  old_ixfrs = glob.glob("*.ix.*")

  cutoff = rpki.sundial.now() - rpki.sundial.timedelta(days = 1)
  for f in glob.iglob("*.ax"):
    t = rpki.sundial.datetime.utcfromtimestamp(os.stat(f).st_mtime)
    if  t < cutoff:
      print "# Deleting old file %s, timestamp %s" % (f, t)
      os.unlink(f)
  
  pdus = axfr_set.parse_rcynic(argv[0])
  pdus.save_axfr()
  for axfr in glob.iglob("*.ax"):
    if axfr != pdus.filename():
      pdus.save_ixfr(axfr_set.load(axfr))
  pdus.mark_current()

  print "# New serial is %s" % pdus.serial

  try:
    os.stat(kickme_dir)
  except OSError:
    print '# Creating directory "%s"' % kickme_dir
    os.makedirs(kickme_dir)

  msg = "Good morning, serial %s is ready" % pdus.serial
  sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
  for name in glob.iglob("%s.*" % kickme_base):
    try:
      print "# Kicking %s" % name
      sock.sendto(msg, name)
    except:
      print "# Failed to kick %s" % name
  sock.close()

  old_ixfrs.sort()
  for ixfr in old_ixfrs:
    print "# Deleting old file %s" % ixfr
    os.unlink(ixfr)

def show_main(argv):
  """
  Display dumps created by --cronjob mode in textual form.
  Intended only for debugging.

  This mode takes no command line arguments.  Run it in the directory
  where you ran --cronjob mode.
  """

  if argv:
    usage("Unexpected arguments: %r" % (argv,))

  g = glob.glob("*.ax")
  g.sort()
  for f in g:
    axfr_set.load(f).show()

  g = glob.glob("*.ix.*")
  g.sort()
  for f in g:
    ixfr_set.load(f).show()

def server_main(argv):
  """
  Implement the server side of the rpkk-router protocol.  Other than
  one PF_UNIX socket inode, this doesn't write anything to disk, so it
  can be run with minimal privileges.  Most of the hard work has
  already been done in --cronjob mode, so all that this mode has to do
  is serve up the results.

  In production use this server is run under sshd.  The subsystem
  mechanism in sshd does not allow us to pass arguments on the command
  line, so either we need a wrapper or we need wired-in names for
  things like our config file.  sshd will have us running in whatever
  it thinks is our home directory on startup, so it may be that the
  easiest approach here is to let sshd put us in the right directory
  and just look for our config file there.

  This mode takes no arguments.  Run it in the directory where you ran
  --cronjob mode.

  The server is event driven, so everything interesting happens in the
  channel classes.
  """

  log("[Starting]")
  if argv:
    usage("Unexpected arguments: %r" % (argv,))
  kickme = None
  try:
    server = server_channel()
    kickme = kickme_channel(server = server)
    rpki.async.event_loop()
  finally:
    if kickme is not None:
      kickme.cleanup()

class client_timer(rpki.async.timer):
  """
  Timer class for client mode, to handle the periodic serial queries.
  """

  def __init__(self, client, period):
    rpki.async.timer.__init__(self)
    self.client = client
    self.period = period
    self.set(period)

  def handler(self):
    if self.client.current_serial is None:
      self.client.push_pdu(reset_query())
    else:
      self.client.push_pdu(serial_query(serial = self.client.current_serial))
    self.set(self.period)

def client_main(argv):
  """
  Toy client, intended only for debugging.

  This program takes one or more arguments.  The first argument
  determines what kind of connection it should open to the server, the
  remaining arguments are connection details specific to this
  particular type of connection.

  If the first argument is "loopback", the client will run a copy of
  the server directly in a subprocess, and communicate with it via a
  PF_UNIX socket pair.  This sub-mode takes no further arguments.

  If the first argument is "ssh", the client will attempt to run ssh
  in as subprocess to connect to the server using the ssh subsystem
  mechanism as specified for this protocol.  The remaining arguments
  should be a hostname (or IP address in a form acceptable to ssh) and
  a TCP port number.

  If the first argument is "tcp", the client will attempt to open a
  direct (and completely insecure!) TCP connection to the server.
  The remaining arguments should be a hostname (or IP address) and
  a TCP port number.
  """

  log("[Startup]")
  client = None
  try:
    if not argv or (argv[0] == "loopback" and len(argv) == 1):
      client = client_channel.loopback()
    elif argv[0] == "ssh" and len(argv) == 3:
      client = client_channel.ssh(*argv[1:])
    elif argv[0] == "tcp" and len(argv) == 3:
      client = client_channel.tcp(*argv[1:])
    else:
      usage("Unexpected arguments: %r" % (argv,))
    client.push_pdu(reset_query())
    client.timer = client_timer(client, rpki.sundial.timedelta(minutes = 10))
    rpki.async.event_loop()
  finally:
    if client is not None:
      client.cleanup()

def log(msg):
  rpki.log.warn(str(msg))

os.environ["TZ"] = "UTC"
time.tzset()

cfg_file = "rtr-origin.conf"

mode = None

kickme_dir  = "sockets"
kickme_base = os.path.join(kickme_dir, "kickme")

main_dispatch = {
  "cronjob" : cronjob_main,
  "client"  : client_main,
  "server"  : server_main,
  "show"    : show_main }

def usage(error = None):
  print "Usage: %s --mode [arguments]" % sys.argv[0]
  print
  print "where --mode is one of:"
  print
  for name, func in main_dispatch.iteritems():
    print "--%s:" % name
    print func.__doc__
  if isinstance(error, str):
    sys.exit("Error: %s" % error)
  else:
    sys.exit(error)

opts, argv = getopt.getopt(sys.argv[1:], "c:h?", ["config=", "help"] + main_dispatch.keys())
for o, a in opts:
  if o in ("-h", "--help", "-?"):
    usage()
  if o in ("-c", "--config"):
    cfg_file = a
  if len(o) > 2 and o[2:] in main_dispatch:
    if mode is not None:
      usage("Conflicting modes specified")
    mode = o[2:]

if mode is None:
  usage("No mode specified")

tag = mode

rpki.log.use_syslog = mode in ("cronjob", "server")

if mode == "server":
  #
  # Try to figure out peer address when we're in server mode.
  try:
    tag += "/tcp/" + str(socket.fromfd(0, socket.AF_INET, socket.SOCK_STREAM).getpeername()[0])
  except (socket.error, IndexError):
    if os.getenv("SSH_CONNECTION"):
      tag += "/ssh/" + os.getenv("SSH_CONNECTION").split()[0]

rpki.log.init("rtr-origin/" + tag, syslog.LOG_PID)

cfg = rpki.config.parser(cfg_file, "mode", allow_missing = True)

main_dispatch[mode](argv)