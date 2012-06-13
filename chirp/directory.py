# Copyright 2010 Dan Smith <dsmith@danplanet.com>
# Copyright 2012 Tom Hayward <tom@tomh.us>
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

from chirp import icf
from chirp import chirp_common, util, rfinder, radioreference, errors

def radio_class_id(cls):
    """Return a unique identification string for @cls"""
    ident = "%s_%s" % (cls.VENDOR, cls.MODEL)
    if cls.VARIANT:
        ident += "_%s" % cls.VARIANT
    ident = ident.replace("/", "_")
    ident = ident.replace(" ", "_")
    ident = ident.replace("(", "")
    ident = ident.replace(")", "")
    return ident

ALLOW_DUPS = False
def enable_reregistrations():
    """Set the global flag ALLOW_DUPS=True, which will enable a driver
    to re-register for a slot in the directory without triggering an
    exception"""
    global ALLOW_DUPS
    if not ALLOW_DUPS:
        print "NOTE: driver re-registration enabled"
    ALLOW_DUPS = True

def register(cls):
    """Register radio @cls with the directory"""
    global DRV_TO_RADIO
    ident = radio_class_id(cls)
    if ident in DRV_TO_RADIO.keys():
        if ALLOW_DUPS:
            print "Replacing existing driver id `%s'" % ident
        else:
            raise Exception("Duplicate radio driver id `%s'" % ident)
    DRV_TO_RADIO[ident] = cls
    RADIO_TO_DRV[cls] = ident
    print "Registered %s = %s" % (ident, cls.__name__)

    return cls

DRV_TO_RADIO = {}
RADIO_TO_DRV = {}

def get_radio(driver):
    """Get radio driver class by identification string"""
    if DRV_TO_RADIO.has_key(driver):
        return DRV_TO_RADIO[driver]
    else:
        raise Exception("Unknown radio type `%s'" % driver)

def get_driver(rclass):
    """Get the identification string for a given class"""
    if RADIO_TO_DRV.has_key(rclass):
        return RADIO_TO_DRV[rclass]
    elif RADIO_TO_DRV.has_key(rclass.__bases__[0]):
        return RADIO_TO_DRV[rclass.__bases__[0]]
    else:
        raise Exception("Unknown radio type `%s'" % rclass)

def icf_to_image(icf_file, img_file):
    # FIXME: Why is this here?
    """Convert an ICF file to a .img file"""
    mdata, mmap = icf.read_file(icf_file)
    img_data = None

    for model in DRV_TO_RADIO.values():
        try:
            if model._model == mdata:
                img_data = mmap.get_packed()[:model._memsize]
                break
        except Exception:
            pass # Skip non-Icoms

    if img_data:
        f = file(img_file, "wb")
        f.write(img_data)
        f.close()
    else:
        print "Unsupported model data:"
        print util.hexprint(mdata)
        raise Exception("Unsupported model")

def get_radio_by_image(image_file):
    """Attempt to get the radio class that owns @image_file"""
    if image_file.startswith("radioreference://"):
        _, _, zipcode, username, password = image_file.split("/", 4)
        rr = radioreference.RadioReferenceRadio(None)
        rr.set_params(zipcode, username, password)
        return rr
    
    if image_file.startswith("rfinder://"):
        _, _, email, passwd, lat, lon, miles = image_file.split("/")
        rf = rfinder.RFinderRadio(None)
        rf.set_params((float(lat), float(lon)), int(miles), email, passwd)
        return rf
    
    if os.path.exists(image_file) and icf.is_icf_file(image_file):
        tempf = tempfile.mktemp()
        icf_to_image(image_file, tempf)
        print "Auto-converted %s -> %s" % (image_file, tempf)
        image_file = tempf

    if os.path.exists(image_file):
        f = file(image_file, "rb")
        filedata = f.read()
        f.close()
    else:
        filedata = ""

    for rclass in DRV_TO_RADIO.values():
        if not issubclass(rclass, chirp_common.FileBackedRadio):
            continue
        if rclass.match_model(filedata, image_file):
            return rclass(image_file)
    raise errors.ImageDetectFailed("Unknown file format")
