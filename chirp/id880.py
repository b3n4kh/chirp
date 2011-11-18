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

from chirp import chirp_common, icf
from chirp import bitwise

mem_format = """
struct {
  u24  freq;
  u16  offset;
  u16  rtone:6,
       ctone:6,
       unknown1:1,
       mode:3;
  u8   dtcs;
  u8   tune_step:4,
       unknown2:4;
  u8   unknown3;
  u8   unknown4:1,
       tmode:3,
       duplex:2,
       dtcs_polarity:2;
  char name[8];
  u8   unknwon5:1,
       digital_code:7;
  char urcall[7];
  char r1call[7];
  char r2call[7];
} memory[1000];

#seekto 0xAA80;
u8 used_flags[132];

#seekto 0xAB04;
u8 skip_flags[132];
u8 pskip_flags[132];

#seekto 0xAD00;
struct {
  u8 bank;
  u8 index;
} bank_info[1000];

#seekto 0xB550;
struct {
  char name[6];
} bank_names[26];

#seekto 0xDE56;
struct {
  char call[8];
  char extension[4];
} mycall[6];

struct {
  char call[8];
} urcall[60];

struct {
  char call[8];
  char extension[4];
} rptcall[99];

"""

TMODES = ["", "Tone", "?2", "TSQL", "DTCS", "TSQL-R", "DTCS-R", ""]
DUPLEX = ["", "-", "+", "?3"]
DTCSP  = ["NN", "NR", "RN", "RR"]
MODES  = ["FM", "NFM", "?2", "AM", "NAM", "DV"]

def decode_call(sevenbytes):
    if len(sevenbytes) != 7:
        raise Exception("%i (!=7) bytes to decode_call" % len(sevenbytes))

    i = 0
    rem = 0
    str = ""
    for byte in [ord(x) for x in sevenbytes]:
        i += 1

        mask = (1 << i) - 1           # Mask is 0x01, 0x03, 0x07, etc

        code = (byte >> i) | rem      # Code gets the upper bits of remainder
                                      # plus all but the i lower bits of this
                                      # byte
        str += chr(code)

        rem = (byte & mask) << 7 - i  # Remainder for next time are the masked
                                      # bits, moved to the high places for the
                                      # next round

    # After seven trips gathering overflow bits, we chould have seven
    # left, which is the final character
    str += chr(rem)

    return str.rstrip()

def encode_call(call):
    call = call.ljust(8)
    val = 0
    
    buf = []
    
    for i in range(0, 8):
        byte = ord(call[i])
        if i > 0:
            last = buf[i-1]
            himask = ~((1 << (7-i)) - 1) & 0x7F
            last |= (byte & himask) >> (7-i)
            buf[i-1] = last
        else:
            himask = 0

        buf.append((byte & ~himask) << (i+1))

    return "".join([chr(x) for x in buf[:7]])

