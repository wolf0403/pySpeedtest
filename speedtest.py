#!/usr/bin/env python

import json, random, sys
import requests
import threading
from random import randint
from math import fsum
from datetime import datetime as dt

# Script was inspired by
# http://tech.ivkin.net/wiki/Run_Speedtest_from_command_line
# http://lethain.com/parallel-http-requests-in-python/

import multiprocessing as mp

CHUNK_SIZE = 64 #1024 * 1

def reqs_get_thread (url, id, array, thread=True):
	hz = 100
	interval = 1.0 / hz
	interval = 0.1
	array[id] = []
	
	def go (url, interval, rarray):
		r = requests.get(url, stream=True)
		total_size = int(r.headers['content-length'])
		size = 0
		ts = 0
		told = dt.now()
		with open ("speedreport-%d.csv" % id, 'w') as logf:
			for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
				assert isinstance(chunk, str)
				size += len(chunk)
				assert isinstance(size, int)
				tnew = dt.now()
				tdelta = tnew - told
				if tdelta.total_seconds() >= interval:
					size, tdsecs, instspeed = (size, tdelta.total_seconds(), size / tdelta.total_seconds())
					rarray.append ((size, tdsecs, instspeed))
					#print "Time: %s, Size: %d" % (tdelta, size)
					print >>logf, "%s,%.2f,%s" % (size, tdsecs, print_speed (instspeed))
					told = tnew
					ts += size
					size = 0
		
		tdelta = tnew - told
		ts += size
		rarray.append ((size, tdelta.total_seconds(), size / tdelta.total_seconds()))
		print "TOTAL: ", ts
		print "T2: ", reduce (lambda x,y:x+y, [t[0] for t in rarray]), len(rarray)
		
	if thread:
		t = threading.Thread (target=go, args=(url,interval, array[id]))
		t.start ()
		return t
	else:
		go (url, interval, array[id])

def chop_results (a, lower=0.3, higher=0.1):
	'a should be a sorted list of speeds'
	n = len(a)
	return a[int(lower * n):(n - int(higher * n))]		

def reqs_get (urls, use_thread=True):
	'''
	returns: m, t, s
	m: [ (size, time, speed), ...] aggregated from all threads
	t: overall wall time from starting all threads until finish
	s: [ total_bytes, ... ] from all threads
	'''
	speed_matrics = [[]] * len(urls)
	tids = []
	t1 = dt.now()
	if use_thread:
		for i in range(len(urls)):
			url = urls[i]
			tids.append (reqs_get_thread (url, i, speed_matrics, use_thread))
		for tid in tids:
			tid.join ()
	else:
		for i in range(len(urls)):
			url = urls[i]
			reqs_get_thread (url, i, speed_matrics, use_thread)
	t2 = dt.now()
	def add (x,y):
		return (x[0] if isinstance (x, tuple) else x) + y[0]
	sizes = [reduce (lambda x,y: add(x,y), e) for e in speed_matrics]
	return reduce (lambda x,y:x+y, speed_matrics), t2 - t1, sizes
	
	
def timeit (url):
	print "%d D %s" % (len(url), url[0])
	return (0, dt.now() - dt.now(), 0)
	try:
		return reqs_get (url) # FIXME if url is a list, parallelize. 
	except:
		import traceback
		print traceback.format_exc ()

def latency (url, repeat=10, printError=True):
	results = []
	for i in range(repeat):
		r = timeit([url + 'latency.txt?x=%d' % randint(1000000000000, 2000000000000)])
		if isinstance (r, tuple):
			speed = r[2]
			results.append (speed)
		else:
			if not printError:
				break
			print >>sys.stderr, url + ' '
			if r is not None:
				print url,
				print >>sys.stderr, "FAILED(%d): %s" % (r.status_code, r.reason)
			else:
				print >>sys.stderr, "General failure"
	return sorted (results)


def download (server, imgindexlist = [3, 6], parallelnums = [2, 4]):
	def randimgs(imgindexs=range(1,9)):
		for i in imgindexs:
			n = 500 * i
			yield ("random%dx%d.jpg" % (n, n), "?x=%d" % (randint(1000000000000, 2000000000000)))
	print "Testing against %s" % server
	imgs = list (randimgs(imgindexlist))
	for i in range (len(imgs)):
		fullurl = []
		for proc in range(parallelnums[i]):
			fullurl.append (server + ''.join(imgs[i]) + '&y=' + str(proc))
		length, reqtime, avg_speed = timeit (fullurl)
		print "%s: %d bytes, %f secs" % (imgs[0], length, reqtime.total_seconds())
	return avg_speed

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

import pprint
pp = pprint.PrettyPrinter(indent=4)

def report_results (matrics, prefix=""):
	t = reduce (lambda x,y:x+y, [x[1] for x in m])
	size = reduce (lambda x,y:x+y, [x[0] for x in m])
	#pp.pprint(m)
	print "%s: #Records: %d" % (prefix, len(m))
	print "%s: %d bytes / %f secs = %s" % (prefix, size, t, ps (size, t))

# m: speed recordings of all threads aggregated [(size, time, speed), ...]
m, t, sizes = reqs_get (['http://api.mspeedapp.com/1M.dat'] * 2, False)
#m, t, sizes = reqs_get (['http://173.230.140.200:2012/xaccel/1m'] * 1)
t = t.total_seconds()
print sizes
print "OVERALL: %d bytes, %.2f secs, %s" % (reduce(lambda x,y:x+y, sizes), t, 
	ps(reduce(lambda x,y:x+y, sizes), t))
	
if 0:
	try:
		assert isinstance(m[0], tuple)
		assert len(m[0]) == 3
	except:
		print m[0]
		raise
m = sorted (m, key=lambda x:x[2]) # sort base on inst speed

report_results (m, "RAW")
m = chop_results (m)
report_results (m, "CHOP")

sys.exit(0)
#s = [ fsum(l) / len(l) for l in map (lambda l: chop_results(l), m) ]
#s = [ fsum(l) / len(l) for l in map (lambda l: chop_results(l), m) ]
s = [ fsum(l) / (len(l)) for l in m ]
print map (print_speed, s)
print print_speed (fsum(s))
sys.exit(1)
			
if __name__ == '__main__':
	if len(sys.argv) < 2:
		print >>sys.stderr, "%s <url>"
		sys.exit (1)
	url = sys.argv[1]
	timelist = latency (url)
	if len(timelist) > 0:
		print "Lantency: %d" % (timelist[0])
		speed = download (url)
		#avg_speed = reduce (lambda x, y: x + y, speed.values()) / len(speed)
		#print print_speed (avg_speed)
	