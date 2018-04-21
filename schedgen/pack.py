import struct
import os

import schedgen.scheduling as sched
import schedgen.xen as xen
#from schedgen.utils import us2ns

class Dummydata:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

def pack_u32(v):
    return struct.pack('=L', v)

def pack_u64(v):
    return struct.pack('=Q', v)

def getlen(s):
    l = 0
    for v in s:
        if isinstance(v[1], list):
            l += getlen(v[1])
        else:
            l += len(v[1])
    return l

def pad(s, nbytes):
    ret = ''
    l = getlen(s)
    for i in xrange(nbytes - l):
        ret += struct.pack('=B', 0)
    return ['pad', ret]

def align(s, align):
    l = getlen(s)
    if l % align != 0:
        return l - l % align + align
    return 0

def packed_to_struct(name, p):
    print 'struct ' + name + ' {'
    for v in p:
        print '\t',
        if len(v[1]) == 4:
            print 'uint32_t ' + str(v[0]) + ';'
        elif len(v[1]) == 8:
            print 'uint64_t ' + str(v[0]) + ';'
        else:
            print 'uint8_t ' + str(v[0]) + '[' + str(len(v[1])) + '];'
    print '};'

class Pack:
    __slots__ = ('packed')
    def __init__(self):
        self.packed = []

    # Push a u32
    def push_u32(self, name, val):
        self.packed.append([name, pack_u32(val)])

    # Push a u64
    def push_u64(self, name, val):
        self.packed.append([name, pack_u64(val)])

    # Push a packed structure
    def push_packed(self, name, val):
        self.packed.append([name, val])

    def align_pad(self, align):
        l = self.length()
        if l % align == 0:
            return
        to_pad = align - l % align
        s = struct.pack('x' * to_pad)
        #s = ''
        #for i in xrange(to_pad):
        #    s += struct.pack('=B', 0)
        self.packed.append(['pad', s])

    # Get the length of this packed structure
    def length(self):
        l = 0
        for v in self.packed:
            if isinstance(v[1], Pack):
                l += v[1].length()
            else:
                l += len(v[1])
        return l

    def to_struct(self, name):
        s = 'struct ' + name + ' {\n'
        for v in self.packed:
            s += '\t'
            if v[0] == 'pad':
                s += 'uint8_t ' + str(v[0]) + '[' + str(len(v[1])) + '];\n'
            elif len(v[1]) == 4:
                s += 'uint32_t ' + str(v[0]) + ';\n'
            elif len(v[1]) == 8:
                s += 'uint64_t ' + str(v[0]) + ';\n'
            else:
                s += 'uint8_t ' + str(v[0]) + '[' + str(len(v[1])) + '];\n'
        s += '};\n'
        return s

    def to_str(self):
        ret = ''
        for v in self.packed:
            if isinstance(v[1], Pack):
                ret += v[1].to_str()
            else:
                ret += v[1]
        return ret


# Pack a single VCPU info structure into a 64-byte image.
def pack_vcpu(v):
    ret = Pack()
    ret.push_u32('dom_id', int(v.dom))  # Pack the domain ID (32 bits)
    ret.push_u32('vcpu_id', int(v.vcpu))# Pack the VCPU id (32 bits)
    cpumask = 0
    for c in v.cores:
        cpumask |= 1 << c
    ret.push_u64('cpumask', cpumask)    # Pack the CPU mask (64 bits)
    if len(v.cores) > 1 or not v.burstable:
        ret.push_u64('flags', 1)        # Pack flags if it's migrating
    else:
        ret.push_u64('flags', 0)        # Pack empty flags if it's non-migrating
    ret.push_u64('vcpu_ptr', 0)         # Pack a 64-bit placeholder for VCPU ptr
    ret.align_pad(64)                   # Pad the struct to 64 bytes (cacheline)
    return ret

# Packs all VCPU info into a binary image with 64-byte entries per VCPU
# Note that VCPUs are packed in the same order found in the vcpu_list passed
# so offsets can be directly calculated from the vcpu_list.
def pack_vcpu_info(vcpus):
    ret = Pack()
    for v in vcpus:
        ret.push_packed('vcpu', pack_vcpu(v))
    ret.align_pad(4096)
    return ret

