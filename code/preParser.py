
from baseObjects import PreParser
from document import StringDocument
import re, gzip, string, binascii, cStringIO as StringIO
import bz2
import httplib, mimetypes, tempfile, os, commands, time
from PyZ3950.zmarc import MARC
from xml.sax.saxutils import escape

# TODO: All PreParsers should set mimetype, and record in/out mimetype


# --- Wrapper ---

class NormaliserPreParser(PreParser):
    """ Calls a named Normaliser to do the conversion """

    _possiblePaths = {'normaliser': {'docs' : "Normaliser identifier to call to do the transformation", 'required' : True}}
    
    def __init__(self, session, config, parent):
        PreParser.__init__(self, session, config, parent)
        self.normaliser = self.get_path(session, 'normaliser', None)
        if self.normaliser == None:
            raise ConfigFileException("Normaliser for %s does not exist." % self.id)

    def process_document(self, session, doc):
        data = doc.get_raw()
        new = self.normaliser.process_string(session, data)
        return StringDocument(data, self.id, doc.processHistory, mimeType=doc.mimeType, parent=doc.parent, filename=doc.filename)
        

class UnicodeDecodePreParser(PreParser):

    _possibleSettings = {'codec': {'docs' : 'Codec to use to decode to unicode. Defaults to UTF-8'}}

    def __init__(self, session, server, config):
        PreParser.__init__(self, session, server, config)
        self.codec = self.get_setting(session, 'codec', 'utf-8')
    def process_document(self, session, doc):
        try:
            data = doc.get_raw().decode(self.codec)
        except UnicodeDecodeError, e:
            raise
        
        return StringDocument(data, self.id, doc.processHistory, mimeType=doc.mimeType, parent=doc.parent, filename=doc.filename)
        

class CmdLinePreParser(PreParser):

    _possiblePaths = {'commandLine' : {'docs' : "Command line to use.  %INDOC% is substituted to create a temporary file to read, and %OUTDOC% is substituted for a temporary file for the process to write to"}}

    def __init__(self, session, server, config):
        PreParser.__init__(self, session, server, config)
        self.cmd = self.get_path(session, 'commandLine', '')
        if not self.cmd:
            raise ConfigFileException("Missing mandatory 'commandLine' path in %s" % self.id)
        # %INDOC%: create temp file for in
        # %OUTDOC%: create temp file to out
                   
    def process_document(self, session, doc):
        cmd = self.cmd
        stdIn = cmd.find('%INDOC%') == -1
        stdOut = cmd.find('%OUTDOC%') == -1
        if not stdIn:
            if doc.mimeType:
                # guess our extn~n
                suff = mimetypes.guess_extension(doc.mimeType[0])
                (qq, infn) = tempfile.mkstemp("." + suff)
            else:
                (qq, infn) = tempfile.mkstemp()
            fh = file(infn, 'w')
            fh.write(doc.get_raw())
            fh.close()
            cmd = cmd.replace("%INDOC%", infn)
        if not stdOut:
            if self.outMimeType:
                # guess our extn~n
                suff = mimetypes.guess_extension(self.outMimeType)
                (qq, outfn) = tempfile.mkstemp("." + suff)
            else:
                (qq, outfn) = tempfile.mkstemp()
            cmd = cmd.replace("%OUTDOC%", outfn)               

        if stdIn:
            (i,o,e) = os.popen3(cmd)
            i.write(doc.get_raw())
            i.close()
            result = o.read()
            o.close()
            e.close()
        else:
            # result will read stdout+err regardless
            result = commands.getoutput(cmd)
            os.remove(infn)
            if not stdOut:
                fh = file(outfn)
                result = fh.read()
                fh.close()
                os.remove(outfn)

        return StringDocument(result, self.id, doc.processHistory, mimeType=doc.mimeType, parent=doc.parent, filename=doc.filename) 
    


# --- HTML PreParsers ---

