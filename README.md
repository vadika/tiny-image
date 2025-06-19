# tiny-image
Tiny linux image management tools 
Based on Daniel P. Berrangé  work

make-tiny-image.py: creating tiny initrds for testing QEMU or Linux kernel/userspace behaviour

## New Feature: Local Kernel Building

You can now build a minimal kernel locally to include in your testing:

```bash
# Build latest stable kernel with minimal config
./make-tiny-image.py --build-kernel

# Build specific kernel version
./make-tiny-image.py --build-kernel 6.8.1

# Use custom kernel config
./make-tiny-image.py --build-kernel --kernel-config /path/to/config

# The built kernel will be saved as "tiny-kernel" and automatically used by run-tiny-image.sh
./run-tiny-image.sh
```

### Multi-Architecture Support

The tools now support multiple architectures:
- **x86_64**: Uses bzImage format with ACPI support
- **ARM64/aarch64**: Uses Image format with PSCI support
- **ARM**: Uses zImage format

The minimal kernel includes only essential features for initrd boot:
- Architecture-specific CPU support
- initrd/initramfs support
- Essential filesystems (proc, sysfs, tmpfs)
- Serial console for QEMU (PL011 for ARM, 8250 for x86)
- Virtio drivers for QEMU
- Power management (ACPI for x86, PSCI for ARM)

The run script automatically detects your architecture and uses the appropriate QEMU binary and options. KVM acceleration is used when available, otherwise it falls back to TCG emulation.
Posted: March 9th, 2023 | Filed under: Coding Tips, Fedora, libvirt, Virt Tools | Tags: debugging, initrd, make-tiny-image | No Comments »

As a virtualization developer a significant amount of time is spent in understanding and debugging the behaviour and interaction of QEMU and the guest kernel/userspace code. As such my development machines have a variety of guest OS installations that get booted for various tasks. Some tasks, however, require a repeated cycle of QEMU code changes, or QEMU config changes, followed by guest testing. Waiting for an OS to boot can quickly become a significant time sink affecting productivity and lead to frustration. What is needed is a very low overhead way to accomplish simple testing tasks without an OS getting in the way.

Enter ‘make-tiny-image.py‘ tool for creating minimal initrd images.

If invoked with no arguments, this tool will create an initrd containing nothing more than busybox. The “init” program will be a script that creates a few device nodes, mounts proc/sysfs and then runs the busybox ‘sh’ binary to provide an interactive shell. This is intended to be used as follows

$ ./make-tiny-image.py
tiny-initrd.img
6.0.8-300.fc37.x86_64

$ qemu-system-x86_64 \
    -kernel /boot/vmlinuz-$(uname -r) \
    -initrd tiny-initrd.img \
    -append 'console=ttyS0 quiet' \
    -accel kvm -m 1000 -display none -serial stdio
~ # uname  -a
Linux (none) 6.0.8-300.fc37.x86_64 #1 SMP PREEMPT_DYNAMIC Fri Nov 11 15:09:04 UTC 2022 x86_64 x86_64 x86_64 Linux
~ # uptime
 15:05:42 up 0 min,  load average: 0.00, 0.00, 0.00
~ # free
              total        used        free      shared  buff/cache   available
Mem:         961832       38056      911264        1388       12512      845600
Swap:             0           0           0
~ # df
Filesystem           1K-blocks      Used Available Use% Mounted on
none                    480916         0    480916   0% /dev
~ # ls
bin   dev   init  proc  root  sys   usr
~ # <Ctrl+D>
[   23.841282] reboot: Power down

When I say “low overhead”, just how low are we talking about ? With KVM, it takes less than a second to bring up the shell. Testing with emulation is where this really shines. Booting a full Fedora OS with QEMU emulation is slow enough that you don’t want to do it at all frequently. With this tiny initrd, it’ll take a little under 4 seconds to boot to the interactive shell. Much slower than KVM, but fast enough you’ll be fine repeating this all day long, largely unaffected by the (lack of) speed relative to KVM.

The make-tiny-image.py tool will create the initrd such that it drops you into a shell, but it can be told to run another command instead. This is how I tested the overheads mentioned above

$ ./make-tiny-image.py --run poweroff
tiny-initrd.img
6.0.8-300.fc37.x86_64

