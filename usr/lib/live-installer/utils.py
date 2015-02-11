
import subprocess
import urllib2
import re

# https://docs.python.org/2.7/library/subprocess.html

def shell_exec_popen(command, kwargs={}):
    print 'Executing:', command
    return subprocess.Popen(command, shell=True,
                            stdout=subprocess.PIPE, **kwargs)

def shell_exec(command):
    print 'Executing:', command
    return subprocess.call(command, shell=True)

def getoutput(command):
    #return shell_exec(command).stdout.read().strip()
    output = subprocess.check_output(command, shell=True).strip().split('\n')
    if len(output) == 1:
        # Single line: return as string
        output = output[0]
    return output

def chroot_exec(command):
    command = command.replace('"', "'").strip()  # FIXME
    return shell_exec('chroot /target/ /bin/sh -c "%s"' % command)

def memoize(func):
    """ Caches expensive function calls.

    Use as:

        c = Cache(lambda arg: function_to_call_if_yet_uncached(arg))
        c('some_arg')  # returns evaluated result
        c('some_arg')  # returns *same* (non-evaluated) result

    or as a decorator:

        @memoize
        def some_expensive_function(args [, ...]):
            [...]

    See also: http://en.wikipedia.org/wiki/Memoization
    """
    class memodict(dict):
        def __call__(self, *args):
            return self[args]
        def __missing__(self, key):
            ret = self[key] = func(*key)
            return ret
    return memodict()

def get_config_dict(file, key_value=re.compile(r'^\s*(\w+)\s*=\s*["\']?(.*?)["\']?\s*(#.*)?$')):
    """Returns POSIX config file (key=value, no sections) as dict.
    Assumptions: no multiline values, no value contains '#'. """
    d = {}
    with open(file) as f:
        for line in f:
            try: key, value, _ = key_value.match(line).groups()
            except AttributeError: continue
            d[key] = value
    return d

# [XK] Check for internet connection
def hasInternetConnection(testUrl='http://google.com'):
    try:
        urllib2.urlopen(testUrl, timeout=1)
        return True
    except urllib2.URLError:
        pass
    return False

# [XK] Check if running in VB
def runningInVirtualBox():
    dmiBIOSVersion = getoutput("dmidecode -t0 | grep 'Version:' | awk -F ': ' '{print $2}'")
    dmiSystemProduct = getoutput("dmidecode -t1 | grep 'Product Name:' | awk -F ': ' '{print $2}'")
    dmiBoardProduct = getoutput("dmidecode -t2 | grep 'Product Name:' | awk -F ': ' '{print $2}'")
    if dmiBIOSVersion != "VirtualBox" and dmiSystemProduct != "VirtualBox" and dmiBoardProduct != "VirtualBox":
        return False
    return True

# [XK] Check if is 64-bit system
def isAmd64():
    machine = getoutput("uname -m")
    if machine == "x86_64":
        return True
    return False

def getBootCommandParameters():
    parms = []
    not_allowed = ['live', 'ram', 'single', 'ignore', 'config', 'components', 'memtest']
    cmd = "cat /proc/cmdline"
    ret = getoutput(cmd).split(" ")
    for line in ret:
        if len(line) > 2:
            add = True
            for s in not_allowed:
                if s in line:
                    add = False
                    break
            if add:
                parms.append(line)
    return " ".join(parms)
