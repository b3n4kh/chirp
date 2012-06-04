# Copyright 2012 Dan Smith <dsmith@danplanet.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from chirp import chirp_common

class InvalidValueError(Exception):
    """An invalid value was specified for a given setting"""
    pass

class InternalError(Exception):
    """A driver provided an invalid settings object structure"""
    pass

class RadioSettingValue:
    """Base class for a single radio setting"""
    def __init__(self):
        self._current = None
        self._has_changed = False

    def changed(self):
        """Returns True if the setting has been changed since init"""
        return self._has_changed

    def set_value(self, value):
        """Sets the current value, triggers changed"""
        if self._current != None and value != self._current:
            self._has_changed = True
        self._current = value

    def get_value(self):
        """Gets the current value"""
        return self._current

    def __trunc__(self):
        return int(self.get_value())

    def __str__(self):
        return str(self.get_value())

class RadioSettingValueInteger(RadioSettingValue):
    """An integer setting"""
    def __init__(self, minval, maxval, current, step=1):
        RadioSettingValue.__init__(self)
        self._min = minval
        self._max = maxval
        self._step = step
        self.set_value(current)

    def set_value(self, value):
        try:
            value = int(value)
        except:
            raise InvalidValueError("An integer is required")
        if value > self._max or value < self._min:
            raise InvalidValueError("Value %i not in range %i-%i" % (value,
                                                                     self._min,
                                                                     self._max))
        RadioSettingValue.set_value(self, value)

    def get_min(self):
        """Returns the minimum allowed value"""
        return self._min

    def get_max(self):
        """Returns the maximum allowed value"""
        return self._max

    def get_step(self):
        """Returns the step increment"""
        return self._step

class RadioSettingValueBoolean(RadioSettingValue):
    """A boolean setting"""
    def __init__(self, current):
        RadioSettingValue.__init__(self)
        self.set_value(current)

    def set_value(self, value):
        RadioSettingValue.set_value(self, bool(value))

    def __str__(self):
        return str(bool(self.get_value()))

class RadioSettingValueList(RadioSettingValue):
    """A list-of-strings setting"""
    def __init__(self, options, current):
        RadioSettingValue.__init__(self)
        self._options = options
        self.set_value(current)

    def set_value(self, value):
        if not value in self._options:
            raise InvalidValueError("%s is not valid for this setting" % value)
        RadioSettingValue.set_value(self, value)

    def get_options(self):
        """Returns the list of valid option values"""
        return self._options

    def __trunc__(self):
        return self._options.index(self._current)

class RadioSettingValueString(RadioSettingValue):
    """A string setting"""
    def __init__(self, minlength, maxlength, current,
                 autopad=True):
        RadioSettingValue.__init__(self)
        self._minlength = minlength
        self._maxlength = maxlength
        self._charset = chirp_common.CHARSET_ASCII
        self._autopad = autopad
        self.set_value(current)

    def set_charset(self, charset):
        """Sets the set of allowed characters"""
        self._charset = charset

    def set_value(self, value):
        if len(value) < self._minlength or len(value) > self._maxlength:
            raise InvalidValueError("Value must be between %i and %i chars" % (\
                    self._minlength, self._maxlength))
        if self._autopad:
            value = value.ljust(self._maxlength)
        for char in value:
            if char not in self._charset:
                raise InvalidValueError("Value contains invalid " +
                                        "character `%s'" % char)
        RadioSettingValue.set_value(self, value)

    def __str__(self):
        return self._current.rstrip()

class RadioSettingGroup(object):
    """A group of settings"""
    def _validate(self, element):
        # RadioSettingGroup can only contain RadioSettingGroup objects
        if not isinstance(element, RadioSettingGroup):
            raise InternalError("Incorrect type")

    def __init__(self, name, shortname, *elements):
        self._name = name           # Setting identifier
        self._shortname = shortname # Short human-readable name/description
        self.__doc__ = name         # Longer explanation/documentation
        self._elements = {}
        self._element_order = []
        
        for element in elements:
            self._validate(element)
            print "Appending element to %s" % self._name
            self.append(element)

    def get_name(self):
        """Returns the group name"""
        return self._name

    def get_shortname(self):
        """Returns the short group identifier"""
        return self._shortname

    def set_doc(self, doc):
        """Sets the docstring for the group"""
        self.__doc__ = doc

    def __str__(self):
        string = "{Settings Group %s:\n" % self._name
        for element in self._elements.values():
            string += str(element) + "\n"
        string += "}"
        return string

    # Kinda list interface

    def append(self, element):
        """Adds an element to the group"""
        self[element.get_name()] = element

    def __iter__(self):
        class RSGIterator:
            """Iterator for a RadioSettingsGroup"""
            def __init__(self, rsg):
                self.__rsg = rsg
                self.__i = 0
            def __iter__(self):
                return self
            def next(self):
                """Next Iterator Interface"""
                if self.__i >= len(self.__rsg.keys()):
                    raise StopIteration()
                e =  self.__rsg[self.__rsg.keys()[self.__i]]
                self.__i += 1
                return e
        return RSGIterator(self)

    # Dictionary interface

    def __len__(self):
        return len(self._elements)

    def __getitem__(self, name):
        return self._elements[name]

    def __setitem__(self, name, value):
        if name in self._element_order:
            raise KeyError("Duplicate item %s" % name)
        self._elements[name] = value
        self._element_order.append(name)

    def items(self):
        """Returns a key=>value set of elements, like a dict"""
        return [(name, self._elements[name]) for name in self._element_order]

    def keys(self):
        """Returns a list of string element names"""
        return self._element_order

    def values(self):
        """Returns the list of elements"""
        return [self._elements[name] for name in self._element_order]

class RadioSetting(RadioSettingGroup):
    """A single setting, which could be an array of items like a group"""
    def _validate(self, value):
        # RadioSetting can only contain RadioSettingValue objects
        if not isinstance(value, RadioSettingValue):
            raise InternalError("Incorrect type")

    def changed(self):
        """Returns True if any of the elements in the group have been changed"""
        for element in self._elements.values():
            if element.changed():
                return True
        return False

    def __str__(self):
        return "%s:%s" % (self._name, self.value)

    def __repr__(self):
        return "[RadioSetting %s:%s]" % (self._name, self._value)

    # Magic foo.value attribute
    def __getattr__(self, name):
        if name == "value":
            if len(self) == 1:
                return self._elements[self._element_order[0]]
            else:
                print self._elements
                raise InternalError("Setting %s is not a scalar" % self._name)
        else:
            return self.__dict__[name]

    def __setattr__(self, name, value):
        if name == "value":
            if len(self) == 1:
                self._elements[self._element_order[0]].set_value(value)
            else:
                raise InternalError("Setting %s is not a scalar" % self._name)
        else:
            self.__dict__[name] = value
            
    # List interface

    def append(self, value):
        index = len(self._element_order)
        self._elements[index] = value
        self._element_order.append(index)

    def __getitem__(self, name):
        if not isinstance(name, int):
            raise IndexError("Index `%s' is not an integer" % name)
        return self._elements[name].get_value()

    def __setitem__(self, name, value):
        if not isinstance(name, int):
            raise IndexError("Index `%s' is not an integer" % name)
        if self._elements.has_key(name):
            self._elements[name].set_value(value)
        else:
            self._elements[name] = value
