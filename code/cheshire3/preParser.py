from __future__ import absolute_import

import os
import re
import time
import string
import binascii
import glob
import httplib
import mimetypes
import tempfile
import hashlib
import subprocess

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

try:
    import cPickle as pickle
except ImportError:
    import pickle

from xml.sax.saxutils import escape
from warnings import warn
from lxml import etree

# Intra-package imports
from cheshire3.baseObjects import PreParser
from cheshire3.document import StringDocument
from cheshire3.marc_utils import MARC
from cheshire3.utils import getShellResult
from cheshire3.exceptions import ConfigFileException, ExternalSystemException


# TODO: All PreParsers should set mimetype, and record in/out mimetype

class TypedPreParser(PreParser):
    _possibleSettings = {
        "inMimeType": {
            'docs': "The mimetype expected for incoming documents"
        },
        "outMimeType": {
            'docs': "The mimetype set on outgoing documents"
        }
     }

    def __init__(self, session, config, parent):
        PreParser.__init__(self, session, config, parent)
        self.inMimeType = self.get_setting(session, 'inMimeType', '')
        self.outMimeType = self.get_setting(session, 'outMimeType', '')


class NormalizerPreParser(PreParser):
    """ Calls a named Normalizer to do the conversion."""

    _possiblePaths = {
        'normalizer': {
             'docs': "Normalizer identifier to call to do the transformation",
             'required': True
         }
    }

    def __init__(self, session, config, parent):
        PreParser.__init__(self, session, config, parent)
        self.normalizer = self.get_path(session, 'normalizer', None)
        if self.normalizer is None:
            msg = "Normalizer for {0} does not exist.".format(self.id)
            raise ConfigFileException(msg)

    def process_document(self, session, doc):
        data = doc.get_raw(session)
        new = self.normalizer.process_string(session, data)
        return StringDocument(new, self.id, doc.processHistory,
                              mimeType=doc.mimeType, parent=doc.parent,
                              filename=doc.filename)


class UnicodeDecodePreParser(PreParser):
    """PreParser to turn non-unicode into Unicode Documents.

    A UnicodeDecodePreParser should accept a Document with content encoded in 
    a non-unicode character encoding scheme and return a Document with the 
    same content decoded to Python's Unicode implementation.
    """

    _possibleSettings = {
        'codec': {
            'docs': 'Codec to use to decode to unicode. Defaults to UTF-8'
        }
    }

    def __init__(self, session, config, parent):
        PreParser.__init__(self, session, config, parent)
        self.codec = self.get_setting(session, 'codec', 'utf-8')

    def process_document(self, session, doc):
        try:
            data = doc.get_raw(session).decode(self.codec)
        except UnicodeDecodeError as e:
            raise e
        return StringDocument(data, self.id, doc.processHistory,
                              mimeType=doc.mimeType, parent=doc.parent,
                              filename=doc.filename)


