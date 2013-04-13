#!/usr/bin/env python

# load speedtest.net serverlist XML

import sys, os, json
import requests

serverxml = './servers.xml'
serverjson = './servers.json'

def loadservers(saveXml=False):
	'''
	Load server array from either XML or JSON
	1. if saveXml, remove JSON and XML to force reload
	2. if JSON not exists, load XML from server, convert to JSON
	3. load results from JSON
	return python dict from JSON data
	'''
	jsondata = {}
	if saveXml:
		# force reload XML by removing JSON cache
		try:
			os.unlink (serverxml)
		except:
			pass
		try:
			os.unlink (serverjson)
		except:
			pass

	if not os.path.exists(serverjson):
		r = requests.get ('http://speedtest.net/speedtest-servers.php')
		if r.ok:
			with open(serverxml, 'w') as f:
				f.write (r.content)

	if os.path.exists (serverxml):
		with open(serverxml, 'r') as f, open(serverjson, 'w') as outf:
			jsondata = convert_servers (f, output=outf)
		if jsondata is not None:
			if not saveXml:
				os.unlink (serverxml)
		else:
			print >>sys.stderr, "Parse server XML list failed."
	elif os.path.exists (serverjson):
		with open(serverjson, 'r') as f:
			jsondata = json.load (f)
			if len(jsondata) == 0:
				jsondata = None
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
		url = s.attrib['url']
		ridx = url.rindex('/')
		fn = url[ridx+1:]
		url = url[:ridx + 1]

		if c not in smap:
			smap[c] = {url : dict(s.attrib)}
		else:
			if fn.startswith ('upload.'):
				smap[c][url] = (dict(s.attrib))
			else:
				print >>sys.stderr, "MISSING upload.php: ", url
	if len(smap) > 0:
		if output is not None:
			output.write (json.dumps (smap, indent=2))
		return smap
	return None
	
if __name__ == '__main__':
	if len(sys.argv) > 1: # convert given XML
		convert_servers (sys.argv[1], sys.stdout)
	else: # download server list and convert to JSON
		loadservers ('SAVE_XML' in os.environ)
