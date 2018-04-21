import os
import errno
from itertools import izip

def ms2ns(x):
    return x * 1000000

def ms2us(x):
    return x * 1000

def ns2ms(x):
    return x / 1000000.0

def us2ns(x):
    return x * 1000

# We use nanoseconds as the base time unit. These are utilities to convert
# from any unit to the base time unit. The base time unit is the same used
# by Xen so it prevents stupid errors in the table during unit conversion.
def SECONDS(s):
    return (s) * 1000000000
def MILLISECS(ms):
    return (ms) * 1000000
def MICROSECS(us):
    return (us) * 1000
def NANOSECS(ns):
    return (ns)

# Calculate the greatest common divisor of two numbers
def gcd(m, n):
    while m > 0:
        tmp = m
        m = n % m
        n = tmp
    return n

# Calculate the lowest common multiple of two numbers
def lcm(m, n):
    return (m / gcd(m, n)) * n

# Make a folder path recursively without throwing errors
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc: # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else: raise

def write_log(folder, fname, data):
    mkdir_p(folder)
    with open(folder + '/' + fname, "w") as f:
        f.write(data)


def pairwise(iterable):
    "s -> (s0, s1), (s2, s3), (s4, s5), ..."
    a = iter(iterable)
    return izip(a, a)