class ID880Radio(icf.IcomCloneModeRadio, chirp_common.IcomDstarSupport):
    VENDOR = "Icom"
    MODEL = "ID-880H"

    _model = "\x31\x67\x00\x01"
    _memsize = 62976
    _endframe = "Icom Inc\x2eB1"

    _ranges = [(0x0000, 0xF5c0, 32),
               (0xF5c0, 0xf5e0, 16),
               (0xf5e0, 0xf600, 32)]

    MYCALL_LIMIT = (1, 7)
    URCALL_LIMIT = (1, 60)
    RPTCALL_LIMIT = (1, 99)

    def process_mmap(self):
        self._memobj = bitwise.parse(mem_format, self._mmap)

    def get_features(self):
        rf = chirp_common.RadioFeatures()
        rf.requires_call_lists = False
        rf.has_bank_index = True
        rf.valid_modes = [x for x in MODES if x is not None]
        rf.valid_tmodes = list(TMODES)
        rf.valid_duplexes = list(DUPLEX)
        rf.valid_tuning_steps = list(chirp_common.TUNING_STEPS)
        rf.valid_bands = [(118000000, 173995000), (230000000, 549995000),
                          (810000000, 823990000), (849000000, 868990000),
                          (894000000, 999990000)]
        rf.valid_skips = ["", "S", "P"]
        rf.valid_name_length = 8
        rf.memory_bounds = (0, 999)
        return rf

    def get_available_bank_index(self, bank):
        indexes = []
        for i in range(0, 1000):
            try:
                mem = self.get_memory(i)
            except:
                continue
            if mem.bank == bank and mem.bank_index >= 0:
                indexes.append(mem.bank_index)

        for i in range(0, 99):
            if i not in indexes:
                return i

        raise errors.RadioError("Out of slots in this bank")

    def get_raw_memory(self, number):
        return repr(self._memobj.memory[number])

    def get_banks(self):
        _banks = self._memobj.bank_names

        banks = []
        for i in range(0, 26):
            banks.append(str(_banks[i].name).rstrip())

        return banks

    def set_banks(self, banks):
        _banks = self._memobj.bank_names

        for i in range(0, 26):
            _banks[i].name = banks[i].ljust(6)[:6]

    def _get_freq(self, _mem):
        val = int(_mem.freq)

        if val & 0x00200000:
            mult = 6250
        else:
            mult = 5000

        val &= 0x0003FFFF

        return (val * mult)

    def _set_freq(self, _mem, freq):
        if chirp_common.is_fractional_step(freq):
            mult = 6250
            flag = 0x00200000
        else:
            mult = 5000
            flag = 0x00000000

        _mem.freq = (freq / mult) | flag

    def get_memory(self, number):
        bytepos = number / 8
        bitpos = 1 << (number % 8)

        _mem = self._memobj.memory[number]
        _used = self._memobj.used_flags[bytepos]

        is_used = ((_used & bitpos) == 0)

        if is_used and MODES[_mem.mode] == "DV":
            mem = chirp_common.DVMemory()
            mem.dv_urcall = decode_call(str(_mem.urcall))
            mem.dv_rpt1call = decode_call(str(_mem.r1call))
            mem.dv_rpt2call = decode_call(str(_mem.r2call))
        else:
            mem = chirp_common.Memory()

        mem.number = number

        if number < 1000:
            _bank = self._memobj.bank_info[number]
            mem.bank = _bank.bank
            mem.bank_index = _bank.index
            if mem.bank == 0xFF:
                mem.bank = None
                mem.bank_index = -1

            _skip = self._memobj.skip_flags[bytepos]
            _pskip = self._memobj.pskip_flags[bytepos]
            if _skip & bitpos:
                mem.skip = "S"
            elif _pskip & bitpos:
                mem.skip = "P"
        else:
            pass # FIXME: Special memories

        if not is_used:
            mem.empty = True
            return mem

        mem.freq = self._get_freq(_mem)
        mem.offset = (_mem.offset * 5) * 1000
        mem.rtone = chirp_common.TONES[_mem.rtone]
        mem.ctone = chirp_common.TONES[_mem.ctone]
        mem.tmode = TMODES[_mem.tmode]
        mem.duplex = DUPLEX[_mem.duplex]
        mem.mode = MODES[_mem.mode]
        mem.dtcs = chirp_common.DTCS_CODES[_mem.dtcs]
        mem.dtcs_polarity = DTCSP[_mem.dtcs_polarity]
        if _mem.tune_step >= len(chirp_common.TUNING_STEPS):
            mem.tuning_step = 5.0
        else:
            mem.tuning_step = chirp_common.TUNING_STEPS[_mem.tune_step]
        mem.name = str(_mem.name).rstrip()

        return mem

    def _wipe_memory(self, mem, char):
        mem.set_raw(char * (mem.size() / 8))

    def set_memory(self, mem):
        bitpos = (1 << (mem.number % 8))
        bytepos = mem.number / 8

        _mem = self._memobj.memory[mem.number]
        _used = self._memobj.used_flags[bytepos]

        was_empty = _used & bitpos

        if mem.empty:
            _used |= bitpos
            self._wipe_memory(_mem, "\xFF")
            return

        _used &= ~bitpos

        if was_empty:
            self._wipe_memory(_mem, "\x00")

        self._set_freq(_mem, mem.freq)
        _mem.offset = int((mem.offset / 1000) / 5)
        _mem.rtone = chirp_common.TONES.index(mem.rtone)
        _mem.ctone = chirp_common.TONES.index(mem.ctone)
        _mem.tmode = TMODES.index(mem.tmode)
        _mem.duplex = DUPLEX.index(mem.duplex)
        _mem.mode = MODES.index(mem.mode)
        _mem.dtcs = chirp_common.DTCS_CODES.index(mem.dtcs)
        _mem.dtcs_polarity = DTCSP.index(mem.dtcs_polarity)
        _mem.tune_step = chirp_common.TUNING_STEPS.index(mem.tuning_step)
        _mem.name = mem.name.ljust(8)

        if isinstance(mem, chirp_common.DVMemory):
            _mem.urcall = encode_call(mem.dv_urcall)
            _mem.r1call = encode_call(mem.dv_rpt1call)
            _mem.r2call = encode_call(mem.dv_rpt2call)
            
        if mem.number < 1000:
            _bank = self._memobj.bank_info[mem.number]
            if mem.bank:
                _bank.bank = mem.bank
                _bank.index = mem.bank_index
            else:
                _bank.bank = 0xFF
                _bank.index = 0

            skip = self._memobj.skip_flags[bytepos]
            pskip = self._memobj.pskip_flags[bytepos]
            if mem.skip == "S":
                skip |= bitpos
            else:
                skip &= ~bitpos
            if mem.skip == "P":
                pskip |= bitpos
            else:
                pskip &= ~bitpos

    def get_urcall_list(self):
        _calls = self._memobj.urcall
        calls = ["CQCQCQ"]

        for i in range(*self.URCALL_LIMIT):
            calls.append(str(_calls[i-1].call))

        return calls

    def get_mycall_list(self):
        _calls = self._memobj.mycall
        calls = []

        for i in range(*self.MYCALL_LIMIT):
            calls.append(str(_calls[i-1].call))

        return calls

    def get_repeater_call_list(self):
        _calls = self._memobj.rptcall
        calls = ["*NOTUSE*"]

        for i in range(*self.RPTCALL_LIMIT):
            # FIXME: Not sure where the repeater list actually is
            calls.append("UNSUPRTD")
            continue

        return calls
        
class ID80Radio(ID880Radio):
    MODEL = "ID-880H"

    _model = "\x31\x55\x00\x01"
    