class CmdLinePreParser(TypedPreParser):

    _possiblePaths = {
        'executable': {'docs': "Name of the executable to run"},
        'executablePath': {'docs': "Path to the executable"},
        'workingPath': {'docs': 'Path to be in when executing command'}
    }

    _possibleSettings = {
        'commandLine': {
            'docs': """\
Command line to use. %INDOC% is substituted to create a temporary file to 
read, and %OUTDOC% is substituted for a temporary file for the process to 
write to"""
        }
    }

    def __init__(self, session, config, parent):
        TypedPreParser.__init__(self, session, config, parent)
        exe = self.get_path(session, 'executable', '')
        if not exe:
            msg = "Missing mandatory 'executable' path in {0}".format(self.id)
            raise ConfigFileException(msg)
        tp = self.get_path(session, 'executablePath', '')
        if tp:
            exe = os.path.join(tp, exe)
        cl = self.get_setting(session, 'commandLine', '')
        self.cmd = exe + ' ' + cl
        self.working = self.get_path(session, 'workingPath', '')

    def process_document(self, session, doc):
        cmd = self.cmd
        stdIn = cmd.find('%INDOC%') == -1
        stdOut = cmd.find('%OUTDOC%') == -1
        if not stdIn:
            # Create temp file for incoming data
            if doc.mimeType or doc.filename:
                # Guess our extn~n                
                try:
                    suff = mimetypes.guess_extension(doc.mimeType)
                except:
                    suff = ''
                if not suff:
                    suff = mimetypes.guess_extension(doc.filename)
                    if not suff:
                        (foofn, suff) = os.path.splitext(doc.filename)
                if suff:
                    (qq, infn) = tempfile.mkstemp(suff)
                else:
                    (qq, infn) = tempfile.mkstemp()                    
            else:
                (qq, infn) = tempfile.mkstemp()                 

            os.close(qq)
            fh = open(infn, 'w')
            fh.write(doc.get_raw(session))
            fh.close()
            cmd = cmd.replace("%INDOC%", infn)
        if not stdOut:
            # Create temp file to outgoing data
            if self.outMimeType:
                # Guess our extn~n
                suff = mimetypes.guess_extension(self.outMimeType)
                (qq, outfn) = tempfile.mkstemp(suff)
            else:
                (qq, outfn) = tempfile.mkstemp()
            cmd = cmd.replace("%OUTDOC%", outfn)               
            os.close(qq)

        if self.working:
            old = os.getcwd()
            os.chdir(self.working)            
        else:
            old = ''

        if stdIn:
            pipe = subprocess.Popen(cmd, bufsize=0, shell=True, 
                                    stdin=subprocess.PIPE, 
                                    stdout=subprocess.PIPE, 
                                    stderr=subprocess.PIPE)
            pipe.stdin.write(doc.get_raw(session))
            pipe.stdin.close()
            result = pipe.stdout.read()
            pipe.stdout.close()
            pipe.stderr.close()
            del pipe
        else:
            # Result will read stdout+err regardless
            result = getShellResult(cmd)
            os.remove(infn)
            if not stdOut:
                if os.path.exists(outfn) and os.path.getsize(outfn) > 0:
                    fh = open(outfn)
                else:
                    # Command probably appended something to the filename
                    # Annoying! Have to glob for it
                    matches = glob.glob(outfn + "*")
                    # Or maybe ignored absolute path and put it in pwd...
                    matches2 = glob.glob(os.path.split(outfn)[-1] + '*')
                    for m in matches + matches2:
                        if os.path.getsize(m) > 0:
                            fh = open(m)
                            break
                try:
                    try:
                        result = fh.read()
                    except:
                        msg = '{0}: {1}'.format(cmd, result)
                        raise ExternalSystemException(msg)
                    else:
                        fh.close()
                finally:
                    os.remove(outfn)
                    try:
                        # Clean up when data written elsewhere
                        os.remove(fh.name) 
                    except OSError:
                        pass
        if old:
            os.chdir(old)
        mt = self.outMimeType
        if not mt:
            mt = doc.mimeType
        return StringDocument(result, self.id, doc.processHistory,
                              mimeType=mt, parent=doc.parent,
                              filename=doc.filename) 


class FileUtilPreParser(TypedPreParser):
    """Call 'file' util to find out the current type of file."""

    def __init__(self, session, config, parent):
        TypedPreParser.__init__(self, session, config, parent)
        warn('''\
{0} is deprecated in favour of objects available from the 
cheshire3.formats package.'''.format(self.__class__.__name__), 
            DeprecationWarning, 
            stacklevel=6)

    def process_document(self, session, doc):
        cmd = "file -i -b %INDOC%"
        (qq, infn) = tempfile.mkstemp()
        os.close(qq)
        fh = open(infn, 'w')
        fh.write(doc.get_raw(session))
        fh.close()
        cmd = cmd.replace("%INDOC%", infn)
        res = getShellResult(cmd)
        mt = res.strip()
        if mt.find(';') > -1:
            bits = mt.split(';')
            mt = bits[0]
            for b in bits[1:]:
                # just stuff them on doc for now
                (type, value) = b.split('=')
                setattr(doc, type, value)

        if mt == "text/plain":
            # Might be sgml, xml, text etc
            res = getShellResult("file -b {0}".format(infn))
            mt2 = res.strip()
            if mt2 == "exported SGML document text":
                mt = "text/sgml"
            elif mt2 == "XML document text":
                mt = "text/xml"
            # Others include java, etc. but not very useful to us
        doc.mimeType = mt
        doc.processHistory.append(self.id)
        return doc


