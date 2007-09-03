################################################## 
# GoogleSearch_services_types.py 
# generated by ZSI.wsdl2python 
# 
# 
##################################################


import ZSI
from ZSI.TCcompound import Struct

############################## 
# targetNamespace 
#
# urn:GoogleSearch 
##############################


# imported as: ns1
class urn_GoogleSearch:
    targetNamespace = 'urn:GoogleSearch'

    class DirectoryCategory_Def(ZSI.TCcompound.Struct):
        schema = 'urn:GoogleSearch'
        type = 'DirectoryCategory'

        def __init__(self, name=None, ns=None, **kw):
            # internal vars
            self._fullViewableName = None
            self._specialEncoding = None

            TClist = [ZSI.TC.String(pname="fullViewableName",aname="_fullViewableName"), ZSI.TC.String(pname="specialEncoding",aname="_specialEncoding"), ]

            oname = name

            if name:
                aname = '_%s' % name
                if ns:
                    oname += ' xmlns="%s"' % ns
                else:
                    oname += ' xmlns="%s"' % self.__class__.schema
            else:
                aname = None

            ZSI.TCcompound.Struct.__init__(self, self.__class__, TClist,
                                           pname=name, inorder=0,
                                           aname=aname, oname=oname,
                                           **kw)

    class ResultElementArray_Def(ZSI.TCcompound.Array):
        def __init__(self, name = None, ns = None, **kw):
            ZSI.TCcompound.Array.__init__(self, 'typens:ResultElement[]', ns1.ResultElement_Def(name=None), pname=name, aname='_%s' % name, oname='%s xmlns="urn:GoogleSearch"' % name, **kw)

    class DirectoryCategoryArray_Def(ZSI.TCcompound.Array):
        def __init__(self, name = None, ns = None, **kw):
            ZSI.TCcompound.Array.__init__(self, 'typens:DirectoryCategory[]', ns1.DirectoryCategory_Def(name=None), pname=name, aname='_%s' % name, oname='%s xmlns="urn:GoogleSearch"' % name, **kw)

    class ResultElement_Def(ZSI.TCcompound.Struct):
        schema = 'urn:GoogleSearch'
        type = 'ResultElement'

        def __init__(self, name=None, ns=None, **kw):
            # internal vars
            self._summary = None
            self._URL = None
            self._snippet = None
            self._title = None
            self._cachedSize = None
            self._relatedInformationPresent = None
            self._hostName = None
            self._directoryCategory = None
            self._directoryTitle = None

            TClist = [ZSI.TC.String(pname="summary",aname="_summary"), ZSI.TC.String(pname="URL",aname="_URL"), ZSI.TC.String(pname="snippet",aname="_snippet"), ZSI.TC.String(pname="title",aname="_title"), ZSI.TC.String(pname="cachedSize",aname="_cachedSize"), ZSI.TC.Boolean(pname="relatedInformationPresent",aname="_relatedInformationPresent"), ZSI.TC.String(pname="hostName",aname="_hostName"), ns1.DirectoryCategory_Def(name="directoryCategory", ns=ns), ZSI.TC.String(pname="directoryTitle",aname="_directoryTitle"), ]

            oname = name

            if name:
                aname = '_%s' % name
                if ns:
                    oname += ' xmlns="%s"' % ns
                else:
                    oname += ' xmlns="%s"' % self.__class__.schema
            else:
                aname = None

            ZSI.TCcompound.Struct.__init__(self, self.__class__, TClist,
                                           pname=name, inorder=0,
                                           aname=aname, oname=oname,
                                           **kw)

    class GoogleSearchResult_Def(ZSI.TCcompound.Struct):
        schema = 'urn:GoogleSearch'
        type = 'GoogleSearchResult'

        def __init__(self, name=None, ns=None, **kw):
            # internal vars
            self._documentFiltering = None
            self._searchComments = None
            self._estimatedTotalResultsCount = None
            self._estimateIsExact = None
            self._resultElements = None
            self._searchQuery = None
            self._startIndex = None
            self._endIndex = None
            self._searchTips = None
            self._directoryCategories = None
            self._searchTime = None

            TClist = [ZSI.TC.Boolean(pname="documentFiltering",aname="_documentFiltering"), ZSI.TC.String(pname="searchComments",aname="_searchComments"), ZSI.TCnumbers.Iint(pname="estimatedTotalResultsCount",aname="_estimatedTotalResultsCount"), ZSI.TC.Boolean(pname="estimateIsExact",aname="_estimateIsExact"), ns1.ResultElementArray_Def(name="resultElements", ns=ns), ZSI.TC.String(pname="searchQuery",aname="_searchQuery"), ZSI.TCnumbers.Iint(pname="startIndex",aname="_startIndex"), ZSI.TCnumbers.Iint(pname="endIndex",aname="_endIndex"), ZSI.TC.String(pname="searchTips",aname="_searchTips"), ns1.DirectoryCategoryArray_Def(name="directoryCategories", ns=ns), ZSI.TCnumbers.FPdouble(pname="searchTime",aname="_searchTime"), ]

            oname = name

            if name:
                aname = '_%s' % name
                if ns:
                    oname += ' xmlns="%s"' % ns
                else:
                    oname += ' xmlns="%s"' % self.__class__.schema
            else:
                aname = None

            ZSI.TCcompound.Struct.__init__(self, self.__class__, TClist,
                                           pname=name, inorder=0,
                                           aname=aname, oname=oname,
                                           **kw)

# define class alias for subsequent ns classes
ns1 = urn_GoogleSearch



