from utils import shell_exec, shell_exec_popen, getoutput, chroot_exec, get_config_dict

import os
import time
import sys

# [XK]
from utils import hasInternetConnection, runningInVirtualBox, isAmd64
from plymouth import PlymouthSave
from localize import Localize


CONFIG_FILE = '/etc/live-installer/live-installer.conf'

class InstallerEngine:
    ''' This is central to the live installer '''

    def __init__(self):
        # Set distribution name and version
        for f, n, v in (('/etc/os-release', 'PRETTY_NAME', 'VERSION'),
                        ('/etc/lsb-release', 'DISTRIB_DESCRIPTION', 'DISTRIB_RELEASE'),
                        (CONFIG_FILE, 'DISTRIBUTION_NAME', 'DISTRIBUTION_VERSION')):
            try:
                config = get_config_dict(f)
                name, version = config[n], config[v]
            except (IOError, KeyError): continue
            else: break
        else: name, version = 'Unknown GNU/Linux', '1.0'
        self.distribution_name, self.distribution_version = name, version
        config = get_config_dict('/etc/os-release')
        self.distribution_id =  config.get('ID', 'distro')
        # Set other configuration
        config = get_config_dict(CONFIG_FILE)
        self.live_user = config.get('live_user', 'user')
        self.media = config.get('live_media_source', '/lib/live/mount/medium/live/filesystem.squashfs')
        self.media_type = config.get('live_media_type', 'squashfs')
        # Flush print when it's called
        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    def set_progress_hook(self, progresshook):
        ''' Set a callback to be called on progress updates '''
        ''' i.e. def my_callback(progress_type, message, current_progress, total) '''
        ''' Where progress_type is any off PROGRESS_START, PROGRESS_UPDATE, PROGRESS_COMPLETE, PROGRESS_ERROR '''
        self.update_progress = progresshook

    def set_error_hook(self, errorhook):
        ''' Set a callback to be called on errors '''
        self.error_message = errorhook

    def get_distribution_name(self):
        return self.distribution_name

    def get_distribution_version(self):
        return self.distribution_version

    def step_format_partitions(self, setup):
        for partition in setup.partitions:
            if(partition.format_as is not None and partition.format_as != ""):
                # report it. should grab the total count of filesystems to be formatted ..
                self.update_progress(total=4, current=1, pulse=True, message=_("Formatting %(partition)s as %(format)s ..." % {'partition':partition.partition.path, 'format':partition.format_as}))

                #Format it
                if partition.format_as == "swap":
                    cmd = "mkswap %s" % partition.partition.path
                elif partition.format_as[:3] == 'ext':
                    cmd = "mkfs.%s -F -q %s" % (partition.format_as, partition.partition.path)
                elif partition.format_as == "jfs":
                    cmd = "mkfs.%s -q %s" % (partition.format_as, partition.partition.path)
                elif partition.format_as == "xfs":
                    cmd = "mkfs.%s -f %s" % (partition.format_as, partition.partition.path)
                elif partition.format_as == "vfat":
                    cmd = "mkfs.%s %s -F 32" % (partition.format_as, partition.partition.path)
                else:
                    cmd = "mkfs.%s %s" % (partition.format_as, partition.partition.path) # works with bfs, btrfs, minix, msdos, ntfs

                shell_exec(cmd)

                partition.type = partition.format_as

    def step_mount_source(self, setup):
        # Mount the installation media
        print " --> Mounting partitions"
        self.update_progress(total=4, current=2, message=_("Mounting %(partition)s on %(mountpoint)s") % {'partition':self.media, 'mountpoint':"/source/"})
        print " ------ Mounting %s on %s" % (self.media, "/source/")
        self.do_mount(self.media, "/source/", self.media_type, options="loop")

    def step_mount_partitions(self, setup):
        self.step_mount_source(setup)

        # Mount the target partition
        for partition in setup.partitions:
            if(partition.mount_as is not None and partition.mount_as != ""):
                  if partition.mount_as == "/":
                        self.update_progress(total=4, current=3, message=_("Mounting %(partition)s on %(mountpoint)s") % {'partition':partition.partition.path, 'mountpoint':"/target/"})
                        print " ------ Mounting partition %s on %s" % (partition.partition.path, "/target/")
                        if partition.type == "fat32":
                            fs = "vfat"
                        else:
                            fs = partition.type
                        self.do_mount(partition.partition.path, "/target", fs, None)
                        break

        # Mount the other partitions
        for partition in setup.partitions:
            if(partition.mount_as is not None and partition.mount_as != "" and partition.mount_as != "/" and partition.mount_as != "swap"):
                print " ------ Mounting %s on %s" % (partition.partition.path, "/target" + partition.mount_as)
                shell_exec("mkdir -p /target" + partition.mount_as)
                if partition.type == "fat16" or partition.type == "fat32":
                    fs = "vfat"
                else:
                    fs = partition.type
                self.do_mount(partition.partition.path, "/target" + partition.mount_as, fs, None)

    def init_install(self, setup):
        # mount the media location.
        print " --> Installation started"
        if(not os.path.exists("/target")):
            if (setup.skip_mount):
                self.error_message(message=_("ERROR: You must first manually mount your target filesystem(s) at /target to do a custom install!"))
                return
            os.mkdir("/target")
        if(not os.path.exists("/source")):
            os.mkdir("/source")
        # find the squashfs..
        if(not os.path.exists(self.media)):
            print "Base filesystem does not exist! Critical error (exiting)."
            self.error_message(message=_("ERROR: Something is wrong with the installation medium! This is usually caused by burning tools which are not compatible with {} (YUMI or other multiboot tools). Please burn the ISO image to DVD/USB using a different tool.".format(self.distribution_name)))
            return

        shell_exec("umount --force /target/dev/shm")
        shell_exec("umount --force /target/dev/pts")
        shell_exec("umount --force /target/dev/")
        shell_exec("umount --force /target/sys/")
        shell_exec("umount --force /target/proc/")

        if (not setup.skip_mount):
            self.step_format_partitions(setup)
            self.step_mount_partitions(setup)
        else:
            self.step_mount_source(setup)

        # [XK] # Preserve /root if it exists
        if os.path.isdir("/target/root"):
            # shutil.copytree gave errors on kde cache files
            shell_exec("cp -r /target/root /tmp/")

        # Transfer the files
        SOURCE = "/source/"
        DEST = "/target/"
        EXCLUDE_DIRS = "home/* dev/* proc/* sys/* tmp/* run/* mnt/* media/* lost+found source".split()
        our_current = 0
        # assume: #(files to copy) ~= #(used inodes on /)
        our_total = int(getoutput("df --inodes /{src} | awk '/^.+?\/{src}$/{{ print $3 }}'".format(src=SOURCE.strip('/'))))
        print " --> Copying {} files".format(our_total)
        rsync_filter = ' '.join('--exclude=' + SOURCE + d for d in EXCLUDE_DIRS)
        rsync = shell_exec_popen("rsync --ignore-errors --verbose --archive --no-D --acls "
                           "--hard-links --xattrs {rsync_filter} "
                           "{src}* {dst}".format(src=SOURCE, dst=DEST, rsync_filter=rsync_filter))
        while rsync.poll() is None:
            line = rsync.stdout.readline()
            if not line: time.sleep(0.1)
            else:
                our_current = min(our_current + 1, our_total)
                self.update_progress(total=our_total, current=our_current, message=_("Copying {}".format(line)))
                #print "Copying " + line
        rsync_return_code = rsync.poll()
        if rsync_return_code > 0:
            print "ERROR: rsync exited with returncode: " + str(rsync_return_code)
            sys.exit()

        # [XK] Restore /root if it was preserved
        if os.path.isdir("/tmp/root"):
            if os.path.isdir("/target/root"):
                shell_exec("mv /target/root /tmp/root.install")
            shell_exec("mv /tmp/root /target/")

        # Steps:
        our_total = 11
        our_current = 0
        # chroot
        print " --> Chrooting"
        self.update_progress(total=our_total, current=our_current, message=_("Entering the system ..."))
        shell_exec("mount --bind /dev/ /target/dev/")
        shell_exec("mount --bind /dev/shm /target/dev/shm")
        shell_exec("mount --bind /dev/pts /target/dev/pts")
        shell_exec("mount --bind /sys/ /target/sys/")
        shell_exec("mount --bind /proc/ /target/proc/")
        shell_exec("mv /target/etc/resolv.conf /target/etc/resolv.conf.bk")
        shell_exec("cp -f /etc/resolv.conf /target/etc/resolv.conf")

        kernelversion = getoutput("uname -r")
        shell_exec("cp /lib/live/mount/medium/live/vmlinuz /target/boot/vmlinuz-%s" % kernelversion)
        shell_exec("cp /lib/live/mount/medium/live/initrd.img /target/boot/initrd.img-%s" % kernelversion)

        if (setup.gptonefi):
            # [XK] Make target dir more generic
            if os.path.exists("/lib/live/mount/medium/EFI/BOOT/grubx64.efi"):
                shell_exec("mkdir -p /target/boot/efi/EFI/%s" % self.distribution_id)
                shell_exec("cp /lib/live/mount/medium/EFI/BOOT/grubx64.efi /target/boot/efi/EFI/%s/" % self.distribution_id)
            shell_exec("mkdir -p /target/debs")
            shell_exec("cp /lib/live/mount/medium/offline/grub-efi* /target/debs/")
            shell_exec("cp /lib/live/mount/medium/offline/efibootmgr* /target/debs/")
            chroot_exec("dpkg -i /debs/*")
            shell_exec("rm -rf /target/debs")

        # Detect cdrom device
        # TODO : properly detect cdrom device
        # Mount it
        # os.system("mkdir -p /target/media/cdrom")
        # if (int(os.system("mount /dev/sr0 /target/media/cdrom"))):
        #     print " --> Failed to mount CDROM. Install will fail"
        # chroot_exec("apt-cdrom -o Acquire::cdrom::AutoDetect=false -m add")

        # remove live-packages (or w/e)
        print " --> Removing live packages"
        our_current += 1
        self.update_progress(pulse=True, total=our_total, current=our_current, message=_("Removing live configuration (packages)"))
        with open("/lib/live/mount/medium/live/filesystem.packages-remove", "r") as fd:
            line = fd.read().replace('\n', ' ')
        chroot_exec("apt-get remove --purge --assume-yes -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold --force-yes %s" % line)

        # add new user
        print " --> Adding new user"
        our_current += 1
        self.update_progress(total=our_total, current=our_current, message=_("Adding new user to the system"))
        chroot_exec('adduser --disabled-login --gecos "{real_name}" {username}'.format(real_name=setup.real_name.replace('"', r'\"'), username=setup.username))
        for group in 'adm audio bluetooth cdrom dialout dip fax floppy fuse lpadmin netdev plugdev powerdev sambashare scanner sudo tape users vboxusers video'.split():
            chroot_exec("adduser {user} {group}".format(user=setup.username, group=group))

        # [XK] Save passwords
        # Using a temporary file fails for the new user (but correctly sets the root's password)
        setup.password1 = setup.password1.replace('"', '\\"')
        chroot_exec("echo \"%s:%s\" | chpasswd" % (setup.username, setup.password1))
        chroot_exec("echo \"root:%s\" | chpasswd" % setup.password1)

        # Set autologin for user if they so elected
        if setup.autologin:
            # LightDM
            chroot_exec(r"sed -i -r 's/^#?(autologin-user)\s*=.*/\1={user}/' /etc/lightdm/lightdm.conf".format(user=setup.username))
            # MDM
            chroot_exec(r"sed -i -r -e '/^AutomaticLogin(Enable)?\s*=/d' -e 's/^(\[daemon\])/\1\nAutomaticLoginEnable=true\nAutomaticLogin={user}/' /etc/mdm/mdm.conf".format(user=setup.username))
            # GDM3
            chroot_exec(r"sed -i -r -e '/^(#\s*)?AutomaticLogin(Enable)?\s*=/d' -e 's/^(\[daemon\])/\1\nAutomaticLoginEnable=true\nAutomaticLogin={user}/' /etc/gdm3/daemon.conf".format(user=setup.username))
            # KDE4
            chroot_exec(r"sed -i -r -e 's/^#?(AutomaticLoginEnable)\s*=.*/\1=true/' -e 's/^#?(AutomaticLoginUser)\s*.*/\1={user}/' /etc/kde4/kdm/kdmrc".format(user=setup.username))
            # LXDM
            chroot_exec(r"sed -i -r -e 's/^#?(autologin)\s*=.*/\1={user}/' /etc/lxdm/lxdm.conf".format(user=setup.username))
            # SLiM
            chroot_exec(r"sed -i -r -e 's/^#?(default_user)\s.*/\1  {user}/' -e 's/^#?(auto_login)\s.*/\1  yes/' /etc/slim.conf".format(user=setup.username))
        else:
            # [XK] LightDM uses autologin in live session
            chroot_exec(r"sed -i -r 's/^#?(autologin-user)\s*=.*/\1=/' /etc/lightdm/lightdm.conf")

        # Add user's face
        shell_exec("cp /tmp/live-installer-face.png /target/home/%s/.face" % setup.username)
        chroot_exec("chown %s:%s /home/%s/.face" % (setup.username, setup.username, setup.username))

        # write the /etc/fstab
        print " --> Writing fstab"
        our_current += 1
        self.update_progress(total=our_total, current=our_current, message=_("Writing filesystem mount information to /etc/fstab"))
        if not os.path.exists("/target/etc/fstab"):
            shell_exec("echo '#### Static Filesystem Table File' > /target/etc/fstab")
        if not setup.skip_mount:
            with open("/target/etc/fstab", "a") as fstab:
                for part in setup.partitions:
                    if not part.mount_as: continue
                    uuid = "UUID=%s" % getoutput('blkid -s UUID -o value ' + part.partition.path) or part.partition.path
                    fsck = 0 if part.type in ('ntfs', 'swap') else 1 if part.mount_as == '/' else 2
                    opts = 'rw,errors=remount-ro' if 'ext' in part.type else 'sw' if part.type == 'swap' else 'defaults'
                    fs = 'vfat' if part.type.startswith('fat') else part.type
                    fstab.write('{uuid}\t{part.mount_as}\t{fs}\t{opts}\t0\t{fsck}\n'.format(**locals()))

    def finish_install(self, setup):
        # Steps:
        our_total = 11
        our_current = 4

        # write host+hostname infos
        print " --> Writing hostname"
        our_current += 1
        self.update_progress(total=our_total, current=our_current, message=_("Setting hostname"))
        hostnamefh = open("/target/etc/hostname", "w")
        hostnamefh.write("%s\n" % setup.hostname)
        hostnamefh.close()
        hostsfh = open("/target/etc/hosts", "w")
        hostsfh.write("127.0.0.1\tlocalhost\n")
        hostsfh.write("127.0.1.1\t%s\n" % setup.hostname)
        hostsfh.write("# The following lines are desirable for IPv6 capable hosts\n")
        hostsfh.write("::1     localhost ip6-localhost ip6-loopback\n")
        hostsfh.write("fe00::0 ip6-localnet\n")
        hostsfh.write("ff00::0 ip6-mcastprefix\n")
        hostsfh.write("ff02::1 ip6-allnodes\n")
        hostsfh.write("ff02::2 ip6-allrouters\n")
        hostsfh.write("ff02::3 ip6-allhosts\n")
        hostsfh.close()

        # set the locale
        print " --> Setting the locale"
        our_current += 1
        self.update_progress(total=our_total, current=our_current, message=_("Setting locale"))
        shell_exec("echo \"%s.UTF-8 UTF-8\" >> /target/etc/locale.gen" % setup.language)
        chroot_exec("locale-gen")
        shell_exec("echo \"\" > /target/etc/default/locale")
        chroot_exec("update-locale LANG=\"%s.UTF-8\"" % setup.language)
        chroot_exec("update-locale LANG=%s.UTF-8" % setup.language)

        # set the timezone
        print " --> Setting the timezone"
        shell_exec("echo \"%s\" > /target/etc/timezone" % setup.timezone)
        shell_exec("cp /target/usr/share/zoneinfo/%s /target/etc/localtime" % setup.timezone)

        # localizing
        if setup.language != "en_US":
            if os.path.exists("/lib/live/mount/medium/pool"):
                print " --> Localizing packages"
                our_current += 1
                self.update_progress(total=our_total, current=our_current, message=_("Localizing packages"))
                shell_exec("mkdir -p /target/debs")
                language_code = setup.language
                if "_" in setup.language:
                    language_code = setup.language.split("_")[0]
                l10ns = getoutput("find /lib/live/mount/medium/pool | grep 'l10n-%s\\|hunspell-%s'" % (language_code, language_code))
                for l10n in l10ns.split("\n"):
                    shell_exec("cp %s /target/debs/" % l10n)
                chroot_exec("dpkg -i /debs/*")
                shell_exec("rm -rf /target/debs")
            if hasInternetConnection:
                # [XK] Localize when not LMDE
                loc = Localize(setup.language, our_total, our_current)
                loc.set_progress_hook(self.update_progress)
                loc.start()
                our_current = loc.our_current

        # [XK] Configure Plymouth
        our_current += 1
        if os.path.exists('/target/bin/plymouth'):
            print " --> Configuring Plymouth"
            self.update_progress(pulse=True, total=our_total, current=our_current, message=_("Configuring Plymouth"))
            plymouth = PlymouthSave()
            plymouth.save(setup.plymouth_enable)

        # [XK] Install multimedia
        our_current += 1
        if setup.multimedia_enable:
            if hasInternetConnection:
                print " --> Install multimedia"
                self.update_progress(pulse=True, total=our_total, current=our_current, message=_("Install multimedia"))
                packages = "libdvdcss2"
                if isAmd64:
                    packages += " w64codecs"
                else:
                    packages += " w32codecs"
                chroot_exec("apt-get install --assume-yes -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold --force-yes %s" % packages)

        # [XK] Configure sensors
        our_current += 1
        if os.path.exists('/target/usr/sbin/sensors-detect'):
            print " --> Configuring sensors"
            self.update_progress(pulse=True, total=our_total, current=our_current, message=_("Configuring sensors"))
            chroot_exec('/usr/bin/yes YES | /usr/sbin/sensors-detect')

        # [XK] Remove VirtualBox when not installing to VirtualBox
        if not runningInVirtualBox():
            print " --> Remove VirtualBox"
            self.update_progress(pulse=True, total=our_total, current=our_current, message=_("Removing VirtualBox"))
            chroot_exec("apt-get purge --assume-yes -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold --force-yes virtualbox*")

        # set the keyboard options..
        print " --> Setting the keyboard"
        our_current += 1
        self.update_progress(total=our_total, current=our_current, message=_("Setting keyboard options"))
        consolefh = open("/target/etc/default/console-setup", "r")
        newconsolefh = open("/target/etc/default/console-setup.new", "w")
        for line in consolefh:
            line = line.rstrip("\r\n")
            if(line.startswith("XKBMODEL=")):
                newconsolefh.write("XKBMODEL=\"%s\"\n" % setup.keyboard_model)
            elif(line.startswith("XKBLAYOUT=")):
                newconsolefh.write("XKBLAYOUT=\"%s\"\n" % setup.keyboard_layout)
            elif(line.startswith("XKBVARIANT=") and setup.keyboard_variant is not None):
                newconsolefh.write("XKBVARIANT=\"%s\"\n" % setup.keyboard_variant)
            else:
                newconsolefh.write("%s\n" % line)
        consolefh.close()
        newconsolefh.close()
        chroot_exec("rm /etc/default/console-setup")
        chroot_exec("mv /etc/default/console-setup.new /etc/default/console-setup")

        consolefh = open("/target/etc/default/keyboard", "r")
        newconsolefh = open("/target/etc/default/keyboard.new", "w")
        for line in consolefh:
            line = line.rstrip("\r\n")
            if(line.startswith("XKBMODEL=")):
                newconsolefh.write("XKBMODEL=\"%s\"\n" % setup.keyboard_model)
            elif(line.startswith("XKBLAYOUT=")):
                newconsolefh.write("XKBLAYOUT=\"%s\"\n" % setup.keyboard_layout)
            elif(line.startswith("XKBVARIANT=") and setup.keyboard_variant is not None):
                newconsolefh.write("XKBVARIANT=\"%s\"\n" % setup.keyboard_variant)
            else:
                newconsolefh.write("%s\n" % line)
        consolefh.close()
        newconsolefh.close()
        chroot_exec("rm /etc/default/keyboard")
        chroot_exec("mv /etc/default/keyboard.new /etc/default/keyboard")

        # write MBR (grub)
        print " --> Configuring Grub"
        our_current += 1
        if(setup.grub_device is not None):
            self.update_progress(pulse=True, total=our_total, current=our_current, message=_("Installing bootloader"))
            print " --> Running grub-install"
            chroot_exec("grub-install --force %s" % setup.grub_device)
            self.do_configure_grub(our_total, our_current)
            grub_retries = 0
            while (not self.do_check_grub(our_total, our_current)):
                self.do_configure_grub(our_total, our_current)
                grub_retries = grub_retries + 1
                if grub_retries >= 5:
                    self.error_message(message=_("WARNING: The grub bootloader was not configured properly! You need to configure it manually."))
                    break

        # recreate initramfs (needed in case of skip_mount also, to include things like mdadm/dm-crypt/etc in case its needed to boot a custom install)
        print " --> Configuring Initramfs"
        our_current += 1
        # [XK] Running update-initramfs takes a long time: check if it is necessary
        initrd = "/boot/initrd.img-".format(getoutput("uname -r"))
        update = os.path.getmtime(initrd) < time.time() - 86400 if os.path.isfile(initrd) else True
        if update:
            self.update_progress(pulse=True, total=our_total, current=our_current, message=_("Configuring initramfs"))
            chroot_exec("/usr/sbin/update-initramfs -t -u -k all")
            kernelversion = getoutput("uname -r")
            chroot_exec("/usr/bin/sha1sum /boot/initrd.img-%s > /var/lib/initramfs-tools/%s" % (kernelversion,kernelversion))

        # Clean APT
        print " --> Cleaning APT"
        our_current += 1
        self.update_progress(pulse=True, total=our_total, current=our_current, message=_("Cleaning APT"))
        shell_exec("chroot /target/ /bin/sh -c \"dpkg --configure -a\"")
        chroot_exec("sed -i 's/^deb cdrom/#deb cdrom/' /etc/apt/sources.list")
        chroot_exec("apt-get -y --force-yes autoremove")

        # now unmount it
        print " --> Unmounting partitions"
        shell_exec("umount --force /target/dev/shm")
        shell_exec("umount --force /target/dev/pts")
        if setup.gptonefi:
            shell_exec("umount --force /target/boot/efi")
            shell_exec("umount --force /target/media/cdrom")
        shell_exec("umount --force /target/dev/")
        shell_exec("umount --force /target/sys/")
        shell_exec("umount --force /target/proc/")
        shell_exec("rm -f /target/etc/resolv.conf")
        shell_exec("mv /target/etc/resolv.conf.bk /target/etc/resolv.conf")
        if(not setup.skip_mount):
            for partition in setup.partitions:
                if(partition.mount_as is not None and partition.mount_as != "" and partition.mount_as != "/" and partition.mount_as != "swap"):
                    self.do_unmount("/target" + partition.mount_as)
            self.do_unmount("/target")
        self.do_unmount("/source")

        self.update_progress(done=True, message=_("Installation finished"))
        print " --> All done"

    def do_configure_grub(self, our_total, our_current):
        self.update_progress(pulse=True, total=our_total, current=our_current, message=_("Configuring bootloader"))
        print " --> Running grub-mkconfig"
        #chroot_exec("grub-mkconfig -o /boot/grub/grub.cfg")
        grub_output = getoutput("chroot /target/ /bin/sh -c \"grub-mkconfig -o /boot/grub/grub.cfg\"")
        grubfh = open("/var/log/live-installer-grub-output.log", "w")
        grubfh.writelines(grub_output)
        grubfh.close()

    def do_check_grub(self, our_total, our_current):
        self.update_progress(pulse=True, total=our_total, current=our_current, message=_("Checking bootloader"))
        print " --> Checking Grub configuration"
        time.sleep(5)
        found_entry = False
        if os.path.exists("/target/boot/grub/grub.cfg"):
            grubfh = open("/target/boot/grub/grub.cfg", "r")
            for line in grubfh:
                line = line.rstrip("\r\n")
                if ("menuentry" in line):
                    found_entry = True
                    print " --> Found Grub entry: %s " % line
            grubfh.close()
            return (found_entry)
        else:
            print "!No /target/boot/grub/grub.cfg file found!"
            return False

    def do_mount(self, device, dest, type, options=None):
        ''' Mount a filesystem '''
        options = '-o ' + options if options else ''
        cmd = "mount {options} -t {type} {device} {dest}".format(**locals())
        #print 'Executing:', cmd
        shell_exec(cmd)

    def do_unmount(self, mountpoint):
        ''' Unmount a filesystem '''
        cmd = "umount %s" % mountpoint
        #print 'Executing:', cmd
        shell_exec(cmd)


