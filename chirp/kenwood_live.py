#!/usr/bin/python
#
# Copyright 2010 Dan Smith <dsmith@danplanet.com>
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

from chirp import chirp_common, errors

DEBUG = True

DUPLEX = { 0 : "", 1 : "+", 2 : "-" }
MODES = { 0 : "FM", 1 : "AM" }
STEPS = list(chirp_common.TUNING_STEPS)
STEPS.append(100.0)

THF6_MODES = ["FM", "WFM", "AM", "LSB", "USB", "CW"]

def rev(hash, value):
    reverse = {}
    for k, v in hash.items():
        reverse[v] = k

    return reverse[value]

LOCK = threading.Lock()

def command(s, command, *args):
    global LOCK

    LOCK.acquire()
    cmd = command
    if args:
        cmd += " " + " ".join(args)
    if DEBUG:
        print "PC->D7: %s" % cmd
    s.write(cmd + "\r")

    result = ""
    while not result.endswith("\r"):
        result += s.read(8)

    if DEBUG:
        print "D7->PC: %s" % result.strip()

    LOCK.release()

    return result.strip()

def get_id(s):
    r = command(s, "ID")
    if " " in r:
        return r.split(" ")[1]
    else:
        raise errors.RadioError("No response from radio")

def get_tmode(tone, ctcss, dcs):
    if dcs and int(dcs) == 1:
        return "DTCS"
    elif int(ctcss):
        return "TSQL"
    elif int(tone):
        return "Tone"
    else:
        return ""

def iserr(result):
    return result in ["N", "?"]

class KenwoodLiveRadio(chirp_common.LiveRadio):
    BAUD_RATE = 9600
    VENDOR = "Kenwood"
    MODEL = ""

    _vfo = 0
    _upper = 200

    def __init__(self, *args, **kwargs):
        chirp_common.LiveRadio.__init__(self, *args, **kwargs)

        self.pipe.setTimeout(0.1)

        self.__memcache = {}

        self.__id = get_id(self.pipe)
        print "Talking to a %s" % self.__id

        command(self.pipe, "AI", "0")

    def _cmd_get_memory(self, number):
        return "MR", "%i,0,%03i" % (self._vfo, number)

    def _cmd_get_memory_name(self, number):
        return "MNA", "%i,%03i" % (self._vfo, number)

    def _cmd_set_memory(self, number, spec):
        if spec:
            spec = "," + spec
        return "MW", "%i,0,%03i%s" % (self._vfo, number, spec)

    def _cmd_set_memory_name(self, number, name):
        return "MNA", "%i,%03i,%s" % (self._vfo, number, name)

    def get_memory(self, number):
        if number < 0 or number > self._upper:
            raise errors.InvalidMemoryLocation( \
                "Number must be between 0 and %i" % self._upper)
        if self.__memcache.has_key(number):
            return self.__memcache[number]

        result = command(self.pipe, *self._cmd_get_memory(number))
        if result == "N":
            mem = chirp_common.Memory()
            mem.number = number
            mem.empty = True
            self.__memcache[mem.number] = mem
            return mem
        elif " " not in result:
            print "Not sure what to do with this: `%s'" % result
            raise errors.RadioError("Unexpected result returned from radio")

        value = result.split(" ")[1]
        spec = value.split(",")

        mem = self._parse_mem_spec(spec)
        self.__memcache[mem.number] = mem

        result = command(self.pipe, *self._cmd_get_memory_name(number))
        if " " in result:
            value = result.split(" ", 1)[1]
            if value.count(",") == 2:
                zero, loc, mem.name = value.split(",")
            else:
                loc, mem.name = value.split(",")
 
        return mem

    def _make_mem_spec(self, mem):
        pass

    def _parse_mem_spec(self, spec):
        pass

    def set_memory(self, memory):
        if memory.number < 0 or memory.number > self._upper:
            raise errors.InvalidMemoryLocation( \
                "Number must be between 0 and %i" % self._upper)

        spec = self._make_mem_spec(memory)
        spec = ",".join(spec)
        r1 = command(self.pipe, *self._cmd_set_memory(memory.number, spec))
        if not iserr(r1):
            r2 = command(self.pipe, *self._cmd_set_memory_name(memory.number,
                                                               memory.name))
            if not iserr(r2):
                self.__memcache[memory.number] = memory
            else:
                raise errors.InvalidDataError("Radio refused %i" % memory.number)
        else:
            raise errors.InvalidDataError("Radio refused %i" % memory.number)

    def erase_memory(self, number):
        if not self.__memcache.has_key(number):
            return

        r = command(self.pipe, *self._cmd_set_memory(number, ""))
        if iserr(r):
            raise errors.RadioError("Radio refused delete of %i" % number)
        del self.__memcache[number]