class HtmlSmashPreParser(PreParser):
    """ Attempts to reduce HTML to its raw text """

    def __init__(self, session, config, parent):
        PreParser.__init__(self, session, config, parent)
	self.body = re.compile('<body(.*?)</body>', re.S | re.I)
	self.tagstrip = re.compile('<[^>]+>')
	self.title = re.compile('<title[^>]*>(.+?)</title>', re.S | re.I)
	self.script = re.compile('<script(.*?)</script>', re.S | re.I)
	self.style = re.compile('<style(.*?)</style>', re.S | re.I)
	self.comment = re.compile('<!--(.*?)-->', re.S | re.I)

    def process_document(self, session, doc):
	data = self.script.sub('', doc.get_raw())
	data = self.style.sub('', data)
	data = self.comment.sub('', data)
	tm = self.title.search(data)
	if tm:
	   title = data[tm.start():tm.end()]
	else:
	   title = ""
	m = self.body.search(data)
	if m:
	   body = data[m.start():m.end()]
	else:
	   body = data
	text = self.tagstrip.sub(' ', body)	
	text = text.replace('<', '&lt;')
	text = text.replace('>', '&gt;')
	text = text.replace("&nbsp;", ' ')
	text = text.replace("&nbsp", ' ')

	l = text.split()
	text = ' '.join(l)
	data = "<html><head>%s</head><body>%s</body></html>" % (title, text)
	return StringDocument(data, self.id, doc.processHistory, mimeType=doc.mimeType, parent=doc.parent, filename=doc.filename) 


class RegexpSmashPreParser(PreParser):
    """ Either strip, replace or keep data which matches a given regular expression """

    _possibleSettings = {'char':
                         {'docs' :"Character(s) to replace matches in the regular expression with. Defaults to empty string (eg strip matches)"},
                         'regexp':
                         {'docs' : "Regular expression to match in the data.", 'required' : True},
                         'keep':
                         {'docs' : "Should instead keep only the matches. Boolean, defaults to False", 'type': int, 'options' : "0|1"}
                         }


    def __init__(self, session, config, parent):
        PreParser.__init__(self, session, config, parent)
        char = self.get_setting(session, 'char')
        regex = self.get_setting(session, 'regexp')
        self.keep = self.get_setting(session, 'keep')
        if regex:
            self.regexp = re.compile(regex, re.S)
        if char:
            self.char = char
        else:
            self.char = ''

    def process_document(self, session, doc):
        data = doc.get_raw()
        if self.keep:
            l = self.regexp.findall(data)
            if l and l[0] and type(l[0]) == tuple:
                r = []
                for e in l:
                    r.append(e[0])
                l = r
            d2 = self.char.join(l)
        else:
            d2 =  self.regexp.sub(self.char, data)
        return StringDocument(d2, self.id, doc.processHistory, mimeType=doc.mimeType, parent=doc.parent, filename=doc.filename) 


try:
    import tidy
    
    class HtmlTidyPreParser(PreParser):
        """ Uses TidyLib to turn HTML into XHTML for parsing """
        def process_document(self, session, doc):
            d = tidy.parseString(doc.get_raw(), output_xhtml=1, add_xml_decl=0, tidy_mark=0, indent=0)
            return StringDocument(str(d), self.id, doc.processHistory, mimeType=doc.mimeType, parent=doc.parent, filename=doc.filename) 
except:
    pass



# --- Not Quite Xml PreParsers ---

