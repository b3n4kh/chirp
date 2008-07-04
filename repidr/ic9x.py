import repidr_common
import errors
import util

import ic9x_ll

class IC9xRadio(repidr_common.IcomRadio):
    BAUD_RATE = 38400

    def get_memory(self, number, vfo=1):
        if vfo not in [1, 2]:
            raise errors.InvalidValueError("VFO must be 1 or 2")

        if number < 0 or number > 999:
            raise errors.InvalidValueError("Number must be between 0 and 999")

        ic9x_ll.send_magic(self.pipe)


        mframe = ic9x_ll.get_memory(self.pipe, vfo, number)

        mem = repidr_common.Memory()
        mem.freq = mframe._freq
        mem.number = mframe._number
        mem.name = mframe._name
        mem.vfo = mframe._vfo

        return mem

    def get_memories(self, vfo=1):
        memories = []

        for i in range(999):
            memories.append(self.get_memory(i, vfo))

        return memories
        
    def set_memory(self, memory):
        mframe = ic9x_ll.IC92MemoryFrame()
        mframe.set_memory(memory)
        mframe.make_raw() # FIXME
        
        result = ic9x_ll.send(self.pipe, mframe._rawdata)

        if len(result) == 0:
            raise errors.InvalidDataError("No response from radio")

        if result[0]._data != "\xfb":
            raise errors.InvalidDataError("Radio reported error")
