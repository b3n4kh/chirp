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

from chirp import chirp_common, yaesu_clone, vx6_ll
from chirp import bitwise

mem_format = """
#seekto 0x1ECA;
struct {
  u8 even_pskip:1,
     even_skip:1,
     even_valid:1,
     even_masked:1,
     odd_pskip:1,
     odd_skip:1,
     odd_valid:1,
     odd_masked:1;
} flags[450];

#seekto 0x21CA;
struct {
  u8 unknown1;
  u8 mode:2,
     duplex:2,
     tune_step:4;
  bbcd freq[3];
  u8 unknown2:6,
     tmode:2;
  u8 name[6];
  bbcd offset[3];
  u8 unknown3:2,
     tone:6;
  u8 unknown4:1,
     dcs:7;
  u8 unknown5;
} memory[900];
"""

DUPLEX = ["", "-", "+", "split"]
MODES  = ["FM", "AM", "WFM", "FM"] # last is auto
TMODES = ["", "Tone", "TSQL", "DTCS"]
STEPS = list(chirp_common.TUNING_STEPS)
STEPS.remove(6.25)
STEPS.remove(30.0)
STEPS.append(100.0)
STEPS.append(9.0)

CHARSET = ["%i" % int(x) for x in range(0, 10)] + \
    [chr(x) for x in range(ord("A"), ord("Z")+1)] + \
    list(" +-/?[]__?????????$%%?**.|=\\?@") + \
    list("?" * 100)

POWER_LEVELS = [chirp_common.PowerLevel("Hi", watts=5.00),
                chirp_common.PowerLevel("L3", watts=2.50),
                chirp_common.PowerLevel("L2", watts=1.00),
                chirp_common.PowerLevel("L1", watts=0.05)]
POWER_LEVELS_220 = [chirp_common.PowerLevel("L2", watts=0.30),
                    chirp_common.PowerLevel("L1", watts=0.05)]

class VX6Radio(yaesu_clone.YaesuCloneModeRadio):
    BAUD_RATE = 19200
    VENDOR = "Yaesu"
    MODEL = "VX-6"

    _model = "AH021"
    _memsize = 32587
    _block_lengths = [10, 32578]
    _block_size = 16

    def _update_checksum(self):
        vx6_ll.update_checksum(self._mmap)

    def _checksums(self):
        return [ yaesu_clone.YaesuChecksum(0x0000, 0x7F49) ]

    def process_mmap(self):
        self._memobj = bitwise.parse(mem_format, self._mmap)

    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.has_bank = False
        rf.has_dtcs_polarity = False
        rf.valid_modes = ["FM", "WFM", "AM"]
        rf.valid_tmodes = ["", "Tone", "TSQL", "DTCS"]
        rf.memory_bounds = (1, 900)
        rf.valid_bands = [(0.5, 998.990)]
        rf.can_odd_split = True
        rf.has_ctone = False
        return rf

    def get_raw_memory(self, number):
        return self._memobj.memory[number-1].get_raw()

    def get_memory(self, number):
        _mem = self._memobj.memory[number-1]
        _flg = self._memobj.flags[(number-1)/2]

        nibble = ((number-1) % 2) and "even" or "odd"
        used = _flg["%s_masked" % nibble] and _flg["%s_valid" % nibble]
        pskip = _flg["%s_pskip" % nibble]
        skip = _flg["%s_skip" % nibble]

        mem = chirp_common.Memory()
        mem.number = number
        if not used:
            mem.empty = True
            return mem

        mem.freq = chirp_common.fix_rounded_step(int(_mem.freq) / 1000.0)
        mem.offset = int(_mem.offset) / 1000.0
        mem.rtone = mem.ctone = chirp_common.TONES[_mem.tone]
        mem.tmode = TMODES[_mem.tmode]
        mem.duplex = DUPLEX[_mem.duplex]
        mem.mode = MODES[_mem.mode]
        mem.dtcs = chirp_common.DTCS_CODES[_mem.dcs]
        mem.tuning_step = STEPS[_mem.tune_step]
        mem.skip = pskip and "P" or skip and "S" or ""
        
        for i in _mem.name:
            if i == 0xFF:
                break
            mem.name += CHARSET[i & 0x7F]
        mem.name = mem.name.rstrip()

        return mem

    def set_memory(self, mem):
        _mem = self._memobj.memory[mem.number-1]
        _flag = self._memobj.flags[(mem.number-1)/2]

        nibble = ((mem.number-1) % 2) and "even" or "odd"
        
        was_valid = int(_flag["%s_valid" % nibble])

        _flag["%s_masked" % nibble] = not mem.empty
        _flag["%s_valid" % nibble] = not mem.empty
        if mem.empty:
            return

        _mem.freq = int(mem.freq * 1000)
        _mem.offset = int(mem.offset * 1000)
        _mem.tone = chirp_common.TONES.index(mem.rtone)
        _mem.tmode = TMODES.index(mem.tmode)
        _mem.duplex = DUPLEX.index(mem.duplex)
        _mem.mode = MODES.index(mem.mode)
        _mem.dcs = chirp_common.DTCS_CODES.index(mem.dtcs)
        _mem.tune_step = STEPS.index(mem.tuning_step)

        _flag["%s_pskip" % nibble] = mem.skip == "P"
        _flag["%s_skip" % nibble] = mem.skip == "S"

        _mem.name == ("\xFF" * 6)
        for i in range(0, 6):
            _mem.name[i] = CHARSET.index(mem.name.ljust(6)[i])

        if mem.name.strip():
            _mem.name[0] |= 0x80

    def filter_name(self, name):
        return chirp_common.name6(name, True)

