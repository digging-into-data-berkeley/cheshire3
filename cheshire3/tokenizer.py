
from cheshire3.baseObjects import Tokenizer

from dateutil import parser as dateparser
from datetime import timedelta
import re

# Python source code tokenizer from base libs
import tokenize, StringIO, keyword

# swap a string over to a list of tokens
# lists aren't hashable so we maintain string key
# also we're very unlikely to duplicate at this point,
#   and even if we do it's not important.
# This MUST be followed by a merge, however.
# as normalisers won't know what to do with a list as data


class SimpleTokenizer(Tokenizer):
    
    _possibleSettings = {'char' : {'docs' : 'character to split with, or empty for default of whitespace'}}

    def __init__(self, session, config, parent):
        Tokenizer.__init__(self, session, config, parent)
        self.char = self.get_setting(session, 'char', None)

    def process_string(self, session, data):
        if self.char:
            return data.split(self.char)
        else:
            return data.split()

    def process_hash(self, session, data):
        kw = {}
        for (key, val) in data.iteritems():
            nval = val.copy()
            nval['text'] = self.process_string(session, val['text'])
            kw[key] = nval
        return kw

class OffsetTokenizer(Tokenizer):

    def process_hash(self, session, data):
        kw = {}
        for (key, val) in data.iteritems():
            nval = val.copy()
            (tokens, positions) = self.process_string(session, val['text']) 
            nval['text'] = tokens
            nval['charOffsets'] = positions
            kw[key] = nval
        return kw


class RegexpSubTokenizer(SimpleTokenizer):
    u"""A Tokenizer that replaces regular expression matches in the data with a configurable character (defaults to whitespace), then splits the result at whitespace.."""
    # pre = self.get_setting(session, 'regexp', u"((?<!\s)'|[-.,]((?=\s)|$)|(^|(?<=\s))[-.,']|[\".,'-][\".,'-]|[~`!@+=\#\&\^*()\[\]{}\\\|\":;<>?/\u2026\u2013\u2014\u2018\u2019\u201c\u201d])")

    _possibleSettings = {'regexp' : {'docs' : ''},
                         'char' : {'docs' : ''}}

    def __init__(self, session, config, parent):
        SimpleTokenizer.__init__(self, session, config, parent)
        pre = self.get_setting(session, 'regexp', u"""([-.,'\")}\]]+((?=\s)|$)|(^|(?<=\s))[-.,']+|[`~!@+=\#\&\^*()\[\]{}\\\|\":;<>?/\u2026\u2013\u2014\u2018\u2019\u201c\u201d]|\.\.\.)""")
        # all strings should be treated as unicode internally
        # this is default for lxml - primary Record implementation
        self.regexp = re.compile(pre, re.UNICODE)
        self.char = self.get_setting(session, 'char', ' ')

    def process_string(self, session, data):
        txt = self.regexp.sub(self.char, data)  # kill unwanted characters
        return txt.split()                      # split at whitespace


class RegexpSplitTokenizer(SimpleTokenizer):
    """A Tokenizer that simply splits at the regex matches."""
     
    _possibleSettings = {'regexp' : {'docs' : 'Regular expression used to split string'}}
     
    def __init__(self, session, config, parent):
        SimpleTokenizer.__init__(self, session, config, parent)
        pre = self.get_setting(session, 'regexp', u"""([-.,'\")}\]]+((?=\s)|$)|(^|(?<=\s))[-.,']+|[`~!@+=\#\&\^*()\[\]{}\\\|\":;<>?/\u2026\u2013\u2014\u2018\u2019\u201c\u201d]|\.\.\.)""")
        self.regexp = re.compile(pre, re.UNICODE)

    def process_string(self, session, data):
        return self.regexp.split(data)


