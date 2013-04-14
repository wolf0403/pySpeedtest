#!/usr/bin/env python

import json, random, sys
import threading
from random import randint
from math import fsum
from datetime import datetime as dt

import asynchttp as ah

# Script was inspired by
# http://tech.ivkin.net/wiki/Run_Speedtest_from_command_line

DEBUG=False

def chop_results (a, lower=0.3, higher=0.1):
	'a should be a sorted list of speeds'
	n = len(a)
	return a[int(lower * n):(n - int(higher * n))]	

ladd = lambda x,y: x+y

def timeit (urls, sharedCounter=None):
	'''
	returns: m, t, s, c
	m: [ (size, time, speed), ...] aggregated from all threads, list
	t: overall wall time from starting all threads until finish, float
	s: [ total_bytes, ... ] from all threads, list of ints
	c: shared or list
	'''
	assert isinstance(urls, list)
	assert len(urls) > 0
	try:
		r = ah.multi_get (urls, sharedCounter=sharedCounter)
		if sharedCounter is not None:
			assert r[3] == sharedCounter
		return r
	except:
		import traceback
		print traceback.format_exc ()

def latency (url, repeat=10):
	urls = [ [e % randint(1000000000000, 2000000000000)] for e in [url + 'latency.txt?x=%d'] * repeat ]
	m = timeit(urls)[0]
	times = [e[1] for e in filter(lambda t:t[4], m)] # find all full intervals
	if len(times) == 0:
		times = [e[1] for e in filter(lambda t:t[2]>0, m)] # fallback to non-0 spee
	
	if DEBUG:
		print times
	#return min (times) # min, according to Speedtest wiki
	return fsum(times) / len(times) # average, according to IMC'12 paper

def __dump (l):
	from pprint import pprint
	pprint (l, indent=4)

def download (server, imgindexlist = [1, 3], conns = [2, 4]):
	def randimgs(imgindexs=range(1,9)):
		for i in imgindexs:
			n = 500 * i
			yield ("random%dx%d.jpg" % (n, n), "?x=%d" % (randint(1000000000000, 2000000000000)))
	# print "Testing against %s" % server
	imgs = list (randimgs(imgindexlist))
	
	#print "Creating {:d} url lists".format(conns[-1])
	#urls = [[] for i in range(conns[-1])] # we need most # connections
	
	allrecs = []
	counter = ah.Counter ()
	
	for i in range (len(imgs)):
		#print i, conns[i]
		urls = [[] for j in range(conns[i])]
		for conn in range(conns[i]):
			#print ' - ', i, conn
			urls[conn].append (server + ''.join(imgs[i]) + '&y=' + str(conn))
		m, t, s, c = timeit (urls, sharedCounter=counter)
		assert (c == counter)
		assert len(m) == len(c.records)
		if DEBUG:
			report_results (m, t, s, ''.join(imgs[i]))
		#allrecs.extend (m) # shared counter does this accumulation
		allrecs = m
	m = allrecs
	assert len(m) == len(counter.records)

	if DEBUG:
		report_results (m, t, s, "RAW")
	m = chop_results (allrecs)
	if DEBUG:
		report_results (m, t, s, "CHOP")

	totalsize = fsum ([t[0] for t in m])
	totaltime = fsum ([t[1] for t in m])
	return totalsize / totaltime

def print_speed (s, fmt = "%.2f %s", bps=False):
	unit = ''
	if s > 1024:
		unit = 'K'
		if s > 1024:
			unit = 'M'
			s /= 1024
		s /= 1024
	if bps:
		s *= 8
		unit += 'bps'
	else:
		unit += 'Bytes/sec'
	return fmt % (s, unit)

def ps (size, secs):
	return print_speed (size / secs)

import pprint
pp = pprint.PrettyPrinter(indent=4)

def report_results (matrics, time, sizes, prefix='', simple=True):
	assert len(matrics) > 0
	t = time.total_seconds()
	size = reduce (ladd, [x[0] for x in matrics])
	tsum = fsum ([x[1] for x in matrics])
	speed = size / t

	if not simple:
		print "{}: #Records: {:,d}".format (prefix, len(matrics))
		print "{}: Wall time returned: ".format(prefix), t
		print "{}: Wall time accmulated: ".format(prefix), tsum

	print "{}: {:,d} bytes / {:,f} secs = {}".format(prefix, size, tsum, print_speed(speed))
	return speed

def __test__():
	urls = ['http://api.mspeedapp.com/1M.dat'] * 2

	
	m, t, sizes, c = ah.multi_get (urls)
	print t

	report_results (m, t, sizes, "RAW")
	m = chop_results (m)
	report_results (m, t, sizes, "CHOP")

	sys.exit(0)
	#s = [ fsum(l) / len(l) for l in map (lambda l: chop_results(l), m) ]
	#s = [ fsum(l) / len(l) for l in map (lambda l: chop_results(l), m) ]
	s = [ fsum(l) / (len(l)) for l in m ]
	print map (print_speed, s)
	print print_speed (fsum(s))

if __name__ == '__main__':
	if len(sys.argv) < 2:
		print >>sys.stderr, "%s <url>" % sys.argv[0]
		print >>sys.stderr, "%s <CC> <Company> <Name>" % sys.argv[0]
		sys.exit (1)
	if len(sys.argv) == 2:
		url = sys.argv[1]
		
	do_latency = True
	if do_latency:
		latency_sec = latency (url)
		print "Lantency: {:.2f} ms".format(latency_sec * 1000)
	do_download = True
	if do_download:
		avg_speed = download (url)
		#avg_speed = reduce (lambda x, y: x + y, speed.values()) / len(speed)
		print "Speed: ", print_speed (avg_speed, bps=True)
	