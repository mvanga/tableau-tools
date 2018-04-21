from schedgen.utils import *
import schedcat.model.tasks as tasks

import os

CONFIG_UTIL_GRANULARITY = 100000

# Possible candidates to pick from. Values are in system base time (nsec)
# Hyperperiod of these values ~= 102ms. This is used both for the generation
# of candidate periods and candidate slice sizes.
candidates = [
    NANOSECS(100100), NANOSECS(102600), NANOSECS(103740), NANOSECS(103950),
    NANOSECS(105336), NANOSECS(108108), NANOSECS(108680), NANOSECS(109725),
    NANOSECS(111150), NANOSECS(112860), NANOSECS(114114), NANOSECS(119700),
    NANOSECS(120120), NANOSECS(122265), NANOSECS(122850), NANOSECS(124488),
    NANOSECS(125400), NANOSECS(128700), NANOSECS(129675), NANOSECS(131670),
    NANOSECS(133380), NANOSECS(135135), NANOSECS(135850), NANOSECS(138600),
    NANOSECS(141075), NANOSECS(143640), NANOSECS(146300), NANOSECS(146718),
    NANOSECS(148200), NANOSECS(150150), NANOSECS(152152), NANOSECS(154440),
    NANOSECS(155610), NANOSECS(158004), NANOSECS(163020), NANOSECS(163800),
    NANOSECS(166725), NANOSECS(171171), NANOSECS(172900), NANOSECS(175560),
    NANOSECS(179550), NANOSECS(180180), NANOSECS(186732), NANOSECS(188100),
    NANOSECS(190190), NANOSECS(193050), NANOSECS(195624), NANOSECS(197505),
    NANOSECS(200200), NANOSECS(203775), NANOSECS(207480), NANOSECS(207900),
    NANOSECS(216216), NANOSECS(219450), NANOSECS(222300), NANOSECS(225225),
    NANOSECS(225720), NANOSECS(228228), NANOSECS(233415), NANOSECS(239400),
    NANOSECS(244530), NANOSECS(245700), NANOSECS(257400), NANOSECS(259350),
    NANOSECS(263340), NANOSECS(266760), NANOSECS(270270), NANOSECS(271700),
    NANOSECS(282150), NANOSECS(285285), NANOSECS(292600), NANOSECS(293436),
    NANOSECS(300300), NANOSECS(311220), NANOSECS(316008), NANOSECS(326040),
    NANOSECS(329175), NANOSECS(333450), NANOSECS(342342), NANOSECS(345800),
    NANOSECS(359100), NANOSECS(360360), NANOSECS(366795), NANOSECS(373464),
    NANOSECS(376200), NANOSECS(380380), NANOSECS(386100), NANOSECS(389025),
    NANOSECS(395010), NANOSECS(407550), NANOSECS(415800), NANOSECS(438900),
    NANOSECS(444600), NANOSECS(450450), NANOSECS(456456), NANOSECS(466830),
    NANOSECS(475475), NANOSECS(489060), NANOSECS(491400), NANOSECS(513513),
    NANOSECS(518700), NANOSECS(526680), NANOSECS(540540), NANOSECS(543400),
    NANOSECS(564300), NANOSECS(570570), NANOSECS(586872), NANOSECS(600600),
    NANOSECS(611325), NANOSECS(622440), NANOSECS(658350), NANOSECS(666900),
    NANOSECS(675675), NANOSECS(684684), NANOSECS(718200), NANOSECS(733590),
    NANOSECS(760760), NANOSECS(772200), NANOSECS(778050), NANOSECS(790020),
    NANOSECS(815100), NANOSECS(855855), NANOSECS(877800), NANOSECS(900900),
    NANOSECS(933660), NANOSECS(950950), NANOSECS(978120), NANOSECS(987525),
    NANOSECS(1027026), NANOSECS(1037400), NANOSECS(1081080), NANOSECS(1128600),
    NANOSECS(1141140), NANOSECS(1167075), NANOSECS(1222650), NANOSECS(1316700),
    NANOSECS(1333800), NANOSECS(1351350), NANOSECS(1369368), NANOSECS(1426425),
    NANOSECS(1467180), NANOSECS(1556100), NANOSECS(1580040), NANOSECS(1630200),
    NANOSECS(1711710), NANOSECS(1801800), NANOSECS(1833975), NANOSECS(1867320),
    NANOSECS(1901900), NANOSECS(1975050), NANOSECS(2054052), NANOSECS(2282280),
    NANOSECS(2334150), NANOSECS(2445300), NANOSECS(2567565), NANOSECS(2633400),
    NANOSECS(2702700), NANOSECS(2852850), NANOSECS(2934360), NANOSECS(3112200),
    NANOSECS(3423420), NANOSECS(3667950), NANOSECS(3803800), NANOSECS(3950100),
    NANOSECS(4108104), NANOSECS(4279275), NANOSECS(4668300), NANOSECS(4890600),
    NANOSECS(5135130), NANOSECS(5405400), NANOSECS(5705700), NANOSECS(6846840),
    NANOSECS(7335900), NANOSECS(7900200), NANOSECS(8558550), NANOSECS(9336600),
    NANOSECS(10270260), NANOSECS(11411400), NANOSECS(12837825), NANOSECS(14671800),
    NANOSECS(17117100), NANOSECS(20540520), NANOSECS(25675650), NANOSECS(34234200),
    NANOSECS(51351300), NANOSECS(102702600)
] 