class RegexpFindTokenizer(SimpleTokenizer):
    """A tokenizer that returns all words that match the regex."""
    # Some ideas thanks to NLTK's RegexpTokenizer

    # Some more ' words:
    # cat-o'-nine-tails, ne'er-do-well, will-o'-the-wisp
    #  --- ignoring
    # 'tis, 'twas, 'til, 'phone
    #  --- IMO should be indexed with leading '
    #  --- eg 'phone == phone
    # 
    # XXX: Should come up with better solution
    # l'il ? y'all ?  
    # 

    # XXX: Decide what to do with 8am 8:00am 1.2M $1.2 $1.2M
    # As related to 8 am, 8:00 am, 1.2 Million, $ 1.2, $1.2 Million
    # vs $1200000 vs $ 1200000 vs four million dollars

    # Require acronyms to have at least TWO letters Eg U.S not just J.

    _possibleSettings = {'regexp' : {'docs' : 'Regular expression'},
                         'gaps' : {'docs' : 'Does the regular expression specify the gaps between desired tokens. Defaults to 0 i.e. No, it specifies tokens to keep', 'type' : int, 'options' : "0|1"}
                         }

    def __init__(self, session, config, parent):
        SimpleTokenizer.__init__(self, session, config, parent)
        pre = self.get_setting(session, 'regexp', u"""
          (?xu)                                            #verbose, unicode
          (?:
            [a-zA-Z0-9!#$%*/?|^{}`~&'+-=_]+@[0-9a-zA-Z.-]+ #email
           |(?:[\w+-]+)?[+-]/[+-]                          #alleles
           |\w+(?:-\w+)+(?:'(?:t|ll've|ll|ve|s|d've|d|re))?  #hypenated word (maybe 'xx on the end)
           |[$\xa3\xa5\u20AC]?[0-9]+(?:[.,:-][0-9]+)+[%]?  #date/num/money/time
           |[$\xa3\xa5\u20AC][0-9]+                        #single money
           |[0-9]+(?=[a-zA-Z]+)                            #split: 8am 1Million
           |[0-9]+%                                        #single percentage 
           |(?:[A-Z]\.)+[A-Z\.]                            #acronym
           |[oOd]'[a-zA-Z]+                                #o'clock, O'brien, d'Artagnan   
           |[a-zA-Z]+://[^\s]+                             #URI
           |\w+'(?:d've|d|t|ll've|ll|ve|s|re)              #don't, we've
           |(?:[hH]allowe'en|[mM]a'am|[Ii]'m|[fF]o'c's'le|[eE]'en|[sS]'pose)
           |[\w+]+                                         #basic words, including +
          )""")

        self.regexp = re.compile(pre, re.UNICODE)
        self.gaps = self.get_setting(session, 'gaps', 0)

    def process_string(self, session, data):
        if self.gaps:
            return [tok for tok in self.regexp.split(text) if tok]
        else:
            return self.regexp.findall(data)


class RegexpFindOffsetTokenizer(OffsetTokenizer, RegexpFindTokenizer):
    """A tokenizer that returns all words that match the regex, and also the character offset at which each word occurs."""
    
    def __init__(self, session, config, parent):
        # Only init once!
        RegexpFindTokenizer.__init__(self, session, config, parent)

    def process_string(self, session, data):
        tokens = []
        positions = []
        for m in self.regexp.finditer(data):
            tokens.append(m.group())
            positions.append(m.start())
        return (tokens, positions)
                         

class RegexpFindPunctuationOffsetTokenizer(RegexpFindOffsetTokenizer):

    def process_string(self, session, data):
        tokens = []
        positions = []
        for m in self.regexp.finditer(data):
            tokens.append(m.group())
            i = m.start();
            while i > 0 and data[i-1] in string.punctuation:
                i = i-1
            positions.append(i)
        return (tokens, positions)


# XXX: This should be in TextMining, and NLTK should auto install
try:
    import nltk
    class PunktWordTokenizer(SimpleTokenizer):

        def __init__(self, session, config, parent):
            SimpleTokenizer.__init__(self, session, config, parent)
            self.punkt = nltk.tokenize.PunktWordTokenizer()

        def process_string(self, session, data):
            return self.punkt.tokenize(data)


    class PunktSentenceTokenizer(SimpleTokenizer):
        def __init__(self, session, config, parent):
            SimpleTokenizer.__init__(self, session, config, parent)
            self.punkt = nltk.data.load('tokenizers/punkt/english.pickle')

        def process_string(self, session, data):
            return self.punkt.tokenize(data)
except:
    pass


# Was a text mining util, now should reformulate workflows
class SentenceTokenizer(SimpleTokenizer):

    def __init__(self, session, config, parent):
        self.paraRe = re.compile('\n\n+', re.UNICODE)
        self.sentenceRe = re.compile('.+?(?<!\.\.)[\.!?:]["\'\)]?(?=\s+|$)(?![a-z])', re.UNICODE)
        self.abbrMashRe = re.compile('(^|\s)([^\s]+?\.[a-zA-Z]+|Prof|Dr|Sr|Mr|Mrs|Ms|Jr|Capt|Gen|Col|Sgt|[ivxjCcl]+|[A-Z])\.(\s|$)', re.UNICODE)

    def process_string(self, session, data):
        ps = self.paraRe.split(data)
        sents = []
        for p in ps:
            s = self.abbrMashRe.sub('\\1\\2&#46;\\3', p)
            sl = self.sentenceRe.findall(s)
            if not sl:
                s += '.'
                sl = self.sentenceRe.findall(s)                
            sents.extend(sl)
        ns = []
        for s in sents:
            ns.append(s.replace("&#46;", '.'))
        return ns