$ time qemu-system-x86_64 \
     -kernel /boot/vmlinuz-$(uname -r) \
     -initrd tiny-initrd.img \
     -append 'console=ttyS0 quiet' \
     -m 1000 -display none -serial stdio -accel kvm
[    0.561174] reboot: Power down

real	0m0.828s
user	0m0.613s
sys	0m0.093s
$ time qemu-system-x86_64 \
     -kernel /boot/vmlinuz-$(uname -r) \
     -initrd tiny-initrd.img \
     -append 'console=ttyS0 quiet' \
     -m 1000 -display none -serial stdio -accel tcg
[    2.741983] reboot: Power down

real	0m3.774s
user	0m3.626s
sys	0m0.174s

As a more useful real world example, I wanted to test the effect of changing the QEMU CPU configuration against KVM and QEMU, by comparing at the guest /proc/cpuinfo.

$ ./make-tiny-image.py --run 'cat /proc/cpuinfo'
tiny-initrd.img
6.0.8-300.fc37.x86_64

$ qemu-system-x86_64 \
    -kernel /boot/vmlinuz-$(uname -r) \
    -initrd tiny-initrd.img \
    -append 'console=ttyS0 quiet' \
    -m 1000 -display none -serial stdio -accel tcg -cpu max | grep '^flags'
flags		: fpu de pse tsc msr pae mce cx8 apic sep mtrr pge mca 
                  cmov pat pse36 clflush acpi mmx fxsr sse sse2 ss syscall 
                  nx mmxext pdpe1gb rdtscp lm 3dnowext 3dnow rep_good nopl 
                  cpuid extd_apicid pni pclmulqdq monitor ssse3 cx16 sse4_1 
                  sse4_2 movbe popcnt aes xsave rdrand hypervisor lahf_lm 
                  svm cr8_legacy abm sse4a 3dnowprefetch vmmcall fsgsbase 
                  bmi1 smep bmi2 erms mpx adx smap clflushopt clwb xsaveopt 
                  xgetbv1 arat npt vgif umip pku ospke la57

$ qemu-system-x86_64 \
    -kernel /boot/vmlinuz-$(uname -r) \
    -initrd tiny-initrd.img \
    -append 'console=ttyS0 quiet' \
    -m 1000 -display none -serial stdio -accel kvm -cpu max | grep '^flags'
flags		: fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca 
                  cmov pat pse36 clflush mmx fxsr sse sse2 ss syscall nx 
                  pdpe1gb rdtscp lm constant_tsc arch_perfmon rep_good 
                  nopl xtopology cpuid tsc_known_freq pni pclmulqdq vmx 
                  ssse3 fma cx16 pdcm pcid sse4_1 sse4_2 x2apic movbe 
                  popcnt tsc_deadline_timer aes xsave avx f16c rdrand 
                  hypervisor lahf_lm abm 3dnowprefetch cpuid_fault 
                  invpcid_single ssbd ibrs ibpb stibp ibrs_enhanced 
                  tpr_shadow vnmi flexpriority ept vpid ept_ad fsgsbase 
                  tsc_adjust sgx bmi1 avx2 smep bmi2 erms invpcid mpx 
                  rdseed adx smap clflushopt xsaveopt xsavec xgetbv1 
                  xsaves arat umip sgx_lc md_clear arch_capabilities

NB, with the list of flags above, I’ve manually line wrapped the output for saner presentation in this blog rather than have one giant long line.

These examples have relied on tools provided by busybox, but we’re not limited by that. It is possible to tell it to copy in arbitrary extra binaries from the host OS by just listing their name. If it is a dynamically linked ELF binary, it’ll follow the ELF header dependencies, pulling in any shared libraries needed.

