import schedgen.utils as utils
from schedgen.utils import *
from schedgen.config import *
import schedgen.xen as xen
import schedgen.task as task

import schedcat.mapping.apa as apa

import sys
import os
import itertools

# Describes metadata for a single VCPU (specifically mapped cores)
class VCPUInfo:
    __slots__ = ('dom', 'vcpu', 'cores', 'id')
    def __init__(self, dom, vcpu, cores, id, burstable):
        self.dom = dom
        self.vcpu = vcpu
        self.cores = cores
        self.index = id
        self.burstable = burstable

    def __repr__(self):
        return '[' + str(self.dom) + '.' + str(self.vcpu) + ': ' + str(self.cores) + ']'

# A single job that is released
class Job:
    __slots__ = ('remaining_budget', 'is_split_task', 'parent', 'release', 'deadline', 'task')
    def __init__(self, task):
        self.remaining_budget = task.cost
        # This is a child task. Adjust phases for the splits
        if not hasattr(task, 'release_time'):
            parent = task.original_task
            parent.split_tasks[0].phase = 0
            parent.split_tasks[1].phase = parent.split_tasks[0].deadline
            parent.split_tasks[0].release_time = 0
            parent.split_tasks[1].release_time = 0
            parent.split_tasks[0].allocations = []
            parent.split_tasks[1].allocations = []
        self.release = task.release_time
        if hasattr(task, 'phase'):
            self.release += task.phase
        self.deadline = task.deadline
        self.task = task

# An allocation on a specific core for a specific VCPU
class Allocation:
    __slots__ = ('aid', 'core', 't_from', 't_to', 'task', 'dom_id', 'vcpu_id')
    newid = itertools.count().next
    def __init__(self, task, t_from, t_to, core):
        self.aid = Allocation.newid()
        self.core = core
        self.task = task
        self.t_from = int(t_from)
        self.t_to = int(t_to)
        if task == None:
            self.dom_id = 32767
            self.vcpu_id = core
        else:
            self.dom_id = task.dom_id
            self.vcpu_id = task.vcpu_id

    def is_same_task(self, slot):
        dom_id = self.task.dom_id
        vcpu_id = self.task.vcpu_id

        sdom_id = slot.task.dom_id
        svcpu_id = slot.task.vcpu_id

        return (sdom_id == dom_id and svcpu_id == vcpu_id)

    def pretty(self):
        dom_id = self.dom_id
        vcpu_id = self.vcpu_id
        return str(int(self.t_from)) + ' ' + \
               str(int(self.t_to)) + ' ' + \
               str(int(self.t_to - self.t_from)) + ' ' + \
               str(dom_id) + ' ' + \
               str(vcpu_id) + '\n'

    def __repr__(self):
        dom_id = self.dom_id
        vcpu_id = self.vcpu_id
        return str(self.aid) + ':' + \
               str(dom_id) + ':' + \
               str(vcpu_id) + ':' + \
               str(int(self.t_from)) + ':' + \
               str(int(self.t_to))

# A single slice with at most 2 VCPU slots and 1 idle slot
class Slice:
    __slots__ = ('core', 't_from', 't_to', 'size', 'left_alloc', 'right_alloc', 'idle_middle', 'boundary')
    def __init__(self, core, t_from, t_to, left_alloc, idle_middle, right_alloc, boundary):
        self.core = core
        self.t_from = t_from
        self.t_to = t_to
        self.size = t_to - t_from
        self.left_alloc = left_alloc
        self.right_alloc = right_alloc
        self.idle_middle = idle_middle
        self.boundary = boundary

    def __repr__(self):
        left = -1 if self.left_alloc == None else self.left_alloc.aid
        right = -1 if self.right_alloc == None else self.right_alloc.aid
        return 'Slice(CPU%d:%d-%d (%s %s %s))' % (self.core, self.t_from, self.t_to, self.left_alloc, self.idle_middle, self.right_alloc)

# A single slice with at most 2 VCPU slots and 1 idle slot
class L2Slice:
    __slots__ = ('core', 't_from', 't_to', 'size', 'left_alloc', 'right_alloc', 'idle_middle', 'boundary')
    def __init__(self, core, t_from, t_to, left_alloc, idle_middle, right_alloc, boundary):
        self.core = core
        self.t_from = t_from
        self.t_to = t_to
        self.size = t_to - t_from
        self.left_alloc = left_alloc
        self.right_alloc = right_alloc
        self.idle_middle = idle_middle
        self.boundary = boundary

    def __repr__(self):
        return 'Slice(CPU%d:%d-%d (%s || %s || %s))' % (self.core, self.t_from, self.t_to, self.left_alloc, self.idle_middle, self.right_alloc)