# trivial, but potentially useful
class LineTokenizer(SimpleTokenizer):
    def process_string(self, session, data):
        return data.split('\n')


class DateTokenizer(SimpleTokenizer):
    """Tokenizer to identify date tokens, and return only these.
    
    Capable of extracting multiple dates, but slowly and less reliably than single ones."""

    _possibleDefaults = {'datetime' : {"docs" : "Default datetime to use for values not supplied in the data"}}
    _possibleSettings = {'fuzzy' : {"docs" : "Should the parser use fuzzy matching.", 'type' : int, 'options' : '0|1'}
                        , 'dayfirst' : {"docs" : "Is the day before the month (when ambiguous). 1 = Yes, 0 = No (default)", 'type' : int, 'options' : '0|1'}}

    def __init__(self, session, config, parent):
        SimpleTokenizer.__init__(self, session, config, parent)
        default = self.get_default(session, 'datetime')
        self.fuzzy = self.get_setting(session, 'fuzzy')
        self.dayfirst = self.get_setting(session, 'dayfirst')
        self.normalisedDateRe = re.compile('(?<=\d)xx+', re.UNICODE)
        self.isoDateRe = re.compile('''
        ([0-2]\d\d\d)        # match any year up to 2999
        (0[1-9]|1[0-2]|xx)?      # match any month 01-12 or xx
        (0[1-9]|[1-2][0-9]|3[0-1]|xx)?  # match any date up to 01-31 or xx
        ''', re.VERBOSE|re.IGNORECASE|re.UNICODE)
        if default:
            self.default = dateparser.parse(default.encode('utf-8'), dayfirst=self.dayfirst, fuzzy=self.fuzzy)
        else:
            self.default = dateparser.parse('2000-01-01', fuzzy=True)
            
    def _convertIsoDates(self, mo):
        dateparts = [mo.group(1)]
        for x in range(2,4):
            if mo.group(x):
                dateparts.append(mo.group(x))
        return '-'.join(dateparts)
    
    def _tokenize(self, data, default=None):
        if default is None:
            default = self.default
        # deconstruct data word by word and feed to parser until success.
        # Must be a better way to do this..., but for now...
        tks = []
        wds = data.split()
        while (len(wds)):
            for x in range(len(wds), 0, -1):
                txt = ' '.join(wds[:x]).encode('utf-8')
                try:
                    t = dateparser.parse(txt, default=default, 
                                         dayfirst=self.dayfirst, 
                                         fuzzy=self.fuzzy).isoformat()
                except:
                    continue
                else:
                    tks.append(t)
                    break
            wds = wds[x:]
        return tks

    def process_string(self, session, data):
        # convert ISO 8601 date elements to extended format (YYYY-MM-DD)
        # for better recognition by date parser
        data = self.isoDateRe.sub(self._convertIsoDates, data)
        if len(data):
            # a range?
            # use a new default, just under a year on for the end of the range
            td = timedelta(days=364, hours=23, minutes=59, seconds=59, 
                           microseconds=999999)
            if data.count('/') == 1:
                bits = data.split('/')
                tks = self._tokenize(bits[0]) + \
                    self._tokenize(bits[1], self.default+td)
            elif data.count('-') == 1:
                bits = data.split('-')
                tks = self._tokenize(bits[0]) + \
                    self._tokenize(bits[1], self.default+td)
            else:
                tks = []
            if len(tks):
                return tks
        return self._tokenize(data)


class PythonTokenizer(OffsetTokenizer):
    """ Tokenize python source code into token/TYPE with offsets """

    def __init__(self, session, config, parent):
        OffsetTokenizer.__init__(self, session, config, parent)
        self.ignoreTypes = [tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE, tokenize.NL, tokenize.ENDMARKER]

    def process_string(self, session, data):
        io = StringIO.StringIO(data)
        toks = []        
        posns = []
        totalChrs = 0
        currLine = 0
        prevLineLen = 0
        for tok in tokenize.generate_tokens(io.readline):
            (ttype, txt, start, end, lineTxt) = tok
            if start[0] != currLine:
                totalChrs += prevLineLen
                prevLineLen = len(lineTxt)
                currLine = start[0]
            # maybe store token
            if not ttype in self.ignoreTypes:
                tname = tokenize.tok_name[ttype]
                if tname == "NAME" and keyword.iskeyword(txt):
                    toks.append("%s/KEYWORD" % (txt))                    
                else:
                    toks.append("%s/%s" % (txt, tokenize.tok_name[ttype]))
                posns.append(totalChrs + start[1])
        return (toks, posns)
                

