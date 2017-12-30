"""
Configuration and launch of greenie GUI
"""

from glob import glob
import wx
import threading
import gui
import subprocess
import time
from os import path

#
# REQUIRED configuration
#

# list of directories containing foreground photos
photoDirs = ["/Users/someuser/Pictures/Eye-Fi"]

# directory containing background images
BGImagesDir = "/Users/someuser/greenie/backgrounds"

# directory in which to store generated compound images
CompoundImagesDir = "/Users/someuser/greenie/compound"

# directory in which to store a backup of all images that were sent to the printer
PrintedImagesDir = "/Users/someuser/greenie/printed"

# path to reference image, i.e. image of the empty green screen;
# # by default is the latest in folder containing reference images
referenceImage = glob("/Users/someuser/greenie/reference/*.[jJ][pP][gG]")[-1]

# printer name
PrinterName = "EPSON_XP_750_Series"

# printer options;
# here: paper source 3 (tray 2), landscape, fit to page, page size as given
PrinterOptions = ["-o", "EPIJ_FdSo=3", "-o", "landscape", "-o", "fit-to-page", "-o",
                  "PageSize=Custom.100x153mm", "-o", "EPIJ_Qual=46"]

#
# OPTIONAL configuration
#

# tolerance values for foreground masking, see greenscreen.Overlay for details
GreenScreenTol = [30., 40.]

# how often to poll the photoDirs for new photos
directoryPollingInterval = 1.0

#
# end of configuration
#


stopThreadsFlag = False

greenieGUI = None
greenieApp = None


def monitorPhotoDirs(callOnPresent=True):
    """
    Monitor directories for new image files, call targetFunc on each new file path.
    If 'callOnPresent' is True, targetFunc is initially called for all present files.
    """
    previous = []
    for d in photoDirs:
        previous += glob(path.join(d, "*.[jJ][pP][gG]"))
    if callOnPresent:
        for f in previous:
            greenieGUI.AddFGImage(f)
    greenieGUI.RefreshGUI()
    while not stopThreadsFlag:
        time.sleep(directoryPollingInterval)
        current = []
        for d in photoDirs:
            current += glob(path.join(d, "*.[jJ][pP][gG]"))
        added = [f for f in current if f not in previous]
        if len(added) > 0:
            for f in added:
                greenieGUI.AddFGImage(f)
            previous = current
            greenieGUI.RefreshGUI()


if __name__ == '__main__':
    # set default printer
    subprocess.check_call(["lpoptions", "-d", PrinterName])

    # build and start GUI
    greenieApp = wx.App()
    greenieGUI = gui.GreenieGUI(BGImagesDir=BGImagesDir,
                                CompoundImagesDir=CompoundImagesDir,
                                PrintedImagesDir=PrintedImagesDir,
                                ReferenceImage=referenceImage,
                                PrinterOptions=PrinterOptions,
                                GreenScreenTol=GreenScreenTol)

    greenieGUI.Show()

    # start monitoring photo directories
    threadFSMonitor = threading.Thread(target=monitorPhotoDirs, args=(True,))
    threadFSMonitor.start()

    # start GUI main loop
    greenieApp.MainLoop()
    # on return, the app has closed

    stopThreadsFlag = True

    pass
