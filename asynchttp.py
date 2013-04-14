#!/usr/bin/env python

import asyncore
import string, socket
import StringIO
import mimetools, urlparse
from datetime import datetime, timedelta

# from http://effbot.org/librarybook/asyncore.htm

DEBUG = False

class Counter(object):
	def __init__(self, interval=1/10.0):
		self.told = datetime.now()
		self.delta = timedelta (0, interval, 0)
		self.size = 0
		self._total_size = 0
		self._records = []
		self._records.append ((0, 0, 0, self.told, False))
		self.from_send = False
		if DEBUG:
			print "RECORD INTERVAL: ", self.delta
	def start (self):
		self.told = datetime.now()

	def add (self, size, lastrec=False):
		'''
		Add record: (size, time, inst speed, record time, is full interval?)
		'''
		#print "ADD, {}, {}".format(len(self.records), size)
		t = datetime.now()
		#print t
		self._total_size += size
		delta = t - self.told
		if delta >= self.delta or lastrec:
			secs = delta.total_seconds()
			rec = (self.size + size, secs, self.size / secs, t, delta >= self.delta)
			if DEBUG:
				print "ADD: ", rec
			self._records.append (rec)
			self.told = t
			self.size = 0
			return rec
		else:
			self.size += size
			return ()

	@property
	def records(self):
		return self._records
	@property
	def total_size(self):
		return self._total_size

class AsyncHTTP(asyncore.dispatcher):
	# HTTP requestor

	def __init__(self, uris, consumer, counter=None, pipelining=False):
		asyncore.dispatcher.__init__(self)
		assert isinstance(uris, list) and isinstance(uris[0], str)
		#self.uri = uri
		self.consumer = consumer
		#print "URLS: {:d}".format(len(uris))

		def build_req (uri):
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
			request = "GET %s HTTP/1.1\r\nHost: %s\r\n\r\n" % (path, host)
			return request, host, port

		#self.request = "GET %s HTTP/1.1\r\nHost: %s\r\n\r\n" % (path, host)
		self.requests = []
		hp = None
		for uri in uris:
			r, h, p = build_req (uri)
			if hp == None:
				hp = (h, p)
			else:
				assert hp == (h, p)
			self.requests.append (r)
		self.requests[-1] = self.requests[-1][:-2] + "Connection: close\r\n\r\n"
		#self.request = ''.join (self.requests)

		self.host, self.port = hp

		self.status = None
		self.header = None
		self.clen = -1
		self.closeconn = False

		self.data = ""
		if counter is not None:
			self.counter = counter
			#print 'SHARED COUNTEr'
		else:
			self.counter = Counter()
		
		self.pipelining = pipelining
		self.do_req = 0

		# get things going!
		self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
		self.connect(hp)

	def _do_one_req (self):
		if len(self.requests) > 0:
			req0 = self.requests[0]
			if req0.startswith('GET'):
				if self.do_req <= 0: # check if we're ready for next req
					#print "Wait for resp done"
					return
			#print "SENDING: {:s}, {:d} bytes".format (req0, len(req0))
			sent = self.send(req0) # return none for dispatcher_with_send
			#self.do_req -= 1
			#print "SENT: {:s} bytes".format(str(sent))
			# following for dispatcher (non-buffered write)
			if sent < len(req0):
				#print "INCOMPLETE SEND", self.requests[0][:sent]
				self.requests[0] = req0[sent:]
			else:
				self.requests = self.requests[1:]
				self.do_req = self.do_req - 1
				#print "do_req {:d}, {:d} left".format(self.do_req, len(self.requests))
			
	def handle_connect(self):
		# connection succeeded
		self.do_req = 1
		#self._do_one_req ()
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
			
	def handle_write(self):
		if self.counter.from_send:
			self.counter.start ()
		self._do_one_req ()

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
				#print "HEADER DONE", self.data[:i+4]
				fp = StringIO.StringIO(self.data[:i+4])
				# status line is "HTTP/version status message"
				status = fp.readline()
				self.status = string.split(status, " ", 2)
				if len(self.status) == 3:
					if int(self.status[1]) >= 400:
						raise Exception("Error: " + status)
				
				# followed by a rfc822-style message header
				self.header = mimetools.Message(fp)
				if 'content-length' in self.header:
					self.clen = int(self.header['content-length'])
					#print 'CLEN: ', self.clen
				if 'connection' in self.header:
					if self.header['connection'].lower().startswith('close'):
						self.closeconn = True
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
				#assert self.clen == datalen
				self.counter.add(len(data), lastrec=True)
				self.consumer.close()
				self.close()
			else:
				self.do_req += 1
				#print "do_req next ", self.do_req
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

def _multi_get (urls, sharedCounter=None):
	requests = []
	consumers = []
	counter = Counter ()
	#print urls
	if sharedCounter is not None:
		#print 'Shared counter'
		pass
	for url in urls:
		consumer = DummyConsumer()
		requests.append (AsyncHTTP(
			url,
			consumer,
			counter=sharedCounter,
			pipelining=True
		))
		consumers.append (consumer)
	asyncore.loop()
	return requests, consumers

def multi_get (urls, contentOnly=False, sharedCounter=None):
	'''
	urls = [
		[ urls for conn1 ],
		[ urls for conn2 ]
	]
	returns: m, t, s, c
	m: [ (size, time, speed), ...] aggregated from all threads, list
	t: overall wall time from starting all threads until finish, timedelta
	s: [ total_bytes, ... ] from all threads, list of ints
	c: counter, shared or list
	'''
	assert isinstance(urls, list)
	assert isinstance(urls[0], list)
	assert isinstance(urls[0][0], str)
	
	if DEBUG:
		print "{} connections, each with {} urls".format(len(urls), [len(c) for c in urls])
	tstart = datetime.now()
	rs, cs = _multi_get (urls, sharedCounter)
	tend = datetime.now()
	t = tend - tstart
	ladd = lambda x,y:x+y
	if sharedCounter is not None:
		m = sharedCounter.records
		c = sharedCounter
	else:
		m = reduce (ladd, [r.counter.records for r in rs])
		c = [ r.counter for r in rs ]
	if contentOnly:
		s = [r.counter.total_size for r in rs]
	else:
		s = [consumer.size for consumer in cs]
	return sorted (m, key=lambda e:e[3]), t, s, c

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

	#m, t, s, c = multi_get ([sys.argv[1:]]) # single socket, pipelined
	if True: # shared counter
		counter = Counter ()
		m, t, s, c = multi_get ([[e] for e in sys.argv[1:]], sharedCounter = counter)
		recs = counter.records
	else:
		counter = None
		m, t, s, counters = multi_get ([[e] for e in sys.argv[1:]]) # multi socket
		recs = None

	if recs is not None:
		print 'Start: ', recs[0][3]
		print 'Finish ', recs[-1][3]
		print 'Wall time: ', (recs[-1][3] - recs[1][3]).total_seconds()
		print 'M has {:d} recs'.format(len(m))
		from math import fsum
		times = [rec[1] for rec in recs]
		print 'fsum: {:d} records, {:f} secs'.format(len(times), fsum (times))
		#print 'reduce ', reduce (lambda x,y:x+y, times)
		for i in range(len(recs) - 1):
			assert recs[i][3] < recs[i+1][3]

	from speedtest import report_results, chop_results

	print 'Outer wall time ', t.total_seconds()

	report_results (m, t, s, "RAW")
	m = chop_results (m)
	report_results (m, t, s, "CHOP")
	