class THD7Radio(KenwoodLiveRadio):
    MODEL = "TH-D7(a)(g)"

    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.has_dtcs = False
        rf.has_dtcs_polarity = False
        rf.has_bank = False
        rf.has_mode = True
        rf.has_tuning_step = False
        rf.valid_modes = MODES.values()
        rf.valid_tmodes = ["", "Tone", "TSQL"]
        rf.valid_characters = chirp_common.CHARSET_ALPHANUMERIC
        rf.valid_name_length = 7
        rf.memory_bounds = (1, self._upper)
        return rf

    def _make_mem_spec(self, mem):
        spec = ( \
            "%011i" % mem.freq,
            "%i" % STEPS.index(mem.tuning_step),
            "%i" % rev(DUPLEX, mem.duplex),
            "0",
            "%i" % (mem.tmode == "Tone"),
            "%i" % (mem.tmode == "TSQL"),
            "", # DCS Flag
            "%02i" % (chirp_common.TONES.index(mem.rtone) + 1),
            "", # DCS Code
            "%02i" % (chirp_common.TONES.index(mem.ctone) + 1),
            "%09i" % mem.offset,
            "%i" % rev(MODES, mem.mode),
            "0")

        return spec

    def _parse_mem_spec(self, spec):
        mem = chirp_common.Memory()

        mem.number = int(spec[2])
        mem.freq = int(spec[3], 10)
        mem.tuning_step = STEPS[int(spec[4])]
        mem.duplex = DUPLEX[int(spec[5])]
        mem.tmode = get_tmode(spec[7], spec[8], spec[9])
        mem.rtone = chirp_common.TONES[int(spec[10]) - 1]
        mem.ctone = chirp_common.TONES[int(spec[12]) - 1]
        if spec[11] and spec[11].isdigit():
            mem.dtcs = chirp_common.DTCS_CODES[int(spec[11][:-1]) - 1]
        else:
            print "Unknown or invalid DCS: %s" % spec[11]
        if spec[13]:
            mem.offset = int(spec[13])
        else:
            mem.offset = 0
        mem.mode = MODES[int(spec[14])]

        return mem

class TMD700Radio(KenwoodLiveRadio):
    MODEL = "TH-D700"

    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.has_dtcs = True
        rf.has_dtcs_polarity = False
        rf.has_bank = False
        rf.has_mode = False
        rf.has_tuning_step = False
        rf.valid_modes = ["FM"]
        rf.valid_tmodes = ["", "Tone", "TSQL", "DTCS"]
        rf.valid_characters = chirp_common.CHARSET_ALPHANUMERIC
        rf.valid_name_length = 7
        rf.memory_bounds = (1, self._upper)
        return rf

    def _make_mem_spec(self, mem):
        spec = ( \
            "%011i" % mem.freq,
            "%i" % STEPS.index(mem.tuning_step),
            "%i" % rev(DUPLEX, mem.duplex),
            "0",
            "%i" % (mem.tmode == "Tone"),
            "%i" % (mem.tmode == "TSQL"),
            "%i" % (mem.tmode == "DTCS"),
            "%02i" % (chirp_common.TONES.index(mem.rtone) + 1),
            "%03i0" % (chirp_common.DTCS_CODES.index(mem.dtcs) + 1),
            "%02i" % (chirp_common.TONES.index(mem.ctone) + 1),
            "%09i" % mem.offset,
            "%i" % rev(MODES, mem.mode),
            "0")

        return spec

    def _parse_mem_spec(self, spec):
        mem = chirp_common.Memory()

        mem.number = int(spec[2])
        mem.freq = int(spec[3])
        mem.tuning_step = STEPS[int(spec[4])]
        mem.duplex = DUPLEX[int(spec[5])]
        mem.tmode = get_tmode(spec[7], spec[8], spec[9])
        mem.rtone = chirp_common.TONES[int(spec[10]) - 1]
        mem.ctone = chirp_common.TONES[int(spec[12]) - 1]
        if spec[11] and spec[11].isdigit():
            mem.dtcs = chirp_common.DTCS_CODES[int(spec[11][:-1]) - 1]
        else:
            print "Unknown or invalid DCS: %s" % spec[11]
        if spec[13]:
            mem.offset = int(spec[13])
        else:
            mem.offset = 0
        mem.mode = MODES[int(spec[14])]

        return mem