class SgmlPreParser(PreParser):
    """ Convert SGML into XML """
    entities = {}
    emptyTags = []
    doctype_re = None
    attr_re = None
    elem_re = None
    amp_re = None
    inMimeType = "text/sgml"
    outMimeType = "text/xml"

    _possibleSettings = {'emptyElements' : {'docs' : 'Space separated list of empty elements in the SGML to turn into empty XML elements.'}}

    def __init__(self, session, server, config):

        PreParser.__init__(self, session, server, config)
        self.doctype_re = (re.compile('<!DOCTYPE (.+?)"(.+?)">'))
        self.attr_re = re.compile(' ([a-zA-Z0-9_]+)[ ]*=[ ]*([-:_.a-zA-Z0-9]+)([ >])')
        self.pi_re = re.compile("<\?(.*?)\?>")
        self.elem_re = re.compile('(<[/]?)([a-zA-Z0-9_]+)')
        self.amp_re = re.compile('&(\s)')
        taglist = self.get_setting(session, 'emptyElements')
        if taglist:
            self.emptyTags = taglist.split()

    def _loneAmpersand(self, match):
        return '&amp;%s' % match.group(1)
    def _lowerElement(self, match):
        #return match.groups()[0] + match.groups()[1].lower()
        return "%s%s" % (match.group(1), match.group(2).lower())
    def _attributeFix(self, match):
        #return match.groups()[0].lower() + '="' + match.groups()[1] + '"'
        return ' %s="%s"%s' % (match.group(1).lower(), match.group(2), match.group(3))
    def _emptyElement(self, match):
        return "<%s/>" % (match.group(1))

    def process_document(self, session, doc):
        txt = doc.get_raw()

        txt = txt.replace('\n', ' ')
        txt = txt.replace('\r', ' ')
        for x in range(9, 14):
            txt = txt.replace('&#%d;' % (x), ' ')

        txt = self.doctype_re.sub('', txt)
        for e in self.entities.keys():
            txt = txt.replace("&%s;" % (e), self.entities[e])

        txt = self.amp_re.sub(self._loneAmpersand, txt)
        txt = txt.replace('&<', '&amp;<')
        txt = self.attr_re.sub(self._attributeFix, txt)
        txt = self.elem_re.sub(self._lowerElement, txt)
        for t in self.emptyTags:
            empty_re = re.compile('<(%s( [^>]+)?)[\s/]*>' % t)
            txt = empty_re.sub(self._emptyElement, txt)
        # strip processing instructions.
        txt = self.pi_re.sub('', txt)

        return StringDocument(txt, self.id, doc.processHistory, mimeType=doc.mimeType, parent=doc.parent, filename=doc.filename)
    


class AmpPreParser(PreParser):
    """ Escape lone ampersands in otherwise XML text """
    entities = {}

    def __init__(self, session, server, config):
        PreParser.__init__(self, session, server, config)
        self.amp_re = re.compile('&([^\s;]*)(\s|$)')
	self.entities = {}

    def _loneAmpersand(self, match):
        return '&amp;%s ' % match.group(1)

    def process_document(self, session, doc):
        txt = doc.get_raw()
        for e in self.entities.keys():
            txt = txt.replace("&%s;" % (e), self.entities[e])
        txt = self.amp_re.sub(self._loneAmpersand, txt)
        return StringDocument(txt, self.id, doc.processHistory, mimeType=doc.mimeType, parent=doc.parent, filename=doc.filename)


# --- MARC PreParsers ---

class MarcToXmlPreParser(PreParser):
    """ Convert MARC into MARCXML """
    inMimeType = "application/marc"
    outMimeType = "text/xml"

    def process_document(self, session, doc):
        data = doc.get_raw()
        m = MARC(data)
        return StringDocument(m.toMARCXML(), self.id, doc.processHistory, mimeType='text/xml', parent=doc.parent, filename=doc.filename)

class MarcToSgmlPreParser(PreParser):
    """ Convert MARC into Cheshire2's MarcSgml """
    inMimeType = "application/marc"
    outMimeType = "text/sgml"

    def process_document(self, session, doc):
        data = doc.get_raw()
        m = MARC(data)
        return StringDocument(m.toSGML(), self.id, doc.processHistory, mimeType='text/sgml', parent=doc.parent, filename=doc.filename)


# --- Raw Text PreParsers ---

