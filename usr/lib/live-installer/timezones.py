# coding: utf-8

from __future__ import division
import math
import re
import gtk
from commands import getoutput
from PIL import Image

TIMEZONE_RESOURCES = '/usr/share/live-installer/timezone/'

CC_IM = Image.open(TIMEZONE_RESOURCES + 'cc.png').convert('RGB')
BACK_IM = Image.open(TIMEZONE_RESOURCES + 'bg.png').convert('RGB')
DOT_IM = Image.open(TIMEZONE_RESOURCES + 'dot.png').convert('RGBA')

def to_float(position, wholedigits):
    assert position and len(position) > 4 and wholedigits < 9
    return float(position[:wholedigits + 1] + '.' + position[wholedigits + 1:])

MAP_CENTER = (373, 263)  # pixel center of where equatorial line and 0th meridian cross on our bg map; WARNING: cc.png relies on this exactly!
MAP_SIZE = BACK_IM.size  # size of the map image
assert MAP_SIZE == (800, 409), 'MAP_CENTER (et al.?) calculations depend on this size'

def pixel_position(lat, lon):
    """Transform latlong pair into map pixel coordinates"""
    dx = MAP_SIZE[0] / 2 / 180
    dy = MAP_SIZE[1] / 2 / 90
    # formulae from http://en.wikipedia.org/wiki/Miller_cylindrical_projection
    x = MAP_CENTER[0] + dx * lon
    y = MAP_CENTER[1] - dy * math.degrees(5/4 * math.log(math.tan(math.pi/4 + 2/5 * math.radians(lat))))
    return int(x), int(y)

TZ_SPLIT_COORDS = re.compile('([+-][0-9]+)([+-][0-9]+)')

def build_timezones(_installer):
    global installer
    installer = _installer
    installer.wTree.get_widget("image_timezones").set_from_file(TIMEZONE_RESOURCES + 'bg.png')
    model = gtk.ListStore(str, str, int, int)
    for line in getoutput("awk '/^[^#]/{ print $1,$2,$3 }' /usr/share/zoneinfo/zone.tab | sort -k3").split('\n'):
        ccode, coords, timezone = line.split()
        lat, lon = TZ_SPLIT_COORDS.search(coords).groups()
        x, y = pixel_position(to_float(lat, 2), to_float(lon, 3))
        if x < 0: x = MAP_SIZE[0] + x
        model.append((timezone, ccode, x, y))
    return model

def cb_combo_changed(combobox, model):
    row = combobox.get_active()
    if row: select_timezone(model[row])

def cb_map_clicked(widget, event, model):
    x, y = event.x, event.y
    print "Coords: %d %d" % (x, y)
    closest_timezone = min(model, key=lambda row: math.sqrt((x - row[2])**2 + (y - row[3])**2))
    print "Closest timezone %s" % closest_timezone[0]
    installer.wTree.get_widget("combo_timezones").set_active_iter(closest_timezone.iter)

# Timezone offsets color coded in cc.png
# If someone can make this more robust (maintainable), I buy you lunch!
TIMEZONE_COLORS = {
    "2b0000": "-11.0",
    "550000": "-10.0",
    "66ff05": "-9.5",
    "800000": "-9.0",
    "aa0000": "-8.0",
    "d40000": "-7.0",
    "ff0001": "-6.0",
    "66ff00": "-5.5",
    "ff2a2a": "-5.0",
    "c0ff00": "-4.5",
    "ff5555": "-4.0",
    "00ff00": "-3.5",
    "ff8080": "-3.0",
    "ffaaaa": "-2.0",
    "ffd5d5": "-1.0",
    "2b1100": "0.0",
    "552200": "1.0",
    "803300": "2.0",
    "aa4400": "3.0",
    "00ff66": "3.5",
    "d45500": "4.0",
    "00ccff": "4.5",
    "ff6600": "5.0",
    "0066ff": "5.5",
    "00ffcc": "5.75",
    "ff7f2a": "6.0",
    "cc00ff": "6.5",
    "ff9955": "7.0",
    "ffb380": "8.0",
    "ffccaa": "9.0",
    "aa0044": "9.5",
    "ffe6d5": "10.0",
    "d10255": "10.5",
    "d4aa00": "11.0",
    "fc0266": "11.5",
    "ffcc00": "12.0",
    "fd2c80": "12.75",
    "fc5598": "13.0",
}

def select_timezone(timezone):
    timezone, _cc, x, y = timezone
    def _get_image(overlay):
        """Superpose the picture of the timezone on the map"""
        im = BACK_IM.copy()
        if overlay:
            overlay_im = Image.open(TIMEZONE_RESOURCES + overlay).convert('RGBA')
            im.paste(overlay_im, (0, 0), overlay_im)
            im.paste(DOT_IM, (int(x - DOT_IM.size[1]/2), int(y - DOT_IM.size[0]/2)), DOT_IM)
        return gtk.gdk.pixbuf_new_from_data(im.tostring(), gtk.gdk.COLORSPACE_RGB,
                                            False, 8, im.size[0], im.size[1], im.size[0] * 3)
    try:
        hexcolor = '{:02x}{:02x}{:02x}'.format(*CC_IM.getpixel((x, y)))
        print "Color: #%s" % hexcolor,
        overlay = 'timezone_{}.png'.format(TIMEZONE_COLORS[hexcolor])
        print "Image: %s" % overlay
    except (IndexError, KeyError):
        installer.wTree.get_widget("image_timezones").set_from_pixbuf(_get_image(None))
    else:
        installer.wTree.get_widget("image_timezones").set_from_pixbuf(_get_image(overlay))
    installer.setup.timezone = timezone