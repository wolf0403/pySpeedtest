#!/usr/bin/env python

import json, random, sys
from random import randint
from requests import get as reqs_get
from datetime import datetime as dt

# Script was inspired by
# http://tech.ivkin.net/wiki/Run_Speedtest_from_command_line

sys.path.append ('.')
from loadserver import loadservers
servers = loadservers ()

cc = 'AU'

def timeit (url):
	try:
		#print url
		t1 = dt.now()
		r = reqs_get (url)
		t2 = dt.now()
		if r.ok:
			cl = 0
			if 'content-length' in r.headers:
				cl = int(r.headers['content-length'])
			else:
				cl = len(r.content)
			return (t2 - t1, cl)
		return r
	except:
		import traceback
		print traceback.format_exc ()

def latency ():
	rmap = {}
	for i in range(3):
		for url in servers[cc]:
			r = timeit(url + 'latency.txt?x=%d' % randint(0, 10000))
			if isinstance (r, tuple):
				speed = r[1] / r[0].total_seconds()
				if url not in rmap:
					rmap[url] = []
				rmap[url].append (speed)
				#results.append ((url, speed))
			else:
				del servers[cc][url]
				print >>sys.stderr, url + ' '
				if r is not None:
					print url,
					print >>sys.stderr, "FAILED(%d): %s" % (r.status_code, r.reason)
				else:
					print >>sys.stderr, "General failure"
	results = [ (k, rmap[k]) for k in rmap ]
	# http://goo.gl/JqrZm
	return sorted (results, key=lambda t:reduce(lambda x,y:x + y, t[1]))


def download (server):
	def randimgs():
		for i in range(1,9):
			n = 500 * i
			yield "random%dx%d.jpg" % (n, n)
	results = {}
	print "Testing against %s" % server
	for img in randimgs():
		fullurl = server + "%s?x=%d" % (img, randint(0, 10000))
		reqtime, length = timeit (fullurl)
		print "%s: %d bytes, %f secs" % (img, length, reqtime.total_seconds())
		try:
			results[img] = length / reqtime.total_seconds()
		except:
			print img
	return results

def print_speed (s):
	unit = "Bytes/sec"
	if s > 1024:
		unit = "KBytes/sec"
		if s > 1024:
			unit = "MBytes/sec"
			s /= 1024
		s /= 1024
	return "%.2f %s" % (s, unit)
			
if __name__ == '__main__':
	import os
	if 'CC' in os.environ:
		cc = os.environ['CC']
	serverlist = latency ()
	speed = download (serverlist[0][0])
	avg_speed = reduce (lambda x, y: x + y, speed.values()) / len(speed)
	print print_speed (avg_speed)
	