class TxtToXmlPreParser(PreParser):
    """ Minimally wrap text in &lt;data&gt; xml tags """

    inMimeType = "text/plain"
    outMimeType = "text/xml"

    def process_document(self, session, doc):
        txt = doc.get_raw()
        txt = escape(txt)
        return StringDocument("<data>" + txt + "</data>", self.id, doc.processHistory, mimeType='text/xml', parent=doc.parent, filename=doc.filename)



#  --- Compression PreParsers ---


class PicklePreParser(PreParser):
    def process_document(self, session, doc):
        data = doc.get_raw()
        string = cPickle.dumps(data)
        return StringDocument(string, self.id, doc.processHistory, mimeType='text/pickle', parent=doc.parent, filename=doc.filename)
    
class UnpicklePreParser(PreParser):
    def process_document(self, session, doc):
        data = doc.get_raw()
        string = cPickle.loads(data)
        return StringDocument(string, self.id, doc.processHistory, mimeType='text/pickle', parent=doc.parent, filename=doc.filename)
    
class GzipPreParser(PreParser):
    """ Gunzip a gzipped document """
    inMimeType = ""
    outMimeType = ""
    
    def process_document(self, session, doc):
        buffer = StringIO.StringIO(doc.get_raw())
        zfile = gzip.GzipFile(mode = 'rb', fileobj=buffer)
        data = zfile.read()
        return StringDocument(data, self.id, doc.processHistory, parent=doc.parent, filename=doc.filename)

class BzipPreParser(PreParser):
    def process_document(self, session, doc):
        buffer = StringIO.StringIO(doc.get_raw())
        zfile = bz2.BZ2File(mode = 'rb', fileobj=buffer)
        data = zfile.read()
        return StringDocument(data, self.id, doc.processHistory, parent=doc.parent, filename=doc.filename)

class B64EncodePreParser(PreParser):
    """ Encode document in Base64 """

    def process_document(self, session, doc):
        data = doc.get_raw()
        return StringDocument(binascii.a2b_base64(data), self.id, doc.processHistory, parent=doc.parent, filename=doc.filename)
    
    
class B64DecodePreParser(PreParser):
    """ Decode document from Base64 """

    def process_document(self, session, doc):
        data = doc.get_raw()
        return StringDocument(binascii.b2a_base64(data), self.id, doc.processHistory, parent=doc.parent, filename=doc.filename)



# --- Nasty OpenOffice PreParser ---

class UrlPreParser(PreParser):


    _possiblePaths = {'remoteUrl' : {'docs' : 'URL at which the OpenOffice handler is listening'}}

    def post_multipart(self, host, selector, fields, files):
        content_type, body = self.encode_multipart_formdata(fields, files)
        h = httplib.HTTPConnection(host)
        headers = {'content-type': content_type}
        h.request('POST', selector, body, headers)
        resp = h.getresponse()
        return resp.read()

    def encode_multipart_formdata(self, fields, files):
        BOUNDARY = '----------ThIs_Is_tHe_bouNdaRY_$'
        CRLF = '\r\n'
        L = []
        for (key, value) in fields:
            L.append('--' + BOUNDARY)
            L.append('Content-Disposition: form-data; name="%s"' % key)
            L.append('')
            L.append(value)
        for (key, filename, value) in files:
            L.append('--' + BOUNDARY)
            L.append('Content-Disposition: form-data; name="%s"; filename="%s"' % (key, filename))
            L.append('Content-Type: %s' % self.get_content_type(filename))
            L.append('')
            L.append(value)
        L.append('--' + BOUNDARY + '--')
        L.append('')
        body = CRLF.join(L)
        content_type = 'multipart/form-data; boundary=%s' % BOUNDARY
        return content_type, body

    def get_content_type(self, filename):
        return mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    def send_request(self, session, data=None):
        url = self.get_path(session, 'remoteUrl')
        if (url[:7] == "http://"):
            url = url[7:]
        hlist = url.split('/', 1)
        host = hlist[0]
        if (len(hlist) == 2):
            selector = hlist[1]
        else:
            selector = ""
        # TODO:  Remove dependency
        fields = ()
        files = [("file", "foo.doc", data)]
        return self.post_multipart(host, selector, fields, files)
    
