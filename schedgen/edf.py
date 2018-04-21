import schedgen.xen as xen
import schedgen.scheduling as sched
import schedgen.task as task

def pick_job_edf(time, jobs):
    picked = None
    for j in jobs:
        if time >= j.release and j.remaining_budget > 0:
            if picked == None or j.deadline < picked.deadline:
                picked = j
    return picked

def next_release_time(time, jobs):
    picked = None
    for j in jobs:
        if time < j.release:
            if picked == None or j.release < picked.release:
                picked = j
    return picked;

def edf_schedule_generate(mapping, max_cpus):
    num_cpus = max_cpus
    cpu_tables = [[] for _ in xrange(num_cpus)]

    hp = task.get_max_hyperperiod(mapping)
    for core, tasks in mapping.iteritems():
        ctime = 0
        current = None
        jobs = [sched.Job(t) for t in tasks]
        while ctime <= hp:
            # check if we completed a job
            if current != None and current.remaining_budget <= 0:
                current.release  += current.task.period
                current.deadline += current.task.period
                current.remaining_budget = current.task.cost

            # reschedule
            edf_job = pick_job_edf(ctime, jobs)

            # record allocation before preemption
            if current != None and (edf_job != current or ctime == hp):
                t = current.task
                pt = t
                if not hasattr(t, 'dom_id'):
                    pt = t.original_task
                a = sched.Allocation(current.task, start_time, ctime, core)
                cpu_tables[core].append(a)
                current.task.allocations.append(a)

            # preempt if necessary
            if edf_job != current:
                start_time = ctime
                current = edf_job

            # advance to next event
            next_release = next_release_time(ctime, jobs)

            if next_release != None and current != None:
                next_time = next_release.release
                if next_time > ctime + current.remaining_budget:
                    next_time = ctime + current.remaining_budget
            elif next_release != None:
                next_time = next_release.release
            elif current != None:
                next_time = ctime + current.remaining_budget
            else:
                break

            if current != None:
                # decrement budget
                current.remaining_budget -= next_time - ctime
            ctime = next_time;
    return { 'tables': cpu_tables, 'length': hp }

# Verify a schedule by checking various invariants
#
# -- The schedule should be "fully covered" with no holes
# -- There should be no slots less than CONFIG_COALESCE_THRESHOLD us
def verify_schedule(sched):
    pass
