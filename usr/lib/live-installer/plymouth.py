#!/usr/bin/env python
#-*- coding: utf-8 -*-

import re
import os
from glob import glob
from utils import chroot_exec

kmsDrv = ['nouveau', 'radeon', 'intel']

manufacturerDrivers = [
['ATI', ['fglrx', 'radeonhd', 'radeon', 'fbdev', 'vesa']],
['NVIDIA', ['nvidia', 'nouveau', 'fbdev', 'vesa']],
['VIA', ['chrome9', 'openchrome', 'unichrome']],
['INTEL', ['intel', 'fbdev', 'vesa']],
['VBOXVIDEO', ['vboxvideo']]
]


# Handles plymouth saving
class PlymouthSave():
    def __init__(self):
        self.modulesPath = '/target/etc/initramfs-tools/modules'
        self.boot = '/target/etc/default/grub'
        self.setThemePath = '/usr/sbin/plymouth-set-default-theme'
        self.theme = ''
        for themeDir in glob(os.path.join('/usr/share/plymouth/themes', '*-logo')):
            self.theme = os.path.basename(themeDir)
            break
        self.resolution = '1024x768'

    # Save given theme and resolution
    def save(self, enable=True):
        if self.theme == '':
            enable = False
        try:
            if os.path.isfile(self.modulesPath) and os.path.isfile(self.boot):

                # Set resolution
                cmd = 'sed -i -e \'/GRUB_GFXMODE=/ c GRUB_GFXMODE=%s\' %s' % (self.resolution, self.boot)
                os.system(cmd)

                # Read grub for debugging purposes
                f = open(self.boot, 'r')
                newGrub = f.read()
                f.close()
                print '\nNew grub:\n%s\n' % newGrub

                # Set the theme
                if enable:
                    chroot_exec('%s %s' % (self.setThemePath, self.theme))

                chroot_exec('update-grub')

            else:
                print 'Plymouth unconfigured - cannot find: %s or %s' % (self.modulesPath, self.boot)

        except Exception, detail:
            print detail

    # Return graphics module used by X.org
    def getUsedDriver(self):
        # find the most recent X.org log
        module = None
        logDir = '/var/log/'
        logPath = None
        maxTime = 0
        for f in glob(os.path.join(logDir, 'Xorg.*.log')):
            mtime = os.stat(f).st_mtime
            if mtime > maxTime:
                maxTime = mtime
                logPath = f

        # Open the log file
        lines = []
        with open(logPath) as f:
            lines = list(f.read().splitlines())

        # Search for "randr" in each line and check the previous line for the used module
        lineCnt = -1
        for line in lines:
            lineCnt += 1
            matchObj = re.search('\)\srandr\s', line, flags=re.IGNORECASE)
            if matchObj:
                prevLine = lines[lineCnt - 1].lower()
                module = self.matchModuleInString(prevLine)
                break

        print 'Used graphics driver: %s' % module
        return module

    # Return the module found in a string (used by getUsedModule)
    def matchModuleInString(self, text):
        for manDrv in manufacturerDrivers:
            for mod in manDrv[1]:
                if mod in text:
                    return mod
        return None
