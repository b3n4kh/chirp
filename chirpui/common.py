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

import gtk
import gobject

import threading

from chirp import errors

class Editor(gobject.GObject):
    __gsignals__ = {
        'changed' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ())
        }

    root = None

    def __init__(self):
        gobject.GObject.__init__(self)

    def focus(self):
        pass

gobject.type_register(Editor)

class RadioJob:
    def __init__(self, cb, func, *args, **kwargs):
        self.cb = cb
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.desc = "Working"

    def set_desc(self, desc):
        self.desc = desc

    def execute(self, radio):
        try:
            func = getattr(radio, self.func)
        except AttributeError, e:
            print "No such radio function `%s'" % self.func
            return

        try:
            print "Running %s (%s %s)" % (self.func,
                                          str(self.args),
                                          str(self.kwargs))
            result = func(*self.args, **self.kwargs)
        except errors.InvalidMemoryLocation, e:
            result = e
        except Exception, e:
            print "Exception running RadioJob: %s" % e
            log_exception()
            result = e

        if self.cb:
            gobject.idle_add(self.cb, result)

class RadioThread(threading.Thread, gobject.GObject):
    __gsignals__ = {
        "status" : (gobject.SIGNAL_RUN_LAST,
                    gobject.TYPE_NONE,
                    (gobject.TYPE_STRING,)),
        }

    def __init__(self, radio):
        threading.Thread.__init__(self)
        gobject.GObject.__init__(self)
        self.__queue = []
        self.__counter = threading.Semaphore(0)
        self.__enabled = True
        self.__lock = threading.Lock()
        self.__runlock = threading.Lock()
        self.radio = radio

    def _qlock(self):
        self.__lock.acquire()

    def _qunlock(self):
        self.__lock.release()

    # This is the external lock, which stops any threads from running
    # so that the radio can be operated synchronously
    def lock(self):
        self.__runlock.acquire()

    def unlock(self):
        self.__runlock.release()

    def submit(self, job):
        self._qlock()
        self.__queue.append(job)
        self._qunlock()
        self.__counter.release()

    def flush(self):
        self._qlock()
        self.__queue = []
        self._qunlock()

    def stop(self):
        self.flush()
        self.__counter.release()
        self.__enabled = False
    
    def status(self, msg):
        gobject.idle_add(self.emit, "status", "[%i] %s" % (len(self.__queue),
                                                           msg))
            
    def run(self):
        while self.__enabled:
            print "Waiting for a job"
            self.status("Idle")
            self.__counter.acquire()

            self._qlock()
            try:
                job = self.__queue.pop(0)
            except IndexError:
                self._qunlock()
                break
            self._qunlock()
            
            self.lock()
            self.status(job.desc)
            job.execute(self.radio)
            self.unlock()
   
        print "RadioThread exiting"

def log_exception():
	import traceback
	import sys

	print "-- Exception: --"
	traceback.print_exc(limit=30, file=sys.stdout)
	print "------"

def show_error(msg, parent=None):
    d = gtk.MessageDialog(buttons=gtk.BUTTONS_OK, parent=parent)
    d.set_property("text", msg)

    if not parent:
        d.set_position(gtk.WIN_POS_CENTER_ALWAYS)

    d.run()
    d.destroy()

def ask_yesno_question(msg, parent=None):
    d = gtk.MessageDialog(buttons=gtk.BUTTONS_YES_NO, parent=parent)
    d.set_property("text", msg)

    if not parent:
        d.set_position(gtk.WIN_POS_CENTER_ALWAYS)

    r = d.run()
    d.destroy()

    return r == gtk.RESPONSE_YES