# Represents the choices made by the user
class Setup(object):
    language = None
    timezone = None
    keyboard_model = None
    keyboard_layout = None
    keyboard_variant = None
    partitions = [] #Array of PartitionSetup objects
    username = None
    hostname = None
    autologin = False
    password1 = None
    password2 = None
    real_name = None
    grub_device = None
    plymouth_enable = None
    multimedia_enable = None
    disks = []
    target_disk = None
    gptonefi = False
    # Optionally skip all mouting/partitioning for advanced users with custom setups (raid/dmcrypt/etc)
    # Make sure the user knows that they need to:
    #  * Mount their target directory structure at /target
    #  * NOT mount /target/dev, /target/dev/shm, /target/dev/pts, /target/proc, and /target/sys
    #  * Manually create /target/etc/fstab after init_install has completed and before finish_install is called
    #  * Install cryptsetup/dmraid/mdadm/etc in target environment (using chroot) between init_install and finish_install
    #  * Make sure target is mounted using the same block device as is used in /target/etc/fstab (eg if you change the name of a dm-crypt device between now and /target/etc/fstab, update-initramfs will likely fail)
    skip_mount = False

    #Descriptions (used by the summary screen)
    keyboard_model_description = None
    keyboard_layout_description = None
    keyboard_variant_description = None

    def print_setup(self):
        if __debug__:
            print "-------------------------------------------------------------------------"
            print "language: %s" % self.language
            print "timezone: %s" % self.timezone
            print "keyboard: %s - %s (%s) - %s - %s (%s)" % (self.keyboard_model, self.keyboard_layout, self.keyboard_variant, self.keyboard_model_description, self.keyboard_layout_description, self.keyboard_variant_description)
            print "user: %s (%s)" % (self.username, self.real_name)
            print "autologin: ", self.autologin
            print "hostname: %s " % self.hostname
            print "passwords: %s - %s" % (self.password1, self.password2)
            print "grub_device: %s " % self.grub_device

            # [XK] Print Plymouth and multimedia settings
            print "plymouth enable: %s " % self.plymouth_enable
            print "multimedia install: %s " % self.multimedia_enable

            print "skip_mount: %s" % self.skip_mount
            if (not self.skip_mount):
                print "target_disk: %s " % self.target_disk
                if self.gptonefi:
                    print "GPT partition table: True"
                else:
                    print "GPT partition table: False"
                print "disks: %s " % self.disks
                print "partitions:"
                for partition in self.partitions:
                    partition.print_partition()
            print "-------------------------------------------------------------------------"