$ ./make-tiny-image.py hwloc-info lstopo-no-graphics
tiny-initrd.img
6.0.8-300.fc37.x86_64
Copy bin /usr/bin/hwloc-info -> /tmp/make-tiny-imagexu_mqd99/bin/hwloc-info
Copy bin /usr/bin/lstopo-no-graphics -> /tmp/make-tiny-imagexu_mqd99/bin/lstopo-no-graphics
Copy lib /lib64/libhwloc.so.15 -> /tmp/make-tiny-imagexu_mqd99/lib64/libhwloc.so.15
Copy lib /lib64/libc.so.6 -> /tmp/make-tiny-imagexu_mqd99/lib64/libc.so.6
Copy lib /lib64/libm.so.6 -> /tmp/make-tiny-imagexu_mqd99/lib64/libm.so.6
Copy lib /lib64/ld-linux-x86-64.so.2 -> /tmp/make-tiny-imagexu_mqd99/lib64/ld-linux-x86-64.so.2
Copy lib /lib64/libtinfo.so.6 -> /tmp/make-tiny-imagexu_mqd99/lib64/libtinfo.so.6

$ qemu-system-x86_64 -kernel /boot/vmlinuz-$(uname -r) -initrd tiny-initrd.img -append 'console=ttyS0 quiet' -m 1000 -display none -serial stdio -accel kvm 
~ # hwloc-info 
depth 0:           1 Machine (type #0)
 depth 1:          1 Package (type #1)
  depth 2:         1 L3Cache (type #6)
   depth 3:        1 L2Cache (type #5)
    depth 4:       1 L1dCache (type #4)
     depth 5:      1 L1iCache (type #9)
      depth 6:     1 Core (type #2)
       depth 7:    1 PU (type #3)
Special depth -3:  1 NUMANode (type #13)
Special depth -4:  1 Bridge (type #14)
Special depth -5:  3 PCIDev (type #15)
Special depth -6:  1 OSDev (type #16)
Special depth -7:  1 Misc (type #17)

~ # lstopo-no-graphics 
Machine (939MB total)
  Package L#0
    NUMANode L#0 (P#0 939MB)
    L3 L#0 (16MB) + L2 L#0 (4096KB) + L1d L#0 (32KB) + L1i L#0 (32KB) + Core L#0 + PU L#0 (P#0)
  HostBridge
    PCI 00:01.1 (IDE)
      Block "sr0"
    PCI 00:02.0 (VGA)
    PCI 00:03.0 (Ethernet)
  Misc(MemoryModule)

An obvious limitation is that if the binary/library requires certain data files, those will not be present in the initrd. It isn’t attempting to do anything clever like query the corresponding RPM file list and copy those. This tool is meant to be simple and fast and keep out of your way. If certain data files are critical for testing though, the --copy argument can be used. The copied files will be put at the same path inside the initrd as found on the host

$ ./make-tiny-image.py --copy /etc/redhat-release 
tiny-initrd.img
6.0.8-300.fc37.x86_64
Copy extra /etc/redhat-release -> /tmp/make-tiny-imageicj1tvq4/etc/redhat-release

$ qemu-system-x86_64 \
    -kernel /boot/vmlinuz-$(uname -r) \
    -initrd tiny-initrd.img \
    -append 'console=ttyS0 quiet' \
    -m 1000 -display none -serial stdio -accel kvm 
~ # cat /etc/redhat-release 
Fedora release 37 (Thirty Seven)

What if the problem being tested requires using some kernel modules ? That’s covered too with the --kmod argument, which will copy in the modules listed, along with their dependencies and the insmod command itself. As an example of its utility, I used this recently to debug a regression in support for the iTCO watchdog in Linux kernels

$ ./make-tiny-image.py --kmod lpc_ich --kmod iTCO_wdt  --kmod i2c_i801 
tiny-initrd.img
6.0.8-300.fc37.x86_64
Copy kmod /lib/modules/6.0.8-300.fc37.x86_64/kernel/drivers/mfd/lpc_ich.ko.xz -> /tmp/make-tiny-image63td8wbl/lib/modules/lpc_ich.ko.xz
Copy kmod /lib/modules/6.0.8-300.fc37.x86_64/kernel/drivers/watchdog/iTCO_wdt.ko.xz -> /tmp/make-tiny-image63td8wbl/lib/modules/iTCO_wdt.ko.xz
Copy kmod /lib/modules/6.0.8-300.fc37.x86_64/kernel/drivers/watchdog/iTCO_vendor_support.ko.xz -> /tmp/make-tiny-image63td8wbl/lib/modules/iTCO_vendor_support.ko.xz
Copy kmod /lib/modules/6.0.8-300.fc37.x86_64/kernel/drivers/mfd/intel_pmc_bxt.ko.xz -> /tmp/make-tiny-image63td8wbl/lib/modules/intel_pmc_bxt.ko.xz
Copy kmod /lib/modules/6.0.8-300.fc37.x86_64/kernel/drivers/i2c/busses/i2c-i801.ko.xz -> /tmp/make-tiny-image63td8wbl/lib/modules/i2c-i801.ko.xz
Copy kmod /lib/modules/6.0.8-300.fc37.x86_64/kernel/drivers/i2c/i2c-smbus.ko.xz -> /tmp/make-tiny-image63td8wbl/lib/modules/i2c-smbus.ko.xz
Copy bin /usr/sbin/insmod -> /tmp/make-tiny-image63td8wbl/bin/insmod
Copy lib /lib64/libzstd.so.1 -> /tmp/make-tiny-image63td8wbl/lib64/libzstd.so.1
Copy lib /lib64/liblzma.so.5 -> /tmp/make-tiny-image63td8wbl/lib64/liblzma.so.5
Copy lib /lib64/libz.so.1 -> /tmp/make-tiny-image63td8wbl/lib64/libz.so.1
Copy lib /lib64/libcrypto.so.3 -> /tmp/make-tiny-image63td8wbl/lib64/libcrypto.so.3
Copy lib /lib64/libgcc_s.so.1 -> /tmp/make-tiny-image63td8wbl/lib64/libgcc_s.so.1
Copy lib /lib64/libc.so.6 -> /tmp/make-tiny-image63td8wbl/lib64/libc.so.6
Copy lib /lib64/ld-linux-x86-64.so.2 -> /tmp/make-tiny-image63td8wbl/lib64/ld-linux-x86-64.so.2

$ ~/src/virt/qemu/build/qemu-system-x86_64 -kernel /boot/vmlinuz-$(uname -r) -initrd tiny-initrd.img -append 'console=ttyS0 quiet' -m 1000 -display none -serial stdio -accel kvm  -M q35 -global ICH9-LPC.noreboot=false -watchdog-action poweroff -trace ich9* -trace tco*
ich9_cc_read addr=0x3410 val=0x20 len=4
ich9_cc_write addr=0x3410 val=0x0 len=4
ich9_cc_read addr=0x3410 val=0x0 len=4
ich9_cc_read addr=0x3410 val=0x0 len=4
ich9_cc_write addr=0x3410 val=0x20 len=4
ich9_cc_read addr=0x3410 val=0x20 len=4
tco_io_write addr=0x4 val=0x8
tco_io_write addr=0x6 val=0x2
tco_io_write addr=0x6 val=0x4
tco_io_read addr=0x8 val=0x0
tco_io_read addr=0x12 val=0x4
tco_io_write addr=0x12 val=0x32
tco_io_read addr=0x12 val=0x32
tco_io_write addr=0x0 val=0x1
tco_timer_reload ticks=50 (30000 ms)
~ # mknod /dev/watchdog0 c 10 130
~ # cat /dev/watchdog0
tco_io_write addr=0x0 val=0x1
tco_timer_reload ticks=50 (30000 ms)
cat: read error: Invalid argument
[   11.052062] watchdog: watchdog0: watchdog did not stop!
tco_io_write addr=0x0 val=0x1
tco_timer_reload ticks=50 (30000 ms)
~ # tco_timer_expired timeouts_no=0 no_reboot=0/1
tco_timer_reload ticks=50 (30000 ms)
tco_timer_expired timeouts_no=1 no_reboot=0/1
tco_timer_reload ticks=50 (30000 ms)
tco_timer_expired timeouts_no=0 no_reboot=0/1
tco_timer_reload ticks=50 (30000 ms)

The Linux regression had accidentally left the watchdog with the ‘no reboot’ bit set, so it would never trigger the action, which we diagnosed from seeing repeated QEMU trace events for tco_timer_expired after triggering the watchdog in the guest. This was quicky fixed by the Linux maintainers.

In spite of being such a simple and crude script, with many, many, many unhandled edge cases, it has proved remarkably useful at enabling low overhead debugging of QEMU/Linux guest behaviour.