# The split callback so we can add custom attributes to split tasks
def split_task(original, t1, t2):
    t1.dom_id = original.dom_id
    t1.vcpu_id = original.vcpu_id
    t2.dom_id = original.dom_id
    t2.vcpu_id = original.vcpu_id

def partition_with_splits(ts):
    # Use worst-fit-decreasing APA partitioning with C=D splitting
    fail, maps = apa.edf_worst_fit_decreasing_difficulty(ts, with_splits=True,
                                                    split_callback=split_task)
    assert fail == set(), 'WARN: some tasks failed mapping: ' + str(fail)

    # Figure out all the processors on which a task is mapped
    vcpu_list = {}
    for i in maps:
        for t in maps[i]:
            name = '%d.%d' % (t.dom_id, t.vcpu_id)
            if name not in vcpu_list:
                vcpu_list[name] = []
            vcpu_list[name].append(i)

    # Now generate a VCPU info list from the mapping info
    splits = []
    vinfo_list = []
    i = 0
    for k, v in vcpu_list.iteritems():
        dom = k.split('.')[0]
        vcpu = k.split('.')[1]
        burstable = [x for x in ts if x.dom_id == int(dom) and x.vcpu_id == int(vcpu)][0].burstable
        vinfo_list.append(VCPUInfo(dom, vcpu, v, i, burstable))
        if len(v) > 1:
            splits.append([dom, vcpu])
        i += 1

    return maps, vinfo_list, splits


def find_in_vinfo(vinfo, dom, vcpu):
    for i, v in enumerate(vinfo):
        if int(v.dom) == int(dom) and int(v.vcpu) == int(vcpu):
            return i
    # If nothing is found return >= len(vinfo)
    return len(vinfo)

def schedule_serialize(schedinfo):
    sched = ''
    schedule = schedinfo['tables']
    sched += str(schedinfo['length']) + '\n'
    for i, core in enumerate(schedule):
        if len(core) == 0:
            sched += '-1:0:' + str(schedinfo['length']) + ':0\n'
            continue
        for slot in core:
            sched += str(slot) + ' '
        if i != len(schedule) - 1:
            sched += '\n'
    return sched

def opt_coalesce_slots(schedinfo):
    osched = [[] for _ in xrange(len(schedinfo['tables']))]
    schedule = schedinfo['tables']

    for i, core in enumerate(schedule):
        last = None
        for slot in core:
            if last != None:
                dom_id = slot.task.dom_id
                vcpu_id = slot.task.vcpu_id

                ldom_id = last.task.dom_id
                lvcpu_id = last.task.vcpu_id

                if slot.is_same_task(last):
                    last.t_to = slot.t_to
                    continue
                else:
                    osched[i].append(last)
            last = slot
        osched[i].append(last)
    return {'tables': osched, 'length': schedinfo['length']}

def opt_idle_threshold(schedinfo):
    osched = [[] for _ in xrange(len(schedinfo['tables']))]
    schedule = schedinfo['tables']

    for i, core in enumerate(schedule):
        last = None
        for slot in core:
            if last != None:
                idle_time = slot.t_from - last.t_to
                if idle_time > 0 and idle_time < CONFIG_COALESCE_THRESHOLD:
                    last.t_to = slot.t_from
            last = slot
    return {'tables': schedule, 'length': schedinfo['length']}

def opt_extend_to_hyperperiod(schedinfo):
    osched = [[] for _ in xrange(len(schedinfo['tables']))]
    schedule = schedinfo['tables']

    for i, core in enumerate(schedule):
        if len(core) == 0:
            break
        last_slot = core[-1]
        if last_slot.t_to < schedinfo['length']:
            last_slot.t_to = schedinfo['length']

    return {'tables': schedinfo['tables'], 'length': schedinfo['length']}

def opt_add_idle_slots(schedinfo):
    osched = [[] for _ in xrange(len(schedinfo['tables']))]
    schedule = schedinfo['tables']

    osched = []
    for i, core in enumerate(schedule):
        c = []
        t = 0
        for slot in core:
            if slot.t_from > t:
                c.append(Allocation(None, t, slot.t_from, i))
            c.append(slot)
            t = slot.t_to
        if t < schedinfo['length']:
            c.append(Allocation(None, t, schedinfo['length'], i))
        osched.append(c)

    if os.getenv('DEBUG', '') != '':
        print osched
    return {'tables': osched, 'length': schedinfo['length']}