class TMV7Radio(KenwoodLiveRadio):
    MODEL = "TM-V7"

    mem_upper_limit = 200 # Will be updated

    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.has_dtcs = False
        rf.has_dtcs_polarity = False
        rf.has_bank = False
        rf.has_mode = False
        rf.has_tuning_step = False
        rf.valid_modes = ["FM"]
        rf.valid_tmodes = ["", "Tone", "TSQL"]
        rf.valid_characters = chirp_common.CHARSET_ALPHANUMERIC
        rf.valid_name_length = 7
        rf.has_sub_devices = True
        rf.memory_bounds = (1, self._upper)
        return rf

    def _make_mem_spec(self, mem):
        spec = ( \
            "%03i" % mem.number,
            "%011i" % mem.freq,
            "%i" % STEPS.index(mem.tuning_step),
            "%i" % rev(DUPLEX, mem.duplex),
            "0",
            "%i" % (mem.tmode == "Tone"),
            "%i" % (mem.tmode == "TSQL"),
            "0",
            "%02i" % (chirp_common.TONES.index(mem.rtone) + 1),
            "000",
            "%02i" % (chirp_common.TONES.index(mem.ctone) + 1),
            "",
            "0")

        return spec

    def _parse_mem_spec(self, spec):
        mem = chirp_common.Memory()
        mem.number = int(spec[2])
        mem.freq = int(spec[3])
        mem.tuning_step = STEPS[int(spec[4])]
        mem.duplex = DUPLEX[int(spec[5])]
        if int(spec[7]):
            mem.tmode = "Tone"
        elif int(spec[8]):
            mem.tmode = "TSQL"
        mem.rtone = chirp_common.TONES[int(spec[10]) - 1]
        mem.ctone = chirp_common.TONES[int(spec[12]) - 1]

        return mem

    def get_sub_devices(self):
        return [TMV7RadioVHF(self.pipe), TMV7RadioUHF(self.pipe)]

    def __test_location(self, loc):
        mem = self.get_memory(loc)
        if not mem.empty:
            # Memory was not empty, must be valid
            return True

        # Mem was empty (or invalid), try to set it
        if self._vfo == 0:
            mem.freq = 144000000
        else:
            mem.freq = 440000000
        mem.empty = False
        try:
            self.set_memory(mem)
        except:
            # Failed, so we're past the limit
            return False

        # Erase what we did
        try:
            self.erase_memory(loc)
        except:
            pass # V7A Can't delete just yet

        return True

    def _detect_split(self):
        # Valid  splits:
        limits = [50, 70, 90, 110, 130, 140]

        for limit in limits:
            print "Testing %s" % (limit)
            if not self.__test_location(limit+1):
                self._upper = limit
                break

        print "Detected limit for VFO %i is %i" % (self._vfo,
                                                   self._upper)


class TMV7RadioSub(TMV7Radio):
    def __init__(self, pipe):
        KenwoodLiveRadio.__init__(self, pipe)
        self._detect_split()

class TMV7RadioVHF(TMV7RadioSub):
    VARIANT = "VHF"
    _vfo = 0

class TMV7RadioUHF(TMV7RadioSub):
    VARIANT = "UHF"
    _vfo = 1

if __name__ == "__main__":
    import serial
    import sys

    s = serial.Serial(port=sys.argv[1], baudrate=9600, xonxoff=True, timeout=1)

    print get_id(s)
    print get_memory(s, int(sys.argv[2]))

class THF6ARadio(KenwoodLiveRadio):
    MODEL = "TH-F6A"

    _upper = 399

    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.has_dtcs_polarity = False
        rf.has_bank = False
        rf.valid_modes = list(THF6_MODES)
        rf.valid_tmodes = ["", "Tone", "TSQL", "DTCS"]
        rf.valid_tuning_steps = list(STEPS)
        rf.valid_bands = [(1000, 1300000000)]
        rf.valid_skips = ["", "S"]
        rf.valid_characters = chirp_common.CHARSET_ALPHANUMERIC
        rf.valid_name_length = 7
        rf.memory_bounds = (0, self._upper)
        return rf

    def _cmd_set_memory(self, number, spec):
        if spec:
            spec = "," + spec
        return "MW", "0,%03i%s" % (number, spec)

    def _cmd_get_memory(self, number):
        return "MR", "0,%03i" % number

    def _cmd_get_memory_name(self, number):
        return "MNA", "%03i" % number

    def _cmd_set_memory_name(self, number, name):
        return "MNA", "%03i,%s" % (number, name)

    def _parse_mem_spec(self, spec):
        mem = chirp_common.Memory()

        mem.number = int(spec[1])
        mem.freq = int(spec[2])
        mem.tuning_step = STEPS[int(spec[3])]
        mem.duplex = DUPLEX[int(spec[4])]
        mem.tmode = get_tmode(spec[6], spec[7], spec[8])
        mem.rtone = chirp_common.TONES[int(spec[9])]
        mem.ctone = chirp_common.TONES[int(spec[10])]
        if spec[11] and spec[11].isdigit():
            mem.dtcs = chirp_common.DTCS_CODES[int(spec[11])]
        else:
            print "Unknown or invalid DCS: %s" % spec[11]
        if spec[11]:
            mem.offset = int(spec[12])
        else:
            mem.offset = 0
        mem.mode = THF6_MODES[int(spec[13])]
        if spec[14] == "1":
            mem.skip = "S"

        return mem

    def _make_mem_spec(self, mem):
        spec = ( \
            "%011i" % mem.freq,
            "%i" % STEPS.index(mem.tuning_step),
            "%i" % rev(DUPLEX, mem.duplex),
            "0",
            "%i" % (mem.tmode == "Tone"),
            "%i" % (mem.tmode == "TSQL"),
            "%i" % (mem.tmode == "DTCS"),
            "%02i" % (chirp_common.TONES.index(mem.rtone)),
            "%02i" % (chirp_common.TONES.index(mem.ctone)),
            "%03i" % (chirp_common.DTCS_CODES.index(mem.dtcs)),
            "%09i" % mem.offset,
            "%i" % (THF6_MODES.index(mem.mode)),
            "%i" % (mem.skip == "S"))

        return spec