def util_to_task_params(util, max_latency):
    for i in reversed(xrange(len(candidates))):                      
        period = candidates[i]
        budget = int((period * util * CONFIG_UTIL_GRANULARITY) / CONFIG_UTIL_GRANULARITY)
        if 2 * (period - budget) <= max_latency:
            return period, budget
    return -1, -1

def get_hyperperiod(tasks):
    if len(tasks) == 0:
        return 0
    hp = tasks[0].period
    for i in xrange(1, len(tasks)):
        hp = lcm(hp, tasks[i].period)
    return hp

def get_max_hyperperiod(mapping):
    hpmax = 0
    for core, partition in mapping.iteritems():
        hpmax = max(hpmax, get_hyperperiod(partition))
    return hpmax


# Convert a list of VMs into a SchedCAT compatible taskset
# 'info' is the domain info that can be retrieved from xen.get_dom_info()
# 'max_pcpus' is the maximum physical CPUs in the system (can be retrieved
# using xen.get_max_cpus()
def vmlist_to_ts(info, max_pcpus):
    ts = []
    # Generate task set based on passed info
    for k, vm in info.iteritems():
        if os.getenv('DEBUG', '') != '':
            print vm
        # For every VM, add the required number of VCPUs
        for v in xrange(0, vm['num_vcpus']):
            dom_id = vm['id']
            util = vm['utilization'] / vm['num_vcpus']
            affinity = vm['affinity']
            max_latency = vm['latency']
            burstable = vm['burstable']
            period, budget = util_to_task_params(util, max_latency)

            assert util > 0 and util <= 1.0, "Utilization must be in (0, 1]"
            assert period > 0 and budget > 0, "No suitable parameters"

            t = tasks.SporadicTask(budget, period, deadline=period)
            t.dom_id = dom_id
            t.vcpu_id = v
            t.max_latency = max_latency
            t.burstable = burstable
            t.util = util    # Double value between 0 and 1
            t.affinity = set(affinity)
            t.release_time = 0
            t.allocations = []

            ts.append(t)

    return ts

# Calculate what slice length should be used
def get_slice_size(sched, length):
    # Start with the length of the table
    min_slot_len = length
    min_idle_slot_len = 9999999999999999999999
    for slot in sched:
        # Ignore idle slots when figuring out slice length
        if slot.dom_id == 32767:
            if slot.t_to - slot.t_from < min_idle_slot_len:
                min_idle_slot_len = slot.t_to - slot.t_from
            continue

        if slot.t_to - slot.t_from < min_slot_len:
            min_slot_len = slot.t_to - slot.t_from

    slen = 1
    for x in candidates:
        if x >= slen and x <= min_slot_len:
            slen = x
        elif x > min_slot_len:
            break
    if os.getenv('DEBUG', '') != '':
        if min_idle_slot_len != 9999999999999999999999:
            print 'INFO: smallest idle slot size: %d ns' % min_idle_slot_len
        else:
            print 'INFO: no idle slot found'

    return slen

