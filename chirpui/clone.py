#!/usr/bin/python
#
# Copyright 2008 Dan Smith <dsmith@danplanet.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import threading
import os

import gtk
import gobject

from chirp import platform, directory, detect, chirp_common
from chirpui import miscwidgets, cloneprog, inputdialog, common, config

AUTO_DETECT_STRING = "Auto Detect (Icom Only)"

class CloneSettings:
    def __init__(self):
        self.port = None
        self.radio_class = None

    def __str__(self):
        s = ""
        if self.radio_class:
            return "%s %s on %s" % (self.radio_class.VENDOR,
                                    self.radio_class.MODEL,
                                    self.port)
        else:
            return "Detect %s on %s" % (self.detect_fn, self.port)

class CloneSettingsDialog(gtk.Dialog):
    def __make_field(self, label, widget):
        l = gtk.Label(label)
        self.__table.attach(l, 0, 1, self.__row, self.__row+1)
        self.__table.attach(widget, 1, 2, self.__row, self.__row+1)
        self.__row += 1

        l.show()
        widget.show()

    def __make_port(self, port):
        conf = config.get("state")

        ports = platform.get_platform().list_serial_ports()
        if not port:
            if conf.get("last_port"):
                port = conf.get("last_port")
            elif ports:
                port = ports[0]

        return miscwidgets.make_choice(ports, True, port)

    def __make_model(self):
        return miscwidgets.make_choice([], False)

    def __make_vendor(self, model):
        vendors = {}
        for rclass in sorted(directory.DRV_TO_RADIO.values()):
            if not vendors.has_key(rclass.VENDOR):
                vendors[rclass.VENDOR] = []

            if rclass.VENDOR not in detect.DETECT_FUNCTIONS:
                vendors[rclass.VENDOR].append(rclass)

        self.__vendors = vendors

        conf = config.get("state")
        if not conf.get("last_vendor"):
            conf.set("last_vendor", sorted(vendors.keys())[0])

        last_vendor = conf.get("last_vendor")
        if last_vendor not in vendors.keys():
            last_vendor = vendors.keys()[0]

        v = miscwidgets.make_choice(vendors.keys(), False, last_vendor)

        def _changed(box, vendors, model):
            models = vendors[box.get_active_text()]

            model.get_model().clear()
            for rclass in models:
                model.append_text(rclass.MODEL)
            if not models:
                model.append_text("Detect")

            model_names = [x.MODEL for x in models]
            if conf.get("last_model") in model_names:
                model.set_active(model_names.index(conf.get("last_model")))
            else:
                model.set_active(0)

        v.connect("changed", _changed, vendors, model)
        _changed(v, vendors, model)

        return v

    def __make_ui(self, settings):
        self.__table = gtk.Table(3, 2)
        self.__table.set_row_spacings(3)
        self.__table.set_col_spacings(10)
        self.__row = 0

        self.__port = self.__make_port(settings and settings.port or None)
        self.__modl = self.__make_model()
        self.__vend = self.__make_vendor(self.__modl)

        self.__make_field("Port", self.__port)
        self.__make_field("Vendor", self.__vend)
        self.__make_field("Model", self.__modl)

        if settings and settings.radio_class:
            common.combo_select(self.__vend, settings.radio_class.VENDOR)
            self.__modl.get_model().clear()
            self.__modl.append_text(settings.radio_class.MODEL)
            common.combo_select(self.__modl, settings.radio_class.MODEL)
            self.__vend.set_sensitive(False)
            self.__modl.set_sensitive(False)

        self.__table.show()
        self.vbox.pack_start(self.__table, 1, 1, 1)

    def __init__(self, settings=None, parent=None, title="Radio"):
        buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                   gtk.STOCK_OK, gtk.RESPONSE_OK)
        gtk.Dialog.__init__(self, title,
                            parent=parent,
                            flags=gtk.DIALOG_MODAL)
        self.__make_ui(settings)
        self.__cancel_button = self.add_button(gtk.STOCK_CANCEL,
                                               gtk.RESPONSE_CANCEL)
        self.__okay_button = self.add_button(gtk.STOCK_OK,
                                             gtk.RESPONSE_OK)
        self.__okay_button.grab_default()
        self.__okay_button.grab_focus()

    def run(self):
        r = gtk.Dialog.run(self)
        if r != gtk.RESPONSE_OK:
            return None

        vendor = self.__vend.get_active_text()
        model = self.__modl.get_active_text()

        cs = CloneSettings()
        cs.port = self.__port.get_active_text()
        if model == "Detect":
            try:
                cs.radio_class = detect.DETECT_FUNCTIONS[vendor](cs.port)
                if not cs.radio_class:
                    raise Exception("Unable to detect radio on %s" % cs.port)
            except Exception, e:
                d = inputdialog.ExceptionDialog(e)
                d.run()
                d.destroy()
                return None
        else:
            for rclass in directory.DRV_TO_RADIO.values():
                if rclass.MODEL == model:
                    cs.radio_class = rclass
                    break
            if not cs.radio_class:
                common.show_error("Internal error: Unable to upload to %s" % model)
                print self.__vendors
                return None

        conf = config.get("state")
        conf.set("last_port", cs.port)
        conf.set("last_vendor", cs.radio_class.VENDOR)
        conf.set("last_model", cs.radio_class.MODEL)

        return cs

class CloneCancelledException(Exception):
    pass

class CloneThread(chirp_common.KillableThread):
    def __status(self, status):
        gobject.idle_add(self.__progw.status, status)

    def __init__(self, radio, direction, cb=None, parent=None):
        threading.Thread.__init__(self)

        self.__radio = radio
        self.__out = direction == "out"
        self.__cback = cb
        self.__cancelled = False

        self.__progw = cloneprog.CloneProg(parent=parent, cancel=self.cancel)

    def cancel(self):
        self.__cancelled = True
        self.kill(CloneCancelledException)

    def run(self):
        print "Clone thread started"

        gobject.idle_add(self.__progw.show)

        self.__radio.status_fn = self.__status
        
        try:
            if self.__out:
                self.__radio.sync_out()
            else:
                self.__radio.sync_in()

            emsg = None
        except Exception, e:
            common.log_exception()
            print "Clone failed: %s" % e
            emsg = e

        gobject.idle_add(self.__progw.hide)

        # NB: Compulsory close of the radio's serial connection
        self.__radio.pipe.close()

        print "Clone thread ended"

        if self.__cback and not self.__cancelled:
            gobject.idle_add(self.__cback, self.__radio, emsg)

if __name__ == "__main__":
    d = CloneSettingsDialog("/dev/ttyUSB0")
    r = d.run()
    print r
