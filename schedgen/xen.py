import os

import schedgen.config as config
from subprocess import Popen, PIPE
from schedgen.utils import *

def fakesetup(dom0_cores=1, num_domu=1, domu_cores=1):
    conf = ''
    conf = "Name     ID  Mem VCPUs  State Time(s)\n"
    conf += "Domain-0  0 2042     %d r-----    10.5\n" % (dom0_cores,)
    for i in xrange(num_domu):
        conf += "vm%d %d 1024 %d -b---- 610.7\n" % (i + 1, i + 1, domu_cores)
    return conf.strip()


def get_dom_info_base(info = ''):
    # Use Xen's xl command to get a dump of currently running domains
    cmd = 'xl list' if info == '' else 'echo \'' + info + '\''
    p = os.popen(cmd + " | grep -v Name | awk '{print $1 \",\" $2 \",\" $4}'")
    info = p.read()
    p.close()

    # Build a nice dict from this data
    domains = {}
    for line in info.split('\n'):
        if line != "" and line[0] != '#':
            data = line.split(',')
            domains[data[0]] = {}
            domains[data[0]]['id'] = int(data[1])
            domains[data[0]]['num_vcpus'] = int(data[2])

    return domains

# Get domain information of all domains currently running
def get_dom_info(conf, info = ''):
    # Use Xen's xl command to get a dump of currently running domains
    cmd = 'xl list' if info == '' else 'echo \'' + info + '\''
    p = os.popen(cmd + " | grep -v Name | awk '{print $1 \",\" $2 \",\" $4}'")
    info = p.read()
    p.close()

    # Build a nice dict from this data
    domains = {}
    for line in info.split('\n'):
        if line != "" and line[0] != '#':
            data = line.split(',')
            domains[data[0]] = {}
            domains[data[0]]['id'] = int(data[1])
            domains[data[0]]['num_vcpus'] = int(data[2])

    # Add additional information for Xfair using latency.conf
    with open (conf, 'r') as f:
        data = f.read().split('\n')
        for line in data:
            if line != "":
                d = line.split(':')
                if d[0] in domains:
                    domains[d[0]]['burstable'] = bool(d[1] == '1')
                    domains[d[0]]['latency'] = MICROSECS(int(d[2]))
                    domains[d[0]]['utilization'] = float(d[3])
                    domains[d[0]]['affinity'] = [int(x) for x in d[4].split(',')]
    t2_vms = []
    for k, v in domains.iteritems():
        if 'utilization' not in v:
            t2_vms.append(k)
    for v in t2_vms:
        domains.pop(v, None)

    return domains

def dump_dom_info(info):
    print "{:<15} {:<5} {:>5} {:>10} {:>10} {:>10}".format('Name','ID','VCPUs', 'Lat', 'Util', 'Affinity')
    for k, v in info.iteritems():
        print "{:<15} {:<5} {:>5} {:>10} {:>10} {:>10}".format(k, v['id'], v['num_vcpus'], v['latency'], v['utilization'], ''.join(str(x) for x in v['affinity']))


def get_max_cpus():
    info = os.popen("xl info | grep nr_cpus | cut -d\: -f 2 | tr -d ' '").read()
    return int(info)

def get_cpu_topology():
    info = os.popen("xenpm get-cpu-topology | tail -n +2 | sed -e 's/CPU//g' | awk '{ print $1,$2,$3,$4}'").read()
    # CPU, core, socket, node
    info = [[int(y) for y in x.split(' ')] for x in info.split('\n') if x != '']
    return info

def submit_schedule(s):
    p = Popen([config.CONFIG_SCHEDULE_ELF, 'f'],
              stdout=PIPE, stdin=PIPE)
    p.stdin.write(s)
    p.communicate()[0]
    p.stdin.close()
    return p.returncode

