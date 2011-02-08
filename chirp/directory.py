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

import os
import tempfile

from chirp import id800, id880, ic2820, ic2200, ic9x, icx8x, ic2100, ic2720
from chirp import icq7, icomciv, idrp, icf, ic9x_icf
from chirp import vx3, vx5, vx6, vx7, vx8, ft7800, ft50
from chirp import kenwood_live, tmv71, thd72
from chirp import xml, chirp_common, convert_icf, csv

DRV_TO_RADIO = {

    # Icom
    "ic2720"         : ic2720.IC2720Radio,
    "ic2820"         : ic2820.IC2820Radio,
    "ic2200"         : ic2200.IC2200Radio,
    "ic2100"         : ic2100.IC2100Radio,
    "ic9x"           : ic9x.IC9xRadio,
    "ic9x:A"         : ic9x.IC9xRadioA,
    "ic9x:B"         : ic9x.IC9xRadioB,
    "id800"          : id800.ID800v2Radio,
    "id880"          : id880.ID880Radio,
    "icx8x"          : icx8x.ICx8xRadio,
    "idrpx000v"      : idrp.IDRPx000V,
    "icq7"           : icq7.ICQ7Radio,
    "icom7200"       : icomciv.Icom7200Radio,

    # Yaesu
    "vx3"            : vx3.VX3Radio,
    "vx5"            : vx5.VX5Radio,
    "vx6"            : vx6.VX6Radio,
    "vx7"            : vx7.VX7Radio,
    "vx8"            : vx8.VX8Radio,
    "ft7800"         : ft7800.FT7800Radio,
    "ft7900"         : ft7800.FT7900Radio,
    "ft8800"         : ft7800.FT8800Radio,
    #"ft50"           : ft50.FT50Radio,

    # Kenwood
    "thd7"           : kenwood_live.THD7Radio,
    "thd72"          : thd72.THD72Radio,
    "tmd700"         : kenwood_live.TMD700Radio,
    "tmv7"           : kenwood_live.TMV7Radio,
    "v71a"           : tmv71.TMV71ARadio,
}

RADIO_TO_DRV = {}
for __key, __val in DRV_TO_RADIO.items():
    RADIO_TO_DRV[__val] = __key

def get_radio(driver):
    if DRV_TO_RADIO.has_key(driver):
        return DRV_TO_RADIO[driver]
    else:
        raise Exception("Unknown radio type `%s'" % driver)

def get_driver(radio):
    if RADIO_TO_DRV.has_key(radio):
        return RADIO_TO_DRV[radio]
    else:
        raise Exception("Unknown radio type `%s'" % radio)

def get_radio_by_image(image_file):
    if image_file.lower().endswith(".chirp"):
        return xml.XMLRadio(image_file)

    if image_file.lower().endswith(".csv"):
        return csv.CSVRadio(image_file)

    if icf.is_9x_icf(image_file):
        return ic9x_icf.IC9xICFRadio(image_file)

    if icf.is_icf_file(image_file):
        tempf = tempfile.mktemp()
        convert_icf.icf_to_image(image_file, tempf)
        print "Auto-converted %s -> %s" % (image_file, tempf)
        image_file = tempf

    f = file(image_file, "rb")
    filedata = f.read()
    f.close()

    for radio in DRV_TO_RADIO.values():
        if not issubclass(radio, chirp_common.CloneModeRadio):
            continue
        if radio.match_model(filedata):
            return radio(image_file)
    raise Exception("Unknown file format")

def get_radio_name(driver):
    cls = DRV_TO_RADIO[driver]
    return cls._get_name(cls)

if __name__ == "__main__":
    vendors = {
        "Icom" : {},
        "Yaesu" : {},
        "Kenwood" : {},
        }

    for radio in DRV_TO_RADIO.values():
        vendors[radio.VENDOR][radio.MODEL]
        print "%s %s:" % (radio.VENDOR, radio.MODEL)
        if radio.VARIANT:
            print "  Variant: %s" % radio.VARIANT
        print "  Baudrate: %i" % radio.BAUD_RATE