D710_DUPLEX = ["", "+", "-", "split"]
D710_MODES = ["FM", "NFM", "AM"]
D710_SKIP = ["", "S"]
D710_STEPS = [5.0, 6.25, 8.33, 10.0, 12.5, 15.0, 20.0, 25.0, 30.0, 50.0, 100.0]

class TMD710Radio(KenwoodLiveRadio):
    MODEL = "TM-D710"
    
    _upper = 999

    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.can_odd_split = True
        rf.has_dtcs_polarity = False
        rf.has_bank = False
        rf.valid_tmodes = ["", "Tone", "TSQL", "DTCS"]
        rf.valid_modes = D710_MODES
        rf.valid_duplexes = D710_DUPLEX
        rf.valid_tuning_steps = D710_STEPS
        rf.valid_characters = chirp_common.CHARSET_ALPHANUMERIC
        rf.valid_name_length = 7
        rf.memory_bounds = (0, 999)
        return rf

    def _cmd_get_memory(self, number):
        return "ME", "%03i" % number

    def _cmd_get_memory_name(self, number):
        return "MN", "%03i" % number

    def _cmd_set_memory(self, number, spec):
        return "ME", "%03i,%s" % (number, spec)

    def _cmd_set_memory_name(self, number, name):
        return "MN", "%03i,%s" % (number, name)

    def _parse_mem_spec(self, spec):
        mem = chirp_common.Memory()

        mem.number = int(spec[0])
        mem.freq = int(spec[1])
        mem.tuning_step = D710_STEPS[int(spec[2], 16)]
        mem.duplex = D710_DUPLEX[int(spec[3])]
        # Reverse
        if int(spec[5]):
            mem.tmode = "Tone"
        elif int(spec[6]):
            mem.tmode = "TSQL"
        elif int(spec[7]):
            mem.tmode = "DTCS"
        mem.rtone = chirp_common.TONES[int(spec[8])]
        mem.ctone = chirp_common.TONES[int(spec[9])]
        mem.dtcs = chirp_common.DTCS_CODES[int(spec[10])]
        mem.offset = int(spec[11])
        mem.mode = D710_MODES[int(spec[12])]
        # TX Frequency
        if int(spec[13]):
            mem.duplex = "split"
            mem.offset = int(spec[13])
        # Unknown
        mem.skip = D710_SKIP[int(spec[15])] # Memory Lockout

        return mem

    def _make_mem_spec(self, mem):
        print "Index %i for step %.2f" % (chirp_common.TUNING_STEPS.index(mem.tuning_step), mem.tuning_step)
        spec = ( \
            "%010i" % mem.freq,
            "%X" % D710_STEPS.index(mem.tuning_step),
            "%i" % (0 if mem.duplex == "split" else D710_DUPLEX.index(mem.duplex)),
            "0", # Reverse
            "%i" % (mem.tmode == "Tone" and 1 or 0),
            "%i" % (mem.tmode == "TSQL" and 1 or 0),
            "%i" % (mem.tmode == "DTCS" and 1 or 0),
            "%02i" % (chirp_common.TONES.index(mem.rtone)),
            "%02i" % (chirp_common.TONES.index(mem.ctone)),
            "%03i" % (chirp_common.DTCS_CODES.index(mem.dtcs)),
            "%08i" % (0 if mem.duplex == "split" else mem.offset), # Offset
            "%i" % D710_MODES.index(mem.mode),
            "%010i" % (mem.offset if mem.duplex == "split" else 0), # TX Frequency
            "0", # Unknown
            "%i" % D710_SKIP.index(mem.skip), # Memory Lockout
            )

        return spec

class TMV71Radio(TMD710Radio):
	MODEL = "TM-V71"	