class MagicRedirectPreParser(TypedPreParser):
    """Map to appropriate PreParser based on incoming MIME type."""

    def _handleLxmlConfigNode(self, session, node):
        # Handle config in the form:
        # <hash>
        #     <object mimeType="" ref=""/>
        #     ...
        # </hash>
        if node.tag == "hash":
            for c in node.iterchildren(tag=etree.Element):
                if c.tag == "object":
                    mt = c.attrib['mimeType']
                    ref = c.attrib['ref']
                    self.mimeTypeHash[mt] = ref

    def _handleConfigNode(self, session, node):
        # Handle config in the form:
        # <hash>
        #     <object mimeType="" ref=""/>
        #     ...
        # </hash>
        if node.localName == "hash":
            for c in node.childNodes:
                if c.nodeType == elementType and c.localName == "object":
                    mt = c.getAttributeNS(None, 'mimeType')
                    ref = c.getAttributeNS(None, 'ref')
                    self.mimeTypeHash[mt] = ref

    def __init__(self, session, config, parent):
        self.mimeTypeHash = {"application/x-gzip": "GunzipPreParser",
                             "application/postscript": "PsPdfPreParser",
                             "application/pdf": "PdfXmlPreParser",
                             "text/html": "HtmlSmashPreParser",
                             "text/plain": "TxtToXmlPreParser",
                             "text/sgml": "SgmlPreParser",
                             "application/x-bzip2": "BzipPreParser"
                             # "application/x-zip": "single zip preparser ?"
                             }

        # Now override from config in init:
        TypedPreParser.__init__(self, session, config, parent)

    def process_document(self, session, doc):
        mt = doc.mimeType
        db = session.server.get_object(session, session.database)
        if not mt:
            # Nasty kludge - use FileUtilPreParser to determine MIME type
            fu = db.get_object(session, 'FileUtilPreParser')
            doc2 = fu.process_document(session, doc)
            mt = doc2.mimeType
            if not mt and doc.filename:
                # Try and guess from filename
                mts = mimetypes.guess_type(doc.filename)
                if mts and mts[0]:
                    mt = mts[0]
        if mt in self.mimeTypeHash:
            db = session.server.get_object(session, session.database)
            redirect = db.get_object(session, self.mimeTypeHash[mt])
            if isinstance(redirect, PreParser):
                return redirect.process_document(session, doc)
            else:
                # Only other thing is workflow
                return redirect.process(session, doc)
        else:
            # XXX: Should we return or raise?
            return doc


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
        data = self.script.sub('', doc.get_raw(session))
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
        return StringDocument(data, self.id, doc.processHistory,
                              mimeType=doc.mimeType, parent=doc.parent,
                              filename=doc.filename) 