# Pack a single slot into a 64-byte structure.
def pack_slot(slot, vinfo):
    ret = Pack()
    # Pack the offset into the VCPU info list
    ret.push_u64('offset', slot.t_from)
    ret.push_u64('vcpu_ptr', sched.find_in_vinfo(vinfo, slot.dom_id, slot.vcpu_id))
    ret.push_u64('length', slot.t_to - slot.t_from)# Pack the size
    ret.push_u64('start', slot.t_from)            # Pack the start time
    ret.push_u64('end', slot.t_to)              # Pack the start time
    ret.align_pad(64)         # Pad the struct to 64 bytes (cacheline)
    return ret

# Packs all slots provided in a list into a binary image containing individual
# 64-byte entries per slot. The ordering is identical to that of the provided
# list and so offsets can be calculated on the original list.
def pack_slots(slots, vinfo):
    ret = Pack()
    for s in slots:
        ret.push_packed('slot', pack_slot(s, vinfo))
    ret.align_pad(4096)
    return ret

# Pack a single slot into a 64-byte structure.
def pack_l2_slot(slot):
    ret = Pack()
    # Pack the offset into the VCPU info list
    ret.push_u64('start', slot[0])            # Pack the start time
    ret.push_u64('end', slot[1])              # Pack the start time
    ret.push_u64('length', slot[1] - slot[0])# Pack the size
    val = 0
    for v in slot[2]:
        val = val | (1 << v)
    ret.push_u64('restricts', val)# Pack the restricted set of vCPUs
    ret.align_pad(64)         # Pad the struct to 64 bytes (cacheline) return ret
    return ret

# Packs all L2 slots into a binary image containing individual
# 64-byte entries per slot.
def pack_l2_slots(slots):
    ret = Pack()
    for s in slots:
        ret.push_packed('slot', pack_l2_slot(s))
    ret.align_pad(4096)
    return ret

# Pack a single slice into a 64-byte structure.
def pack_slice(s, slots):
    ret = Pack()
    ret.push_u64('start', s.t_from)
    ret.push_u64('end', s.t_to)

    # Pack the left slot (should always be set)
    assert s.left_alloc != None
    ret.push_u64('left', sched.sid_to_slot(s.left_alloc, slots))

    # Pack middle slot (may be NULL)
    if s.idle_middle == None:
        ret.push_u64('middle', 32767)
    else:
        ret.push_u64('middle', sched.sid_to_slot(s.idle_middle, slots))

    # Pack the right slot (may be NULL)
    if s.right_alloc == None:
        ret.push_u64('right', 32767)
    else:
        ret.push_u64('right', sched.sid_to_slot(s.right_alloc, slots))

    ret.push_u64('boundary', s.boundary)
    ret.align_pad(64)
    return ret

# Pack a single slice into a 64-byte structure.
def pack_l2_slice(s, slots):
    ret = Pack()
    ret.push_u64('start', s.t_from)
    ret.push_u64('end', s.t_to)

    # Pack the left slot (should always be set)
    assert s.left_alloc != None
    ret.push_u64('left', sched.l2_sid_to_slot(s.left_alloc, slots))

    # Pack middle slot (may be NULL)
    if s.idle_middle == None:
        ret.push_u64('middle', 32767)
    else:
        ret.push_u64('middle', sched.l2_sid_to_slot(s.idle_middle, slots))

    # Pack the right slot (may be NULL)
    if s.right_alloc == None:
        ret.push_u64('right', 32767)
    else:
        ret.push_u64('right', sched.l2_sid_to_slot(s.right_alloc, slots))

    ret.push_u64('boundary', s.boundary)
    ret.align_pad(64)
    return ret

def pack_slices_percpu(slices, slots):
    ret = Pack()
    for s in slices:
        ret.push_packed('slice', pack_slice(s, slots))
    ret.align_pad(4096)
    return ret

def pack_l2_slices_percpu(slices, slots):
    ret = Pack()
    for s in slices:
        ret.push_packed('slice', pack_l2_slice(s, slots))
    ret.align_pad(4096)
    return ret