# Optimize a given table through an ordered series of optimization functions
def optimize(schedinfo):
    # The set of optimization passes to run
    passes = [
        opt_idle_threshold,
        opt_add_idle_slots
    ]

    for f in passes:
        schedinfo = f(schedinfo)
    return schedinfo

# Convert a slot id into an offset
def sid_to_slot(slot, slots):
    for core in slots:
        for i, s in enumerate(core):
            if s is slot:
                return i
    print 'FATAL: did not find slot: ' + str(slot)
    sys.exit(1)

def l2_sid_to_slot(slot, slots):
    for i, s in enumerate(slots):
        if s == slot:
            return i
    print 'FATAL: did not find slot: ' + str(slot)
    sys.exit(1)

# Find all slots within an interval on a particular core
def find_in_interval(core, t_min, t_max):
    interval = []
    for s in core:
        if s.t_from < t_max and s.t_to >= t_min:
            interval.append(s)
    return interval

def slice_schedule(sched):
    slice_lens = [task.get_slice_size(s, sched['length']) for s in sched['tables']]
    #slice_len = task.get_slice_size(sched)
    sched_len = sched['length']
    if os.getenv('DEBUG', '') != '':
        print slice_lens

    slices = [[] for i in xrange(len(sched['tables']))]
    for i, core in enumerate(sched['tables']):
        if os.getenv('DEBUG', '') != '':
            print 'CORE' + str(i) + ' (slice length = ' + str(slice_lens[i]) + ')'
        # Iterate over intervals of the slice length for this core
        for t in xrange(0, sched_len, slice_lens[i]):
            # Bounds for this slice
            tmin = t
            tmax = tmin + slice_lens[i]

            # Get all slots in this interval
            interval = find_in_interval(core, tmin, tmax)

            if len(interval) == 0:
                # There should always be at least one slot in a given interval
                # since our optimization passes ensure a "fully covered"
                # schedule with no gaps in it.
                print 'FATAL: no slot in interval: [%d, %d)' % (tmin, tmax)
                sys.exit(1)
            elif len(interval) == 1:
                # If there is only one slot, then it fully covers the entire
                # slice. In this case, we just set the left pointer.
                v = interval[0]
                s = Slice(i, tmin, tmax, v, None, None, 0)
                slices[i].append(s)
                if os.getenv('DEBUG', '') != '':
                    print s
            elif len(interval) == 2:
                v1 = interval[0]
                v2 = interval[1]
                boundary = v2.t_from - tmin
                s = Slice(i, tmin, tmax, v1, None, v2, boundary)
                slices[i].append(s)
                if os.getenv('DEBUG', '') != '':
                    print s
            elif len(interval) == 3:
                v1 = interval[0]
                v2 = interval[1]
                v3 = interval[2]
                boundary = v2.t_from - tmin
                assert v2.dom_id == 32767, 'FATAL: middle is not id'
                s = Slice(i, tmin, tmax, v1, v2, v3, boundary)
                slices[i].append(s)
                if os.getenv('DEBUG', '') != '':
                    print s
            else:
                print 'FATAL: over three slots found: [%d, %d)' % (tmin, tmax)
                sys.exit(1)
    return slices, slice_lens

def task_to_vinfo_offset(task, vinfo):
    i = 0
    for v in vinfo:
        if int(v.dom) == task.dom_id and int(v.vcpu) == task.vcpu_id:
            return i
        i += 1
    return None

