#!/usr/bin/env python
#-*- coding: utf-8 -*-

import os
import re
import gettext
from utils import chroot_exec, get_config_dict
import apt
import apt_pkg

# i18n
gettext.install("live-installer", "/usr/share/locale")

CONFIG_FILE = '/etc/live-installer/live-installer.conf'


class Localize():
    def __init__(self, language, our_total, our_current):
        self.cache = apt.Cache()
        self.language = language
        self.our_current = our_current
        self.our_total = our_total
        self.locale = self.language.lower().split("_")
        self.scriptDir = os.path.dirname(os.path.realpath(__file__))
        self.edition = 'all'
        config = get_config_dict(CONFIG_FILE)
        self.info = config.get('info', '/etc/linuxmint/info')
        if os.path.exists(self.info):
            config = get_config_dict(self.info)
            self.edition = config.get('EDITION', 'all').replace(' ', '').lower()

    def set_progress_hook(self, progresshook):
        ''' Set a callback to be called on progress updates '''
        ''' i.e. def my_callback(progress_type, message, current_progress, total) '''
        ''' Where progress_type is any off PROGRESS_START, PROGRESS_UPDATE, PROGRESS_COMPLETE, PROGRESS_ERROR '''
        self.update_progress = progresshook

    def start(self):
        self.our_current += 1
        self.update_progress(total=self.our_total, current=self.our_current, message=_("Update apt cache"))
        chroot_exec("apt-get update")
        self.applications()
        self.languageSpecific()

    def languageSpecific(self):
        self.our_current += 1
        localizeConf = os.path.join(self.scriptDir, "localize/%s" % self.language)
        if os.path.exists(localizeConf):
            try:
                print " --> Localizing %s" % self.edition
                config = get_config_dict(localizeConf)
                packages = config.get(self.edition, '').strip()
                if packages != "":
                    self.update_progress(total=self.our_total, current=self.our_current, message=_("Install additional localized packages"))
                    chroot_exec("apt-get --yes --force-yes install %s" % packages)
            except Exception as detail:
                msg = "ERROR: %s" % detail
                print msg
                self.update_progress(total=self.our_total, current=self.our_current, message=msg)

    def applications(self):
        if self.language != "en_US":
            # Localize KDE
            self.our_current += 1
            if self.isPackageInstalled("kde-runtime"):
                print " --> Localizing KDE"
                self.update_progress(total=self.our_total, current=self.our_current, message=_("Localizing KDE"))
                lan = "".join(self.locale)
                package = "kde-l10n-%s" % lan
                print "    > package = %s" % package
                if not self.doesPackageExist(package):
                    lan = self.locale[0]
                    package = "kde-l10n-%s" % lan
                    print "    > package = %s" % package
                    if not self.doesPackageExist(package):
                        package = ""
                if package != "":
                    chroot_exec("apt-get install --yes --force-yes %s" % package)

            # Localize LibreOffice
            self.our_current += 1
            if self.isPackageInstalled("libreoffice"):
                print " --> Localizing LibreOffice"
                self.update_progress(total=self.our_total, current=self.our_current, message=_("Localizing LibreOffice"))
                lan = "-".join(self.locale)
                package = "libreoffice-l10n-%s" % lan
                print "    > package = %s" % package
                if not self.doesPackageExist(package):
                    lan = self.locale[0]
                    package = "libreoffice-l10n-%s" % lan
                    print "    > package = %s" % package
                    if not self.doesPackageExist(package):
                        package = ""
                if package != "":
                    chroot_exec("apt-get install --yes --force-yes %s" % package)
                    chroot_exec("apt-get install --yes --force-yes libreoffice-help-%s" % lan)
                    chroot_exec("apt-get install --yes --force-yes myspell-%s" % lan)

            # Localize AbiWord
            self.our_current += 1
            if self.isPackageInstalled("abiword"):
                print " --> Localizing AbiWord"
                self.update_progress(total=self.our_total, current=self.our_current, message=_("Localizing AbiWord"))
                chroot_exec("apt-get install --yes --force-yes aspell-%s" % self.locale[0])

            # Localize Firefox
            self.our_current += 1
            isESR = self.isPackageInstalled("firefox-esr")
            if isESR or self.isPackageInstalled("firefox"):
                esr = ""
                if isESR:
                    esr = "esr-"
                print " --> Localizing Firefox"
                self.update_progress(total=self.our_total, current=self.our_current, message=_("Localizing Firefox"))
                lan = "-".join(self.locale)
                package = "firefox-%sl10n-%s" % (esr, lan)
                print "    > package = %s" % package
                if not self.doesPackageExist(package):
                    lan = self.locale[0]
                    package = "firefox-%sl10n-%s" % (esr, lan)
                    print "    > package = %s" % package
                    if not self.doesPackageExist(package):
                        package = ""
                if package != "":
                    chroot_exec("apt-get install --yes --force-yes %s" % package)
                    self.localizePref('/etc/skel/.mozilla/firefox/mwad0hks.default/prefs.js')

            # Localize Thunderbird
            self.our_current += 1
            if self.isPackageInstalled("thunderbird"):
                print " --> Localizing Thunderbird"
                self.update_progress(total=self.our_total, current=self.our_current, message=_("Localizing Thunderbird"))
                lan = "-".join(self.locale)
                package = "thunderbird-l10n-%s" % lan
                print "    > package = %s" % package
                if not self.doesPackageExist(package):
                    lan = self.locale[0]
                    package = "thunderbird-l10n-%s" % lan
                    print "    > package = %s" % package
                    if not self.doesPackageExist(package):
                        package = ""
                if package != "":
                    chroot_exec("apt-get install --yes --force-yes %s" % package)
                    self.localizePref("/etc/skel/.thunderbird/pjzwmea6.default/prefs.js")

    def localizePref(self, prefsPath):
        if os.path.exists(prefsPath):
            with open(prefsPath, 'r') as f:
                text = f.read()

            # Create language strings for Mozilla
            lan = "_".join(self.locale)
            if self.locale[0] == self.locale[1].lower():
                lan = self.locale[0]
            lanMoz = "-".join(self.locale)

            # Set Mozilla parameters in prefs file
            mozLine = "user_pref(\"spellchecker.dictionary\", \"%s\");" % lan
            text = self.searchAndReplace(text, ".*spellchecker\.dictionary.*", mozLine, mozLine)

            mozLine = "user_pref(\"extensions.qls.visiblemenuitems\", \"%s#en-US\");" % lanMoz
            text = self.searchAndReplace(text, ".*extensions\.qls\.visiblemenuitems.*", mozLine, mozLine)

            mozLine = "user_pref(\"extensions.qls.contentlocale\", \"%s\");" % lanMoz
            text = self.searchAndReplace(text, ".*extensions\.qls\.contentlocale.*", mozLine, mozLine)

            mozLine = "user_pref(\"extensions.qls.locale\", \"%s\");" % lanMoz
            text = self.searchAndReplace(text, ".*extensions\.qls\.locale.*", mozLine, mozLine)

            mozLine = "user_pref(\"general.useragent.locale\", \"%s\");" % lanMoz
            text = self.searchAndReplace(text, ".*general\.useragent\.locale.*", mozLine, mozLine)

            with open(prefsPath, 'w') as f:
                f.write(text)

    def searchAndReplace(self, text, regexpSearch, replaceWithString, appendString=None):
        matchObj = re.search(regexpSearch, text)
        if matchObj:
            text = re.sub(regexpSearch, replaceWithString, text)
        else:
            if appendString is not None:
                text += "\n%s" % appendString
        return text

    # Check if package exists
    def doesPackageExist(self, package):
        return package in self.cache

    # Check if a package is installed
    def isPackageInstalled(self, packageName, alsoCheckVersion=True):
        isInstalled = False
        try:
            pkg = self.cache[packageName]
            if (not pkg.is_installed or
                pkg._pkg.current_state != apt_pkg.CURSTATE_INSTALLED or
                self.cache._depcache.broken_count > 0):
                isInstalled = False
            elif alsoCheckVersion:
                if pkg.installed.version == pkg.candidate.version:
                    isInstalled = True
            else:
                isInstalled = True
        except:
            pass
        return isInstalled
