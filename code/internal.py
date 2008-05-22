
storeTypes = ['authStore', 'objectStore', 'configStore', 'recordStore', 'documentStore', 'resultSetStore', 'indexStore', 'queryStore']
collTypes = ['server', 'database', 'index', 'workflow']
processTypes = ['preParser', 'parser', 'normalizer', 'extractor', 'transformer', 'documentFactory', 'xpathProcessor', 'logger', 'tokenMerger', 'tokenizer']


# modules in which we can find configurable objects
modules = ['database', 'documentFactory', 'documentStore', 'extractor', 'index', 'indexStore', 'logger', 'normalizer', 'objectStore', 'parser', 'postgres', 'preParser', 'protocolMap', 'queryFactory', 'queryStore', 'recordStore', 'resultSetStore', 'server', 'transformer', 'workflow', 'xpathProcessor', 'textmining.tmNormalizer', 'textmining.tmDocumentFactory', 'textmining.tmPreParser', 'textmining.tmTransformer', 'datamining.dmPreParser', 'datamining.dmTransformer', 'grid.srbIndex', 'grid.srbStore']


cheshireVersion = (0,9,10)

cheshireRoot = "/home/cheshire/cheshire3"
cheshireCode = "/home/cheshire/cheshire3/code/extensions"
cheshireDbs = "/home/cheshire/cheshire3/dbs"
cheshireWww = "/home/cheshire/cheshire3/www"


class Architecture(object):
    # Facilitate Architecture Introspection 

    moduleObjects = []
    classDefns = []

    def __init__(self):
        self.moduleObjects = []
        self.classDefns = []

    def discover_classes(self):
        # cache, as no new code before restart
        # (barring total psychedelic craziosity)
        if self.classDefns:
            return self.classDefns

        for m in modules:
            try:
                if m.find('.') == -1:
                    self.moduleObjects.append(__import__(m))
                else:
                    base = __import__(m)
                    (m, mod) = m.split('.', 1)
                    self.moduleObjects.append(getattr(base, mod))
            except:
                print "Could not import module: %s" % m


        classes = []
        for mod in self.moduleObjects:
            for mb in dir(mod):
                bit = getattr(mod, mb)
                if type(bit) == type:
                    # found a class defn
                    if bit.__module__ == mod.__name__:
                        # found a class in this module
                        if hasattr(bit, '_possiblePaths'):
                            # C3Object probably ancestor
                            # now look for baseClass
                            bases = list(bit.__bases__)
                            while bases:
                                base = bases.pop(0)
                                if base.__module__ == 'baseObjects':
                                    classes.append((base.__name__, bit))
                                    break
                                else:
                                    bases.extend(list(base.__bases__))
        classes.sort()
        self.classDefns = classes
        return classes
                        

    def find_class(self, name):
        bits  = name.split('.')
        try:
            loaded = __import__(bits[0])
        except ImportError:
            # no such module, default error is appropriate
            raise
        for moduleName in bits[1:-1]:
            loaded = getattr(loaded, moduleName)

        className = bits[-1]
        try:
            cls = getattr(loaded, className)
        except AttributeError:
            # no such class
            raise AttributeError("Module %s has no class %s" % (moduleName, className))
        if not isinstance(cls, type):
            # not a class defn
            raise AttributeError("Class %s is not a C3 Object" % name)
        return cls


    def find_params(self, cls):
        try:
            paths = cls._possiblePaths
            settings = cls._possibleSettings
            defaults = cls._possibleDefaults
        except:
            # not a c3object
            raise AttributeError("Class %s is not a C3 Object" % name)

        bases = list(cls.__bases__)

        while bases:
            cls = bases.pop(0)
            try:
                for (k,v) in cls._possiblePaths.iteritems():
                    if not paths.has_key(k):
                        paths[k] = v                        
                for (k,v) in cls._possibleSettings.iteritems():
                    if not settings.has_key(k):
                        settings[k] = v
                for (k,v) in cls._possibleDefaults.iteritems():
                    if not defaults.has_key(k):
                        defaults[k] = v
            except:
                # not a c3object, eg mix-ins/interfaces/etc
                if cls.__name__ == "ArrayIndex":
                    raise
                
                continue
            bases.extend(list(cls.__bases__))
        return (paths, settings, defaults)

defaultArchitecture = Architecture()