class OpenOfficePreParser(UrlPreParser):
    """ Use OpenOffice server to convert documents into OpenDocument XML """
    inMimeType = ""
    outMimeType = "text/xml"

    def process_document(self, session, doc):
        data = doc.get_raw()
        try:
            xml = self.send_request(session, data)
        except:
            xml = "<error/>"
        return StringDocument(xml, self.id, doc.processHistory, mimeType='text/xml', parent=doc.parent, filename=doc.filename)




class PrintableOnlyPreParser(PreParser):
    """ Replace or Strip non printable characters """

    inMimeType = "text/*"
    outMimeType = "text/plain"

    _possibleSettings = {'strip' : {'docs' : "Should the preParser strip the characters or replace with numeric character entities (default)", 'type' : int, 'options' : "0|1"}}

    def __init__(self, session, config, parent):
        PreParser.__init__(self, session, config, parent)
        self.asciiRe = re.compile('([\x7b-\xff])')
        self.nonxmlRe = re.compile('([\x00-\x08]|[\x0E-\x1F]|[\x0B\x0C\x1F])')
 	self.strip = self.get_setting(session, 'strip', 0)
	
    # Strip any non printable characters
    def process_document(self, session, doc):
        data = doc.get_raw()
        # This is bizarre, but otherwise:
        # UnicodeDecodeError: 'ascii' codec can't decode byte ...
        if type(data) == unicode:
            data = data.replace(u"\xe2\x80\x9c", u'&quot;')
            data = data.replace(u"\xe2\x80\x9d", u'&quot;')
            data = data.replace(u"\xe2\x80\x9e", u'&quot;')
            data = data.replace(u"\xe2\x80\x93", u'-')
            data = data.replace(u"\xe2\x80\x98", u"'")
            data = data.replace(u"\xe2\x80\x99", u"'")
            data = data.replace(u"\xe2\x80\x9a", u",")
            data = data.replace(u"\x99", u"'")        
            data = data.replace(u'\xa0', u' ')
        else:
            data = data.replace("\xe2\x80\x9c", '&quot;')
            data = data.replace("\xe2\x80\x9d", '&quot;')
            data = data.replace("\xe2\x80\x9e", '&quot;')
            data = data.replace("\xe2\x80\x93", '-')
            data = data.replace("\xe2\x80\x98", "'")
            data = data.replace("\xe2\x80\x99", "'")
            data = data.replace("\xe2\x80\x9a", ",")
            data = data.replace("\x99", "'")        
            data = data.replace('\xa0', ' ')
            

        data = self.nonxmlRe.sub(' ', data)
	
	if self.strip:
	    return StringDocument(self.asciiRe.sub('', data), self.id, doc.processHistory, mimeType=doc.mimeType, parent=doc.parent, filename=doc.filename)
	else:
	    fn = lambda x: "&#%s;" % ord(x.group(1))
	    return StringDocument(self.asciiRe.sub(fn, data), self.id, doc.processHistory, mimeType=doc.mimeType, parent=doc.parent, filename=doc.filename)