class RegexpSmashPreParser(PreParser):
    """Strip, replace or keep only data which matches a given regex."""

    _possibleSettings = {
        'char': {
            'docs': """\
Character(s) to replace matches in the regular expression with. Defaults to 
empty string (i.e. strip matches)"""
        },
        'regexp': {
            'docs': "Regular expression to match in the data.",
            'required': True
        },
        'keep': {
            'docs': """\
Should instead keep only the matches. Boolean, defaults to False""",
            'type': int,
            'options': "0|1"
        }
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
        data = doc.get_raw(session)
        if self.keep:
            l = self.regexp.findall(data)
            if l and l[0] and type(l[0]) == tuple:
                r = []
                for e in l:
                    r.append(e[0])
                l = r
            d2 = self.char.join(l)
        else:
            d2 = self.regexp.sub(self.char, data)
        return StringDocument(d2, self.id, doc.processHistory,
                              mimeType=doc.mimeType, parent=doc.parent,
                              filename=doc.filename) 


try:
    import tidy
except ImportError:
    # Gracefully degrade functionality

    class HtmlTidyPreParser(PreParser):

        def __init__(self, session, config, parent):
            raise NotImplementedError("""\
HtmlTidyPreParser not supported due to a missing library on your system.""")

else:
    class HtmlTidyPreParser(PreParser):
        """Uses TidyLib to turn HTML into XHTML for parsing."""

        def process_document(self, session, doc):
            d = tidy.parseString(doc.get_raw(session),
                                 output_xhtml=1,
                                 add_xml_decl=0,
                                 tidy_mark=0,
                                 indent=0)
            return StringDocument(str(d), self.id, doc.processHistory,
                                  mimeType=doc.mimeType, parent=doc.parent,
                                  filename=doc.filename)


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

    _possibleSettings = {
        'emptyElements': {
            'docs': '''\
Space separated list of empty elements in the SGML to turn into empty XML 
elements.'''
        }
    }

    def __init__(self, session, config, parent):
        PreParser.__init__(self, session, config, parent)
        self.doctype_re = (re.compile('<!DOCTYPE\s+?(.+?)["\'](.+?)["\']>'))
        self.attr_re = re.compile(
            ' ([a-zA-Z0-9_]+)[ ]*=[ ]*([-:_.a-zA-Z0-9]+)([ >])'
        )
        self.pi_re = re.compile("<\?(.*?)\?>")
        self.elem_re = re.compile('(<[/]?)([a-zA-Z0-9_]+)')
        self.amp_re = re.compile('&(\s)')
        taglist = self.get_setting(session, 'emptyElements')
        if taglist:
            self.emptyTags = taglist.split()

    def _loneAmpersand(self, match):
        # Fix unencoded ampersands
        return '&amp;%s' % match.group(1)

    def _lowerElement(self, match):
        # Make all tags lowercase
        #return match.groups()[0] + match.groups()[1].lower()
        return "%s%s" % (match.group(1), match.group(2).lower())

    def _attributeFix(self, match):
        # Fix messy attribute values
        # - lowercase attribute names
        # - remove spurious whitespace
        # - quote unquoted values
        #return match.groups()[0].lower() + '="' + match.groups()[1] + '"'
        return ' %s="%s"%s' % (match.group(1).lower(), 
                               match.group(2), 
                               match.group(3))

    def _emptyElement(self, match):
        # Make empty elements sefl-closing
        return "<%s/>" % (match.group(1))

    def process_document(self, session, doc):
        txt = doc.get_raw(session)
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
            empty_re = re.compile('<(%s( [^>/]+)?)[\s/]*>' % t)
            txt = empty_re.sub(self._emptyElement, txt)
        # strip processing instructions.
        txt = self.pi_re.sub('', txt)

        return StringDocument(txt, self.id, doc.processHistory,
                              mimeType=doc.mimeType, parent=doc.parent,
                              filename=doc.filename)


class AmpPreParser(PreParser):
    """Escape lone ampersands in otherwise XML text."""
    entities = {}

    def __init__(self, session, config, parent):
        PreParser.__init__(self, session, config, parent)
        self.amp_re = re.compile('&([^\s;]*)(\s|$)')
        self.entities = {}

    def _loneAmpersand(self, match):
        # Fix unencoded ampersands
        return '&amp;%s ' % match.group(1)

    def process_document(self, session, doc):
        txt = doc.get_raw(session)
        for e in self.entities.keys():
            txt = txt.replace("&%s;" % (e), self.entities[e])
        txt = self.amp_re.sub(self._loneAmpersand, txt)
        return StringDocument(txt, self.id, doc.processHistory,
                              mimeType=doc.mimeType, parent=doc.parent,
                              filename=doc.filename)


# --- MARC PreParsers ---

class MarcToXmlPreParser(PreParser):
    """ Convert MARC into MARCXML """
    inMimeType = "application/marc"
    outMimeType = "text/xml"

    def process_document(self, session, doc):
        data = doc.get_raw(session)
        m = MARC(data)
        return StringDocument(m.toMARCXML(), self.id, doc.processHistory,
                              mimeType='text/xml', parent=doc.parent,
                              filename=doc.filename)


class MarcToSgmlPreParser(PreParser):
    """ Convert MARC into Cheshire2's MarcSgml """
    inMimeType = "application/marc"
    outMimeType = "text/sgml"

    def process_document(self, session, doc):
        data = doc.get_raw(session)
        m = MARC(data)
        return StringDocument(m.toSGML(), self.id, doc.processHistory,
                              mimeType='text/sgml', parent=doc.parent,
                              filename=doc.filename)


# --- Raw Text PreParsers ---

class TxtToXmlPreParser(PreParser):
    """Minimally wrap text in <data> XML tags"""

    inMimeType = "text/plain"
    outMimeType = "text/xml"

    def process_document(self, session, doc):
        txt = doc.get_raw(session)
        txt = escape(txt)
        data = "<data>{0}</data>".format(txt)
        return StringDocument(data, self.id, doc.processHistory,
                              mimeType='text/xml', parent=doc.parent,
                              filename=doc.filename)


#  --- Compression PreParsers ---


class PicklePreParser(PreParser):
    """Compress Document content using Python pickle."""

    def process_document(self, session, doc):
        data = doc.get_raw(session)
        string = pickle.dumps(data)
        return StringDocument(string, self.id, doc.processHistory,
                              mimeType='text/pickle', parent=doc.parent,
                              filename=doc.filename)


class UnpicklePreParser(PreParser):
    """Decompress Document content using Python pickle."""

    def process_document(self, session, doc):
        data = doc.get_raw(session)
        string = pickle.loads(data)
        return StringDocument(string, self.id, doc.processHistory,
                              mimeType='text/pickle', parent=doc.parent,
                              filename=doc.filename)

try:
    import gzip
except ImportError:
    # Gracefully degrade functionality

    class GzipPreParser(PreParser):
        """Gzip a not-gzipped document."""
        def __init__(self, session, config, parent):
            raise NotImplementedError('''\
Compression by gzip is not supported due to a missing library in your system.\
''')

    class GunzipPreParser(PreParser):
        """Gunzip a gzipped document."""
        def __init__(self, session, config, parent):
            raise NotImplementedError('''\
Decompression by gzip is not supported due to a missing library in your \
system.''')

else:
    class GzipPreParser(PreParser):
        """Gzip a not-gzipped document."""
        inMimeType = ""
        outMimeType = ""

        def __init__(self, session, config, parent):
            PreParser.__init__(self, session, config, parent)
            self.compressLevel = self.get_setting(session, "compressLevel", 1)

        def process_document(self, session, doc):
            outDoc = StringIO.StringIO()
            zfile = gzip.GzipFile(mode='wb', fileobj=outDoc, 
                                  compresslevel=self.compressLevel)
            zfile.write(doc.get_raw(session))
            zfile.close()
            l = outDoc.tell()
            outDoc.seek(0)
            data = outDoc.read(l)
            outDoc.close()
            return StringDocument(data, self.id, doc.processHistory,
                                  parent=doc.parent, filename=doc.filename)

    # This comment needed for validation by PEP8 validator

    class GunzipPreParser(PreParser):
        """Gunzip a gzipped document."""
        inMimeType = ""
        outMimeType = ""

        def process_document(self, session, doc):
            buff = StringIO.StringIO(doc.get_raw(session))
            zfile = gzip.GzipFile(mode='rb', fileobj=buff)
            data = zfile.read()
            zfile.close()
            buff.close()
            del zfile
            del buff
            return StringDocument(data, self.id, doc.processHistory,
                                  parent=doc.parent, filename=doc.filename)

try:
    import bz2
except ImportError:
    # Gracefully degrade functionality

    class Bzip2PreParser(PreParser):
        """Unzip a bz2 zipped document."""
        def __init__(self, session, config, parent):
            raise NotImplementedError('''\
Decompression by bzip2 is not supported due to a missing library in your \
system.''')

else:
    class Bzip2PreParser(PreParser):
        """Unzip a bz2 zipped document."""
        def process_document(self, session, doc):
            bzdata = doc.get_raw(session)
            data = bz2.decompress(bzdata)
            return StringDocument(data, self.id, doc.processHistory,
                                  parent=doc.parent, filename=doc.filename)


class B64EncodePreParser(PreParser):
    """Encode document in Base64."""

    def process_document(self, session, doc):
        data = doc.get_raw(session)
        new = binascii.a2b_base64(data)
        return StringDocument(new, self.id, doc.processHistory,
                              parent=doc.parent, filename=doc.filename)


class B64DecodePreParser(PreParser):
    """Decode document from Base64."""

    def process_document(self, session, doc):
        data = doc.get_raw(session)
        new = binascii.b2a_base64(data)
        return StringDocument(new, self.id, doc.processHistory,
                              parent=doc.parent, filename=doc.filename)


# --- Nasty OpenOffice PreParser ---

class UrlPreParser(PreParser):
    """Abstract Base Class for PreParsers that use OpenOffice.

    DEPRECATED: see cheshire3.formats sub-package instead
    """

    _possiblePaths = {
        'remoteUrl': {
            'docs': 'URL at which the OpenOffice handler is listening'
        }
    }

    def _post_multipart(self, host, selector, fields, files):
        content_type, body = self._encode_multipart_formdata(fields, files)
        h = httplib.HTTPConnection(host)
        headers = {'content-type': content_type}
        h.request('POST', selector, body, headers)
        resp = h.getresponse()
        return resp.read()

    def _encode_multipart_formdata(self, fields, files):
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
            L.append(
                 'Content-Disposition: form-data; name="%s"; filename="%s"' % 
                 (key, filename)
                 )
            L.append('Content-Type: %s' % self._get_content_type(filename))
            L.append('')
            L.append(value)
        L.append('--' + BOUNDARY + '--')
        L.append('')
        body = CRLF.join(L)
        content_type = 'multipart/form-data; boundary=%s' % BOUNDARY
        return content_type, body

    def _get_content_type(self, filename):
        return mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    def _send_request(self, session, data=None):
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
        return self._post_multipart(host, selector, fields, files)


class OpenOfficePreParser(UrlPreParser):
    """Use OpenOffice server to convert documents into OpenDocument XML """

    inMimeType = ""
    outMimeType = "text/xml"

    def process_document(self, session, doc):
        data = doc.get_raw(session)
        try:
            xml = self._send_request(session, data)
        except:
            xml = "<error/>"
        return StringDocument(xml, self.id, doc.processHistory,
                              mimeType='text/xml', parent=doc.parent,
                              filename=doc.filename)


class PrintableOnlyPreParser(PreParser):
    """Replace or Strip non printable characters."""

    inMimeType = "text/*"
    outMimeType = "text/plain"

    _possibleSettings = {
        'strip': {
            'docs': """\
Should the preParser strip the characters or replace with numeric character \
entities (default)""", 
            'type': int,
            'options': "0|1"
        }
    }

    def __init__(self, session, config, parent):
        PreParser.__init__(self, session, config, parent)
        self.asciiRe = re.compile('([\x7b-\xff])')
        self.nonxmlRe = re.compile('([\x00-\x08]|[\x0E-\x1F]|[\x0B\x0C\x1F])')
        self.strip = self.get_setting(session, 'strip', 0)

    def process_document(self, session, doc):
        """Strip any non printable characters."""
        data = doc.get_raw(session)
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
            new = self.asciiRe.sub('', data)
        else:
            fn = lambda x: "&#%s;" % ord(x.group(1))
            new = self.asciiRe.sub(fn, data)
        return StringDocument(new, self.id, doc.processHistory,
                              mimeType=doc.mimeType, parent=doc.parent,
                              filename=doc.filename)


class CharacterEntityPreParser(PreParser):
    """Change named and broken entities to numbered.

    Transform latin-1 and broken character entities into numeric character 
    entities. eg
    &amp;something; --> &amp;#123;
    """

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
            "trade": '#8482',
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

        self.preEntities = {
            "OUML;": "Ouml",
            "UUML": "Uuml",
            "AELIG": "AElig",
            "Aelig": "AElig"
        }
        self.entities = ['nbsp', 'iexcl', 'cent', 'pound', 'curren', 'yen',
                         'brvbar', 'sect', 'uml', 'copy', 'ordf', 'laquo',
                         'not', 'shy', 'reg', 'macr', 'deg', 'plusmn',
                         'sup2', 'sup3', 'acute', 'micro', 'para', 'middot',
                         'cedil', 'sup1', 'ordm', 'raquo', 'frac14', 'frac12',
                         'frac34', 'iquest', 'Agrave', 'Aacute', 'Acirc',
                         'Atilde', 'Auml', 'Aring', 'AElig', 'Ccedil',
                         'Egrave', 'Eacute', 'Ecirc', 'Euml', 'Igrave',
                         'Iacute', 'Icirc', 'Iuml', 'ETH', 'Ntilde', 'Ograve',
                         'Oacute', 'Ocirc', 'Otilde', 'Ouml', 'times',
                         'Oslash', 'Ugrave', 'Uacute', 'Ucirc', 'Uuml',
                         'Yacute', 'THORN', 'szlig', 'agrave', 'aacute',
                         'acirc', 'atilde', 'auml', 'aring', 'aelig',
                         'ccedil', 'egrave', 'eacute', 'ecirc', 'euml',
                         'igrave', 'iacute', 'icirc', 'iuml', 'eth', 'ntilde',
                         'ograve', 'oacute', 'ocirc', 'otilde', 'ouml',
                         'divide', 'oslash', 'ugrave', 'uacute', 'ucirc',
                         'uuml', 'yacute', 'thorn', 'yuml']

    def process_document(self, session, doc):
        txt = doc.get_raw(session)
        # Replace entities that can be represented with simple chars
        for (fromEnt, toEnt) in self.inane.iteritems():
            txt = txt.replace("&%s;" % fromEnt, toEnt)
        # Fix some common mistakes
        for (fromEnt, toEnt) in self.preEntities.iteritems():
            txt = txt.replace("&%s;" % fromEnt, "&%s;" % toEnt)
        # Fix straight forward entites
        for (s, enty) in enumerate(self.entities):
            txt = txt.replace("&%s;" % enty, "&#%s;" % (160 + s))
        # Fix additional random entities
        for (fent, totxt) in self.otherEntities.iteritems():
            txt = txt.replace("&%s;" % fent, "&%s;" % totxt)
        # Add missing # in &123;

        def hashed(mo):
            return '&#%s;' % mo.group(1)

        txt = self.numericalEntRe.sub(hashed, txt)
        # Fix made up fraction entities. (?)

        def fraction(mo):
            return '%s&#8260;%s' % (mo.group(1), mo.group(2))

        txt = self.fractionRe.sub(fraction, txt)
        # Kill remaining invalid character entities
        txt = self.invalidRe.sub('', txt)
        return StringDocument(txt, self.id, doc.processHistory,
                              mimeType=doc.mimeType, parent=doc.parent,
                              filename=doc.filename)


class DataChecksumPreParser(PreParser):
    """Checksum Document data and add to Document metadata."""

    _possibleSettings = {
        'sumType': {
            'docs': "Type of checkSum to carry out.",
            'type': str,
            'default': 'md5'
        }
    }

    def __init__(self, session, config, parent):
        PreParser.__init__(self, session, config, parent)
        self.sumType = self.get_setting(session, 'sumType', 'md5')
        try:
            hashlib.new(self.sumType)
        except ValueError as e:
            raise ConfigFileException(str(e))

    def process_document(self, session, doc):
        data = doc.get_raw(session)
        h = hashlib.new(self.sumType)
        h.update(data)
        md = {
            self.sumType: {
                'hexdigest': h.hexdigest(),
                'analysisDateTime': time.strftime('%Y-%m-%dT%H:%M:%S%Z')
            }
        }
        try:
            doc.metadata['checksum'].update(md)
        except KeyError:
            doc.metadata['checksum'] = md
        doc.processHistory.append(self.id)
        return doc