def gen_l2_schedule(ts, mapping, vlist, sched, split_tasks):
    def alloc_compare(a1, a2):
        if a1.t_from < a2.t_from:
            return -1
        elif a1.t_from > a2.t_from:
            return 1
        else:
            return 0

    l2_sched = {}
    l2_sched['tables'] = {}
    l2_sched['shortest'] = {}
    for core in mapping:
        percpu_vlist = [x for x in vlist if core in x.cores]

        # Search split_tasks list for any of these vCPUs:
        always_restrict = []
        for i, v in enumerate(percpu_vlist):
            for t in split_tasks:
                if v.dom == t[0] and v.vcpu == t[1]:
                    always_restrict.append(i)

        allocations = [x for x in sched['tables'][core] if x.task == None]
        for task in mapping[core]:
            allocations += task.allocations
        allocations = sorted(allocations, cmp=alloc_compare)

        points = {}
        for a in allocations:
            if a.t_from not in points:
                points[a.t_from] = []
            if a.t_to not in points:
                points[a.t_to] = []
            points[a.t_from].append(['+', a.task])
            points[a.t_to].append(['-', a.task])
            #print a.task, a.t_from, a.t_to

        # Generate a list of L2 allocations
        l2_sched['tables'][core] = []
        a_start_time = 0
        curr_restrict = []
        old_restrict = []
        k = 0
        for p in sorted(points):
            old_restrict = curr_restrict[:]
            for op in points[p]:
                if op[1] == None:
                    continue
                if op[0] == '+':
                    curr_restrict.append(op[1])
                elif op[0] == '-':
                    curr_restrict.remove(op[1])

            if k == (len(sorted(points)) - 1) and op[1] == None:
                l2_sched['tables'][core].append([a_start_time, p, list(set([task_to_vinfo_offset(t, percpu_vlist) for t in old_restrict] + always_restrict))])
                l2_sched['length'] = p
                if p - a_start_time < l2_sched['shortest']:
                    if core not in l2_sched['shortest']:
                        l2_sched['shortest'][core] = p - a_start_time
                    else:
                        l2_sched['shortest'][core] = p - a_start_time

            # If the set of restricted VMs change, create allocation
            if sorted(set(old_restrict)) != sorted(set(curr_restrict)):
                if k == 0:
                    a_start_time = 0
                    k += 1
                    continue
                else:
                    l2_sched['tables'][core].append([a_start_time, p, list(set([task_to_vinfo_offset(t, percpu_vlist) for t in old_restrict] + always_restrict))])
                    if p - a_start_time < l2_sched['shortest']:
                        if core not in l2_sched['shortest']:
                            l2_sched['shortest'][core] = p - a_start_time
                        else:
                            l2_sched['shortest'][core] = p - a_start_time
                    a_start_time = p
            k += 1
        print l2_sched['tables'][core]
    return l2_sched

def l2_find_in_interval(sched, tmin, tmax):
    interval = []
    for s in sched:
        if s[0] < tmax and s[1] >= tmin:
            interval.append(s)
    return interval

def slice_l2_schedule(l2_sched):
    slices = [[] for i in xrange(len(l2_sched['tables']))]
    slice_lens = [l2_sched['shortest'][x] for x in l2_sched['shortest']]

    for i, core in enumerate(l2_sched['tables']):
        # Iterate over intervals of the slice length for this core
        for t in xrange(0, l2_sched['length'], slice_lens[i]):
            # Bounds for this slice
            tmin = t
            tmax = tmin + slice_lens[i]

            # Get all slots in this interval
            interval = l2_find_in_interval(l2_sched['tables'][core], tmin, tmax)

            if len(interval) == 0:
                # There should always be at least one slot in a given interval
                # since our optimization passes ensure a "fully covered"
                # schedule with no gaps in it.
                print 'FATAL: no slot in interval: [%d, %d)' % (tmin, tmax)
                sys.exit(1)
            elif len(interval) == 1:
                # If there is only one slot, then it fully covers the entire
                # slice. In this case, we just set the left pointer.
                v = interval[0]
                s = L2Slice(i, tmin, tmax, v, None, None, 0)
                slices[i].append(s)
                if os.getenv('DEBUG', '') != '':
                    print s
            elif len(interval) == 2:
                v1 = interval[0]
                v2 = interval[1]
                boundary = v2[0] - tmin
                s = L2Slice(i, tmin, tmax, v1, None, v2, boundary)
                slices[i].append(s)
                if os.getenv('DEBUG', '') != '':
                    print s
            elif len(interval) == 3:
                v1 = interval[0]
                v2 = interval[1]
                v3 = interval[2]
                boundary = v2[0] - tmin
                s = L2Slice(i, tmin, tmax, v1, v2, v3, boundary)
                slices[i].append(s)
                if os.getenv('DEBUG', '') != '':
                    print s
            else:
                print 'FATAL: over three slots found: [%d, %d)' % (tmin, tmax)
                sys.exit(1)
    return slices, slice_lens

def vcpu_list_to_str(vl):
    s = ''
    for v in vl:
        s += v.dom + ' '
        s += v.vcpu + ' '
        scores = [str(x) for x in v.cores]
        s += ','.join(scores) + '\n'
    return s

def slices_to_str(slices):
    s = ''
    for core in slices:
        for i, sl in enumerate(core):
            s += str(sl)
            if i != len(core) - 1:
                s += ' '
        s += '\n'
    return s