class CharacterEntityPreParser(PreParser):
    """ Transform latin-1 and broken character entities into numeric character entities. eg &amp;something; --> &amp;#123; """
    
    def __init__(self, session, config, parent):
        PreParser.__init__(self, session, config, parent)

        self.numericalEntRe = re.compile('&(\d+);')
        self.fractionRe = re.compile('&frac(\d)(\d);')
        self.invalidRe = re.compile('&#(\d|[0-2]\d|3[01]);')

        self.start = 160
        self.otherEntities = {
            "quot": '#34',
            "amp": '#38',
            "lt": '#60',
            "gt": '#62',
            "trade" : '#8482',
            "OElig": '#338',
            "oelig": '#339',
            "Scaron": '#352',
            "scaron": '#353',
            "Yuml": '#376',
            "circ": '#710',
            "tilde": '#732',
            "ensp": '#8194',
            "emsp": '#8195',
            "thinsp": '#8201',
            "zwnj": '#8204',
            "zwj": '#8205',
            "lrm": '#8206',
            "rlm": '#8207',
            "ndash": '#8211',
            "mdash": '#8212',
            "lsquo": '#8216',
            "rsquo": '#8217',
            "sbquo": '#8218',
            "ldquo": '#8220',
            "rdquo": '#8221',
            "bdquo": '#8222',
            "dagger": '#8224',
            "Dagger": '#8225',
            "permil": '#8240',
            "lsaquo": '#8249',
            "rsaquo": '#8250',
            "euro": '#8364',
            "rdquo": '#34',
            "lsquo": '#34',
            "rsquo": '#34',
            "half": '#189',
            "ast": '#8727'
            }
        self.inane = {
            "apos": "'",
            "hellip": '...',
            "ldquo": '',
            "lsqb": '[',
            "rsqb": ']',
            "sol": '\\',
            "commat": '@',
            "plus": '+',
            "percnt": '%'
            }

        self.preEntities = {"OUML;" : "Ouml", "UUML" : "Uuml", "AELIG" : "AElig"}
        self.entities = ['nbsp', 'iexcl', 'cent', 'pound', 'curren', 'yen', 'brvbar', 'sect', 'uml',    'copy',   'ordf',   'laquo',  'not',    'shy',    'reg',    'macr',   'deg',    'plusmn', 'sup2',   'sup3',   'acute',  'micro',  'para',   'middot', 'cedil',  'sup1',   'ordm',   'raquo',  'frac14', 'frac12', 'frac34', 'iquest', 'Agrave', 'Aacute', 'Acirc',  'Atilde', 'Auml',   'Aring',  'AElig',  'Ccedil','Egrave','Eacute','Ecirc', 'Euml',  'Igrave', 'Iacute','Icirc', 'Iuml',  'ETH',   'Ntilde','Ograve','Oacute','Ocirc', 'Otilde','Ouml',  'times', 'Oslash','Ugrave','Uacute','Ucirc', 'Uuml',  'Yacute','THORN', 'szlig', 'agrave','aacute','acirc', 'atilde','auml',  'aring', 'aelig', 'ccedil','egrave','eacute','ecirc', 'euml',  'igrave', 'iacute','icirc', 'iuml',  'eth',   'ntilde','ograve', 'oacute','ocirc', 'otilde','ouml',  'divide','oslash','ugrave','uacute','ucirc', 'uuml',  'yacute','thorn', 'yuml']
                
    def process_document(self, session, doc):
        txt = doc.get_raw()
        # Fix some common mistakes
        for (fromEnt, toEnt) in self.inane.items():
            txt = txt.replace("&%s;" % fromEnt, toEnt)
        for (fromEnt, toEnt) in self.preEntities.items():
            txt = txt.replace("&%s;" % fromEnt, "&%s;" % toEnt)
        for s in range(len(self.entities)):
            txt = txt.replace("&%s;" % self.entities[s] , "&#%s;" % (160 +s))
        for (fent, totxt) in self.otherEntities.items():
            txt = txt.replace("&%s;" % fent, "&%s;" % totxt)

        # Add missing # in &123;
        def hashed(mo): return '&#%s;' % mo.group(1)
        txt = self.numericalEntRe.sub(hashed, txt)
        # Fraction entities. (?)
        def fraction(mo): return '%s&#8260;%s' % (mo.group(1), mo.group(2))
        txt = self.fractionRe.sub(fraction, txt)

        # kill invalid character entities
        txt = self.invalidRe.sub('', txt)

        return StringDocument(txt, self.id, doc.processHistory, mimeType=doc.mimeType, parent=doc.parent, filename=doc.filename)
        