# Pack a per-CPU header.
def pack_percpu_header(nslots, nslices, slot_off, slice_off, slice_len, table_len, nvcpus, vcpu_list_off):
    ret = Pack()
    ret.push_u64('nslots', nslots)
    ret.push_u64('slot_list_off', slot_off)
    ret.push_u64('nslices', nslices)
    ret.push_u64('slice_list_off', slice_off)
    ret.push_u64('slice_length', slice_len)
    ret.push_u64('table_length', table_len)

    ret.push_u64('nvcpus', nvcpus)
    ret.push_u64('vcpu_list_off', vcpu_list_off)

    ret.align_pad(4096)
    return ret

# Pack everything for a single CPU into a single packed binary
def pack_percpu(core, vcpu_list, l1_slots, l1_slices, l1_slice_len, l1_table_len):
    ret = Pack()

    # Generate and pack the per-CPU VCPU info list
    percpu_vlist = [x for x in vcpu_list if core in x.cores]
    packed_vinfo = pack_vcpu_info(percpu_vlist)

    #packed_l1_slots = pack_slots(l1_slots[core], vcpu_list)
    packed_l1_slots = pack_slots(l1_slots[core], vcpu_list)
    packed_l1_slices = pack_slices_percpu(l1_slices[core], l1_slots)

    packed_header = pack_percpu_header(
                        nslots=len(l1_slots[core]),
                        nslices=len(l1_slices[core]),
                        slot_off=4096, # L1 slots are immediately after 4K header
                        slice_off=4096 + packed_l1_slots.length(), # L1 slices are after header (4K) + slots
                        slice_len=l1_slice_len,
                        table_len=l1_table_len,

                        nvcpus=len(percpu_vlist),
                        vcpu_list_off=4096 + packed_l1_slots.length() + packed_l1_slices.length()
                    )

    ret.push_packed('header', packed_header)
    ret.push_packed('slots', packed_l1_slots)
    ret.push_packed('slices', packed_l1_slices)
    ret.push_packed('vinfo', packed_vinfo)

    if os.getenv('DEBUG', '') != '':
        print '%-3d %10d %10d %10d %10d' % (core, packed_header.length(), packed_l1_slots.length(), packed_l1_slices.length(), ret.length())

    return ret

# Pack the global header.
#
# struct global_header {
#     uint64_t num_vcpus;        /* Number of VCPUs is VCPU list */
#     uint64_t vcpu_list_off; /* Offset of VCPU list */
#     uint64_t num_cpus;      /* Number of CPUs in Per-CPU data list */
#     uint64_t percpu_off[MAX_CPUS];  /* Per-CPU data offsets */
# } __attribute__((aligned(4096)));
def pack_global_header(num_vcpus, num_cpus, vinfo, percpu_packed):
    ret = Pack()
    ret.push_u64('num_vcpus', num_vcpus)
    ret.push_u64('vcpu_list_off', 4096)
    ret.push_u64('num_cpus', num_cpus)
    off = 4096 + vinfo.length()
    # Add the per-cpu data offsets
    for i in xrange(len(percpu_packed)):
        ret.push_u64('percpu_off[' + str(i) + ']', off)
        off += percpu_packed[i].length()
    for i in xrange(len(percpu_packed), 64):
        ret.push_u64('percpu_off[' + str(i) + ']', 0)
    ret.align_pad(4096)
    return ret

def pack_global(vcpu_list, l1_schedule, l1_slices, l1_slice_lens):
    num_cpus = len(l1_schedule['tables'])
    # Pack the VCPU info list
    vinfo_packed = pack_vcpu_info(vcpu_list)

    # Pack the per-CPU data
    percpu_packed = []
    
    if os.getenv('DEBUG', '') != '':
        print '%-3s %10s %10s %10s %10s' % ('cpu', 'header', 'slots', 'slices', 'total')
    for i in xrange(num_cpus):
        percpu_packed.append(pack_percpu(i, vcpu_list, l1_schedule['tables'], l1_slices, l1_slice_lens[i], l1_schedule['length']))

    ret = Pack()
    ret.push_packed('global_header', pack_global_header(len(vcpu_list), num_cpus, vinfo_packed, percpu_packed))
    ret.push_packed('vinfo', vinfo_packed)
    for i in xrange(num_cpus):
        ret.push_packed('percpu[' + str(i) + ']', percpu_packed[i])
    return ret
