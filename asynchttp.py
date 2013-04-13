#!/usr/bin/env python

import asyncore
import string, socket
import StringIO
import mimetools, urlparse
from datetime import datetime, timedelta

# from http://effbot.org/librarybook/asyncore.htm

class Counter(object):
	def __init__(self, interval=0.1):
		self.told = datetime.now()
		self.delta = timedelta (0, interval, 0)
		self.size = 0
		self.total_size = 0
		self._records = []
	def start (self):
		self.told = datetime.now()

	def add (self, size):
		t = datetime.now()
		self.total_size += size
		delta = t - self.told
		if delta < self.delta:
			self.size += size
			return ()
		else:
			secs = delta.total_seconds()
			rec = (self.size + size, secs, self.size / secs)
			self._records.append (rec)
			
			self.told = t
			self.size = 0
			return rec

	@property
	def records(self):
		return self._records

class AsyncHTTP(asyncore.dispatcher_with_send):
	# HTTP requestor

	def __init__(self, uri, consumer):
		asyncore.dispatcher_with_send.__init__(self)

		self.uri = uri
		self.consumer = consumer

		# turn the uri into a valid request
		scheme, host, path, params, query, fragment = urlparse.urlparse(uri)
		assert scheme == "http", "only supports HTTP requests"
		try:
			host, port = string.split(host, ":", 1)
			port = int(port)
		except (TypeError, ValueError):
			port = 80 # default port
		if not path:
			path = "/"
		if params:
			path = path + ";" + params
		if query:
			path = path + "?" + query

		self.request = "GET %s HTTP/1.0\r\nHost: %s\r\n\r\n" % (path, host)

		self.host = host
		self.port = port

		self.status = None
		self.header = None
		self.clen = -1
		self.closeconn = False

		self.data = ""
		self.counter = Counter()

		# get things going!
		self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
		self.connect((host, port))

	def handle_connect(self):
		# connection succeeded
		self.send(self.request)
		#self.counter = Counter()

	def handle_expt(self):
		# connection failed; notify consumer (status is None)
		self.close()
		try:
			http_header = self.consumer.http_header
		except AttributeError:
			pass
		else:
			http_header(self)

	def handle_read(self):
		data = self.recv(2048)
		self.counter.add(len(data))
		if not self.header:
			self.data = self.data + data
			try:
				i = string.index(self.data, "\r\n\r\n")
			except ValueError:
				return # continue
			else:
				# parse header
				fp = StringIO.StringIO(self.data[:i+4])
				# status line is "HTTP/version status message"
				status = fp.readline()
				self.status = string.split(status, " ", 2)
				# followed by a rfc822-style message header
				self.header = mimetools.Message(fp)
				if 'content-length' in self.header:
					self.clen = int(self.header['content-length'])
					print 'CLEN: ', self.clen
				#if 'connection' in self.header:
					#if self.header['connection'].lower().startswith('close'):
						#self.closeconn = True
				# followed by a newline, and the payload (if any)
				data = self.data[i+4:]
				self.data = ""
				# notify consumer (status is non-zero)
				try:
					http_header = self.consumer.http_header
				except AttributeError:
					pass
				else:
					http_header(self)
				if not self.connected:
					return # channel was closed by consumer
		datalen = len(data)
		if self.clen <= datalen:
			self.consumer.feed(data, self.clen)
			self.clen = -1
			self.header = None
			self.data = data[self.clen:]
			if self.closeconn:
				assert self.clen == datalen
				self.consumer.close()
				self.close()
		else:
			self.consumer.feed(data, datalen)
			self.clen = self.clen - datalen 
			assert self.clen > 0

	def handle_close(self):
		self.consumer.close()
		self.close()
		
class DummyConsumer:
	size = 0

	def http_header(self, request):
		# handle header
		if request.status is None:
			print "connection failed"
		else:
			pass
			#print "status", "=>", request.status
			#for key, value in request.header.items():
				#print key, "=", value

	def feed(self, data, datalen):
		# handle incoming data
		#self.size = self.size + len(data)
		self.size += datalen

	def close(self):
		# end of data
		#print self.size, "bytes in body"
		pass

def _multi_get (urls):
	requests = []
	consumers = []
	for url in urls:
		consumer = DummyConsumer()
		requests.append (AsyncHTTP(
			url,
			consumer
		))
		consumers.append (consumer)
	asyncore.loop()
	return requests, consumers

def multi_get (urls, contentOnly=False):
	'''
	returns: m, t, s
	m: [ (size, time, speed), ...] aggregated from all threads, list
	t: overall wall time from starting all threads until finish, timedelta
	s: [ total_bytes, ... ] from all threads, list of ints
	'''
	tstart = datetime.now()
	rs, cs = _multi_get (urls)
	tend = datetime.now()
	t = tend - tstart
	ladd = lambda x,y:x+y
	m = reduce (ladd, [r.counter.records for r in rs])
	if contentOnly:
		s = [c.counter.total_size for c in cs]
	else:
		s = [c.size for c in cs]
	return m, t, s

def print_speed (s, fmt = "%.2f %s"):
	unit = "Bytes/sec"
	if s > 1024:
		unit = "KBytes/sec"
		if s > 1024:
			unit = "MBytes/sec"
			s /= 1024
		s /= 1024
	return fmt % (s, unit)

def ps (size, secs):
	return print_speed (size / secs)
	
if __name__ == '__main__':
	import sys
	if len(sys.argv) <= 1:
		raise ('{} <url>'.format(sys.argv[0]))
		sys.exit(1)

	m, t, s = multi_get (sys.argv[1:])
	print m
	print t
	print s
	sys.exit (0)
	from speedtest import report_results

	print t.total_seconds()

	report_results (m, t, s, "RAW")
	m = chop_results (m)
	report_results (m, t, s, "CHOP")