# coding: utf-8

import xml.dom.minidom

# text = """
# <GSP VER="3.2"> 
# <TM>0.260739</TM><Q>brooke</Q> 
# <PARAM name="cx" value="009671596744752298541:auhlevjhxa4" original_value="009671596744752298541:auhlevjhxa4"/> 
# <PARAM name="client" value="google-csbe" original_value="google-csbe"/> 
# <PARAM name="output" value="xml_no_dtd" original_value="xml_no_dtd"/> 
# <PARAM name="q" value="brooke" original_value="brooke"/> 
# <PARAM name="adkw" value="AELymgXOPVSsTIIMdmVvhljS56GNCEE-BCSmMK029rJFX8CKkNkFTkwKv759gaqhlqKJ3lEslG-APD4-EqPNNhuImyPvtPqY4Cttx2XErG91qLlUdWh3BzY" original_value="AELymgXOPVSsTIIMdmVvhljS56GNCEE-BCSmMK029rJFX8CKkNkFTkwKv759gaqhlqKJ3lEslG-APD4-EqPNNhuImyPvtPqY4Cttx2XErG91qLlUdWh3BzY"/> 
# <PARAM name="hl" value="en" original_value="en"/> 
# <PARAM name="oe" value="UTF-8" original_value="UTF-8"/> 
# <PARAM name="ie" value="UTF-8" original_value="UTF-8"/> 
# <PARAM name="boostcse" value="0" original_value="0"/> 
# <Context><title>RIABiz Search</title></Context><RES SN="1" EN="10"> 
# <M>292</M> 
# <NB><NU>/custom?q=brooke&amp;hl=en&amp;safe=off&amp;client=google-csbe&amp;cx=009671596744752298541:auhlevjhxa4&amp;boostcse=0&amp;output=xml_no_dtd&amp;ie=UTF-8&amp;oe=UTF-8&amp;start=10&amp;sa=N</NU> 
# </NB> 
#  
# <RG START="1" SIZE="10"></RG><RG START="1" SIZE="1"></RG><R N="1"><U>http://www.riabiz.com/</U><UE>http://www.riabiz.com/</UE><T>RIABiz</T><RK>0</RK><S>&lt;b&gt;Brooke&amp;#39;s&lt;/b&gt; Note: When people climb Mt. Everest today, it is a great feat, &lt;b&gt;.....&lt;/b&gt; &lt;br&gt;  &lt;b&gt;Brooke&amp;#39;s&lt;/b&gt; note: When we started RIABiz, we hoped to write stories that not only &lt;br&gt;  &lt;b&gt;...&lt;/b&gt;</S><LANG>en</LANG><Label>_cse_auhlevjhxa4</Label><HAS><L/><C SZ="109k" CID="TuSI8OGrJSYJ"/><RT/></HAS></R> 
# <RG START="2" SIZE="1"></RG><R N="2"><U>http://www.riabiz.com/about</U><UE>http://www.riabiz.com/about</UE><T>RIABiz | about</T><RK>0</RK><S>3 Aug 2009 &lt;b&gt;...&lt;/b&gt; &lt;b&gt;Brooke&lt;/b&gt; and I have been friends since our jobs back at a small paper &lt;b&gt;...&lt;/b&gt; On a &lt;br&gt;  personal note, I have worked closely with &lt;b&gt;Brooke&lt;/b&gt; Southall for &lt;b&gt;...&lt;/b&gt;</S><LANG>en</LANG><Label>_cse_auhlevjhxa4</Label><HAS><L/><C SZ="20k" CID="X1y_LaiSQw0J"/><RT/></HAS></R> 
# <RG START="3" SIZE="1"></RG><R N="3"><U>http://www.riabiz.com/a/8051</U><UE>http://www.riabiz.com/a/8051</UE><T>RIABiz | Welcome to RIABiz on day one</T><RK>0</RK><S>“As a professional in the RIA space, I&amp;#39;ve relied on &lt;b&gt;Brooke&amp;#39;s&lt;/b&gt; articles over the &lt;br&gt;  years &lt;b&gt;...&lt;/b&gt; Good luck &lt;b&gt;Brooke&lt;/b&gt;! I&amp;#39;m looking forward to reading your publication. &lt;b&gt;...&lt;/b&gt;</S><LANG>en</LANG><Label>_cse_auhlevjhxa4</Label><HAS><L/><C SZ="35k" CID="Cx2vq5NG5zUJ"/><RT/></HAS></R> 
# <RG START="4" SIZE="1"></RG><R N="4"><U>http://www.riabiz.com/a/69007</U><UE>http://www.riabiz.com/a/69007</UE><T>RIABiz | 10 reasons why Schwab&amp;#39;s move into ETFs may be an even &lt;b&gt;...&lt;/b&gt;</T><RK>0</RK><S>Wednesday 11/4/09 by &lt;b&gt;Brooke&lt;/b&gt; Southall tags: Schwab | ETFs | Barclays Global &lt;br&gt;  Investors. Charles Schwab &amp;amp; Co. thundered into the exchange traded fund business &lt;br&gt;  &lt;b&gt;...&lt;/b&gt;</S><LANG>en</LANG><Label>_cse_auhlevjhxa4</Label><HAS><L/><C SZ="31k" CID="QFkYgZDLvuYJ"/><RT/></HAS></R> 
# <RG START="5" SIZE="1"></RG><R N="5"><U>http://www.riabiz.com/a/83136</U><UE>http://www.riabiz.com/a/83136</UE><T>RIABiz | Taking A Break From the Turkey?</T><RK>0</RK><S>26 Nov 2009 &lt;b&gt;...&lt;/b&gt; &lt;b&gt;Brooke&lt;/b&gt; Southall dug deep to get the story — and then interviewed &lt;b&gt;...&lt;/b&gt; &lt;b&gt;Brooke&lt;/b&gt; &lt;br&gt;  reached out to some of the most in-touch people in the RIA world &lt;b&gt;...&lt;/b&gt;</S><LANG>en</LANG><Label>_cse_auhlevjhxa4</Label><HAS><L/><C SZ="37k" CID="NxAiKwlIfkQJ"/><RT/></HAS></R> 
# <RG START="6" SIZE="1"></RG><R N="6"><U>http://www.riabiz.com/a/96001</U><UE>http://www.riabiz.com/a/96001</UE><T>RIABiz | 11 steps to becoming an RIA without upsetting Merrill &lt;b&gt;...&lt;/b&gt;</T><RK>0</RK><S>10 Dec 2009 &lt;b&gt;...&lt;/b&gt; &lt;b&gt;Brooke&amp;#39;s&lt;/b&gt; note: I think I know a lot about RIAs but if somebody were to ask &lt;b&gt;....&lt;/b&gt; &lt;br&gt;  Great article &lt;b&gt;Brooke&lt;/b&gt;. My experience at TradePMR confirms Mr. &lt;b&gt;...&lt;/b&gt;</S><LANG>en</LANG><Label>_cse_auhlevjhxa4</Label><HAS><L/><C SZ="34k" CID="yYSWPBHuLecJ"/><RT/></HAS></R> 
# <RG START="7" SIZE="1"></RG><R N="7"><U>http://www.riabiz.com/a/29195</U><UE>http://www.riabiz.com/a/29195</UE><T>RIABiz | 10 top ways to use social media without courting &lt;b&gt;...&lt;/b&gt;</T><RK>0</RK><S>22 Sep 2009 &lt;b&gt;...&lt;/b&gt; &lt;b&gt;Brooke&lt;/b&gt; Southall (RIABiz) (Tuesday 9/22/09 10:28a.m. &lt;b&gt;...&lt;/b&gt; &lt;b&gt;Brooke&lt;/b&gt;: It is not worth &lt;br&gt;  it to “speed” on compliance matters, especially violations &lt;b&gt;...&lt;/b&gt;</S><LANG>en</LANG><Label>_cse_auhlevjhxa4</Label><HAS><L/><C SZ="41k" CID="Tp4I0JY5UrcJ"/><RT/></HAS></R> 
# <RG START="8" SIZE="1"></RG><R N="8"><U>http://www.riabiz.com/a/63140</U><UE>http://www.riabiz.com/a/63140</UE><T>RIABiz | Black Diamond green lights beta testing of Blue Sky</T><RK>0</RK><S>Thursday 10/29/09 by &lt;b&gt;Brooke&lt;/b&gt; Southall tags: Black Diamond | Advent Software | &lt;br&gt;  Reed Colley | Dan Skiles | Chris Boruff | Morningstar &lt;b&gt;...&lt;/b&gt;</S><LANG>en</LANG><Label>_cse_auhlevjhxa4</Label><HAS><L/><C SZ="33k" CID="B2p8FQzcNXoJ"/><RT/></HAS></R> 
# <RG START="9" SIZE="1"></RG><R N="9"><U>http://www.riabiz.com/a/103207</U><UE>http://www.riabiz.com/a/103207</UE><T>RIABiz | Merrill Lynch goes unmentioned as Bank of America settles &lt;b&gt;...&lt;/b&gt;</T><RK>0</RK><S>Friday 12/18/09 by &lt;b&gt;Brooke&lt;/b&gt; Southall tags: Bank of America | Merrill Lynch | &lt;br&gt;  Schwab | US &lt;b&gt;...&lt;/b&gt; &lt;b&gt;Brooke&amp;#39;s&lt;/b&gt; note: What happens at Bank of America matters to RIAs. &lt;br&gt;  &lt;b&gt;...&lt;/b&gt;</S><LANG>en</LANG><Label>_cse_auhlevjhxa4</Label><HAS><L/><C SZ="35k" CID="AMZyIaflO2UJ"/><RT/></HAS></R> 
# <RG START="10" SIZE="1"></RG><R N="10"><U>http://www.riabiz.com/a/23426</U><UE>http://www.riabiz.com/a/23426</UE><T>RIABiz | Top 10 things I learned at Schwab IMPACT about the &lt;b&gt;...&lt;/b&gt;</T><RK>0</RK><S>17 Sep 2009 &lt;b&gt;...&lt;/b&gt; &lt;b&gt;Brooke&lt;/b&gt;,. Thank – You for a wonderful article. As the Executive Vice – President &lt;br&gt;  of an &lt;b&gt;...&lt;/b&gt; &lt;b&gt;Brooke&lt;/b&gt; Southall (Thursday 9/17/09 8:06a.m. PST) &lt;b&gt;...&lt;/b&gt;</S><LANG>en</LANG><Label>_cse_auhlevjhxa4</Label><HAS><L/><C SZ="35k" CID="vX8kRnfGKKsJ"/><RT/></HAS></R> 
# </RES> 
# </GSP>
# """

def xmltodict(xmlstring):
	doc = xml.dom.minidom.parseString(xmlstring)
	remove_whilespace_nodes(doc.documentElement)
	return elementtodict(doc.documentElement)

def elementtodict(parent):
	child = parent.firstChild
	if (not child):
		return None
	elif (child.nodeType == xml.dom.minidom.Node.TEXT_NODE):
		return child.nodeValue
	
	d={}
	while child is not None:
		if (child.nodeType == xml.dom.minidom.Node.ELEMENT_NODE):
			try:
				d[child.tagName]
			except KeyError:
				d[child.tagName]=[]
			d[child.tagName].append(elementtodict(child))
		child = child.nextSibling
	return d

def remove_whilespace_nodes(node, unlink=True):
	remove_list = []
	for child in node.childNodes:
		if child.nodeType == xml.dom.Node.TEXT_NODE and not child.data.strip():
			remove_list.append(child)
		elif child.hasChildNodes():
			remove_whilespace_nodes(child, unlink)
	for node in remove_list:
		node.parentNode.removeChild(node)
		if unlink:
			node.unlink()
			
			
# results = xmltodict(text)
# for r in results['RES'][0]['R']:
#   print str(r)
#   print '=============================='
# print results['Q'][0]
  