#!/usr/bin/env python

# load speedtest.net serverlist XML

import sys, os, json
import requests

serverxml = './servers.xml'
serverjson = './servers.json'

def loadservers():
	'''
	Load server array from either XML or JSON
	return python map
	'''
	jsondata = {}
	if os.path.exists (serverjson):
		with open(serverjson, 'r') as f:
			jsondata = json.load (f)
	elif not os.path.exists (serverxml):
		r = requests.get ('http://speedtest.net/speedtest-servers.php')
		if r.ok:
			with open(serverxml, 'w') as f:
				print >>f, r.content
	if os.path.exists (serverxml):
		with open(serverxml, 'r') as f, open(serverjson, 'w') as outf:
			jsondata = convert_servers (f, output=outf)
		os.unlink (serverxml)
	return jsondata

def convert_servers(src, output=None):
	from lxml import etree
	parser = etree.XMLParser ()
	tree = etree.parse (src, parser)
	root = tree.getroot()
	servers = root.getchildren()[0].getchildren() # all <server>s
	smap = {}
	for s in servers:
		c = s.attrib['cc']
		if c not in smap:
			smap[c] = {s.attrib['url'] : dict(s.attrib)}
		else:
			url = s.attrib['url']
			if url.endswith ('/upload.php'):
				url = url[:url.rindex('/') + 1]
			smap[c][url] = (dict(s.attrib))
	if output is not None:
		output.write (json.dumps (smap, indent=2))
	return smap
	
if __name__ == '__main__':
	if len(sys.argv) > 1: # convert given XML
		convert_servers (sys.argv[1], sys.stdout)
	else: # download server list and convert to JSON
		loadservers ()
