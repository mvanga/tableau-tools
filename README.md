# Tableau Userspace Tools

This repository contains the userspace tools for the Xen implementation
of [the Tableau VM scheduler](https://github.com/mvanga/tableau-xen-4.9).

### Configuration

Edit `schedgen/config.py` and change the `CONFIG_SCHEDULE_ELF` variable
to point to the `xc_ttxen_push_table` binary in the Tableau Xen tree.

### Generating Tables

The `table_build` script can be used to generate tables. It takes as a
parameter a configuration file and writes its output to a hidden
folder called `.sched` in the current working directory.

    ./table_build examples/example.conf

See `examples/example.conf` for details on the configuration file format.

### Pushing Tables to the Hypervisor

The `table_push` script is used to push a generated table to the hypervisor.
It takes a single parameter: the folder containing the generated table.

    ./table_push .sched

### Load Balancing Background VMs

Tableau begins running newly-created VMs immediately using a background
scheduler, which places a VM on a random core and schedules it whenever
there are idle cycles on that core. To avoid long-term starvation, the
`load_balancer` script can be used to load balance VMs across cores. It
works by measuring the average number of idle cycles on each core, and
re-partitioning background VMs based on it.

The script can be run as follows:

    ./load_balance
