"""
Greenscreen photo booth GUI
"""
import time

import wx
from glob import glob
from os import path
import greenscreen
from PIL import Image
import os
from numpy import random
import shutil
import datetime
import subprocess


# GUI layout
nBGSelectorPreviewPanels = 2  # number of 'preview' items in BG selector, each forwards and backwards
BGPreviewScaleFac = 0.2  # scale factor for background preview images
BGImageThumbnailScaleFac = 0.2  # scale factor for background image thumbnails
FGImageThumbnailScaleFac = 0.3  # scale factor for foreground image thumbnails
BGSelectedImageBorderWidth = 4  # border width around the selected background image
nFGSelectorPreviewPanels = 3  # number of 'preview' items in FG selector, each backwards and forwards
nFGTotalPreviewPanels = 2 * nFGSelectorPreviewPanels + 1
iMainFGPanel = 2 * nFGSelectorPreviewPanels + 1
iMidFGPanel = nFGSelectorPreviewPanels
nFGThumbnailCache = 30  # cache size for thumbnail cache
SelectedImageBorderWidth = 6  # border around selected composite image


# file name conventions:
# - P1234567.JPG: input image
# - Background123.JPG background image
# - C1234567___Background123.JPG: compound image to above input and background image


def PILImageToWxBitmap(img):
    image = wx.EmptyImage(img.size[0], img.size[1])
    image.SetData(img.convert("RGB").tostring())
    return wx.BitmapFromImage(image)


class GreenieGUI(wx.Frame):

    def __init__(self,
                 BGImagesDir,
                 CompoundImagesDir,
                 PrintedImagesDir,
                 ReferenceImage,
                 PrinterOptions,
                 GreenScreenTol):

        wx.Frame.__init__(self, None, title="Greenie GUI", pos=(0, 22), size=(1276, 778),
                          style=wx.CAPTION | wx.CLOSE_BOX | wx.CLIP_CHILDREN | wx.SYSTEM_MENU)

        self.BGImagesPath = BGImagesDir
        self.CompoundImagesPath = CompoundImagesDir
        self.PrintedImagesPath = PrintedImagesDir
        self.ReferenceImagePath = ReferenceImage
        self.PrinterOptions = PrinterOptions
        self.GreenScreenTol = GreenScreenTol

        self.Bind(wx.EVT_CLOSE, self.OnClose)

        mainPanel = wx.Panel(self)
        mainBox = wx.BoxSizer(wx.HORIZONTAL)
        mainPanel.SetSizer(mainBox)

        BGSelectorPanel = wx.Panel(mainPanel)
        mainBox.Add(BGSelectorPanel, 1, wx.ALL | wx.EXPAND, border=5)
        BGSelectorBox = wx.BoxSizer(wx.VERTICAL)
        BGSelectorPanel.SetSizer(BGSelectorBox)

        BGSelectorTitleText = wx.StaticText(BGSelectorPanel, -1, "Background selection:")
        BGSelectorTitleText.SetFont(wx.Font(14, wx.SWISS, wx.NORMAL, wx.BOLD))
        BGSelectorTitleText.SetSize(BGSelectorTitleText.GetBestSize())
        BGSelectorBox.Add(BGSelectorTitleText, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        BGSelectorBox.AddStretchSpacer(1)

        BGUpButton = wx.Button(BGSelectorPanel, label="Up")
        BGSelectorBox.Add(BGUpButton, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        BGUpButton.Bind(wx.EVT_BUTTON, lambda evt, idx=nBGSelectorPreviewPanels - 1: self.OnBGImageClick(evt, idx))

        self.BGSelectorImagePanels = []
        for i in range(2 * nBGSelectorPreviewPanels + 1):
            panel = wx.Panel(BGSelectorPanel)
            self.BGSelectorImagePanels.append(panel)
            panel.SetSize((30, 20))
            BGSelectorBox.Add(panel, 0, wx.ALL | wx.EXPAND | wx.SHAPED | wx.ALIGN_CENTER | wx.ALIGN_CENTER_VERTICAL, 5)
            panel.Bind(wx.EVT_LEFT_DOWN, lambda evt, idx=i: self.OnBGImageClick(evt, idx))
            if i == nBGSelectorPreviewPanels:
                panel.BackgroundColour = ((255, 100, 0))
            panel.Bind(wx.EVT_PAINT, lambda evt, idx=i: self.OnBGPanelPaint(evt, idx))
            panel.Bind(wx.EVT_ERASE_BACKGROUND, self.OnBGPanelEraseBackground)

        BGDownButton = wx.Button(BGSelectorPanel, label="Down")
        BGSelectorBox.Add(BGDownButton, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        BGDownButton.Bind(wx.EVT_BUTTON, lambda evt, idx=nBGSelectorPreviewPanels + 1: self.OnBGImageClick(evt, idx))

        BGSelectorBox.AddStretchSpacer(1)

        BGSelectButton = wx.Button(BGSelectorPanel, label="Change background for selected photo")
        BGSelectButton.Bind(wx.EVT_BUTTON, self.DoBGSelection)
        BGSelectButton.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL, 0, ""))
        BGSelectorBox.Add(BGSelectButton, 0, wx.ALL | wx.ALIGN_CENTER, 5)

        mainBox.Add(wx.StaticLine(mainPanel, style=wx.LI_VERTICAL), 0, flag=wx.EXPAND | wx.ALL, border=5)

        PhotoControlSelectorPanel = wx.Panel(mainPanel)
        mainBox.Add(PhotoControlSelectorPanel, 8, wx.ALL | wx.EXPAND, border=5)
        PhotoControlSelectorBox = wx.BoxSizer(wx.VERTICAL)
        PhotoControlSelectorPanel.SetSizer(PhotoControlSelectorBox)

        ImageViewerPanel = wx.Panel(PhotoControlSelectorPanel)
        PhotoControlSelectorBox.Add(ImageViewerPanel, 5, wx.ALL | wx.EXPAND, border=5)
        ImageViewerPanelBox = wx.BoxSizer(wx.VERTICAL)
        ImageViewerPanel.SetSizer(ImageViewerPanelBox)

        ImageViewerPreviewRowPanel = wx.Panel(ImageViewerPanel)
        ImageViewerPreviewRowPanelBox = wx.BoxSizer(wx.HORIZONTAL)
        ImageViewerPreviewRowPanel.SetSizer(ImageViewerPreviewRowPanelBox)
        ImageViewerPreviewRowPanel.SetMinSize((1, 100))

        self.FGSelectorImagePanels = []
        for i in range(nFGTotalPreviewPanels + 1):
            if i < nFGTotalPreviewPanels:
                panel = wx.Panel(ImageViewerPreviewRowPanel)
                panel.SetSize((30, 20))
                ImageViewerPreviewRowPanelBox.Add(
                    panel, 0,
                    wx.ALL | wx.EXPAND | wx.SHAPED | wx.ALIGN_CENTER | wx.ALIGN_CENTER_VERTICAL,
                    5)
            else:  # center panel
                panel = wx.Panel(ImageViewerPanel)
                panel.SetSize((30, 20))
                ImageViewerPanelBox.Add(panel, 0,
                                        wx.ALL | wx.EXPAND | wx.SHAPED | wx.ALIGN_CENTER | wx.ALIGN_CENTER_VERTICAL, 5)
            self.FGSelectorImagePanels.append(panel)
            panel.Bind(wx.EVT_LEFT_DOWN, lambda evt, idx=i: self.OnFGImageClick(evt, idx))
            # panel.BackgroundColour = ( ( 255, 100, 20 * i ) )
            panel.Bind(wx.EVT_PAINT, lambda evt, idx=i: self.OnFGPanelPaint(evt, idx))
            panel.Bind(wx.EVT_ERASE_BACKGROUND, self.OnFGPanelEraseBackground)

        # must be added here instead of above to get correct order
        ImageViewerPanelBox.Add(ImageViewerPreviewRowPanel, 1, wx.ALL | wx.EXPAND, border=5)

        ImageViewerButtonPanel = wx.Panel(PhotoControlSelectorPanel)
        PhotoControlSelectorBox.Add(ImageViewerButtonPanel, 0, wx.ALL | wx.EXPAND, border=5)
        ImageViewerButtonPanelBox = wx.BoxSizer(wx.HORIZONTAL)
        ImageViewerButtonPanel.SetSizer(ImageViewerButtonPanelBox)

        ImageViewerButtonPanelBox.AddStretchSpacer(1)

        ImageFirstButton = wx.Button(ImageViewerButtonPanel, label="First")
        ImageViewerButtonPanelBox.Add(ImageFirstButton, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        ImageFirstButton.Bind(wx.EVT_BUTTON, lambda evt, idx=iMidFGPanel - 1000000: self.OnFGImageClick(evt, idx))

        ImageMinus10Button = wx.Button(ImageViewerButtonPanel, label="-10")
        ImageViewerButtonPanelBox.Add(ImageMinus10Button, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        ImageMinus10Button.Bind(wx.EVT_BUTTON, lambda evt, idx=iMidFGPanel - 10: self.OnFGImageClick(evt, idx))

        ImageViewerButtonPanelBox.AddStretchSpacer(1)

        ImageBackButton = wx.Button(ImageViewerButtonPanel, label="Back")
        ImageViewerButtonPanelBox.Add(ImageBackButton, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        ImageBackButton.Bind(wx.EVT_BUTTON, lambda evt, idx=iMidFGPanel - 1: self.OnFGImageClick(evt, idx))

        ImageForwardButton = wx.Button(ImageViewerButtonPanel, label="Forward")
        ImageViewerButtonPanelBox.Add(ImageForwardButton, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        ImageForwardButton.Bind(wx.EVT_BUTTON, lambda evt, idx=iMidFGPanel + 1: self.OnFGImageClick(evt, idx))

        ImageViewerButtonPanelBox.AddStretchSpacer(1)

        ImagePlus10Button = wx.Button(ImageViewerButtonPanel, label="+10")
        ImageViewerButtonPanelBox.Add(ImagePlus10Button, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        ImagePlus10Button.Bind(wx.EVT_BUTTON, lambda evt, idx=iMidFGPanel + 10: self.OnFGImageClick(evt, idx))

        ImageLastButton = wx.Button(ImageViewerButtonPanel, label="Last")
        ImageViewerButtonPanelBox.Add(ImageLastButton, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        ImageLastButton.Bind(wx.EVT_BUTTON, lambda evt, idx=iMidFGPanel + 1000000: self.OnFGImageClick(evt, idx))

        ImageViewerButtonPanelBox.AddStretchSpacer(3)

        self.ImagePrintButton = wx.Button(ImageViewerButtonPanel, label="Print current photo")
        self.ImagePrintButton.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL, 0, ""))
        ImageViewerButtonPanelBox.Add(self.ImagePrintButton, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        self.ImagePrintButton.Bind(wx.EVT_BUTTON, self.PrintImage)

        ImageViewerButtonPanelBox.AddStretchSpacer(1)

        self.RefreshBGImageList()

        self.CompoundImageList = []
        self.FGImageList = []
        self.selectedFGImageIdx = -1
        self.ShownFGImagePaths = [None] * len(self.FGSelectorImagePanels)
        self.FGImageCache = {}

        self.GreenScreenRefColors = greenscreen.GetRefColor(Image.open(self.ReferenceImagePath))

        mainPanel.Layout()

    def RefreshBGImageList(self):
        # find all BG images
        self.BGImageFiles = glob(path.join(self.BGImagesPath, "*.[jJ][pP][gG]"))
        self.BGImageBitmaps = [None] * len(self.BGSelectorImagePanels)
        self.selectedBGImageIdx = min(nBGSelectorPreviewPanels, len(self.BGImageFiles) - 1)

        # store re-sized versions of all BG images
        self.PreviewBGImags = []
        for imgPath in self.BGImageFiles:
            bmp = wx.Bitmap(imgPath)
            image = wx.ImageFromBitmap(bmp).Scale(bmp.Size[0] * BGImageThumbnailScaleFac,
                                                  bmp.Size[1] * BGImageThumbnailScaleFac, wx.IMAGE_QUALITY_HIGH)
            self.PreviewBGImags.append(wx.BitmapFromImage(image))
        self.RefreshGUI()

    def AddFGImage(self, FGImagePath):
        # if no compound image does exist yet, create it
        ImageName = path.split(FGImagePath)[1]
        CompoundImagePattern = path.join(self.CompoundImagesPath, "C" + ImageName[1: -4] + "*.[jJ][pP][gG]")
        curCompoundImages = glob(CompoundImagePattern)
        newFile = False
        if len(curCompoundImages) == 0:
            newFile = True
            BGImagePath = self.BGImageFiles[self.selectedBGImageIdx]
            BGImageName = path.split(BGImagePath)[1]
            CompoundImagePath = path.join(self.CompoundImagesPath, "C" + ImageName[1: -4] + "___" + BGImageName[:])
        else:
            CompoundImagePath = curCompoundImages[0]
        self.CompoundImageList.append(CompoundImagePath)
        self.FGImageList.append(FGImagePath)
        self.selectedFGImageIdx = len(self.CompoundImageList) - 1
        if newFile:
            self.MakeCompoundImage()

    def MakeCompoundImage(self):
        BGImagePath = self.BGImageFiles[self.selectedBGImageIdx]
        BGImageName = path.split(BGImagePath)[1]
        bgImage = Image.open(BGImagePath)
        FGImagePath = self.FGImageList[self.selectedFGImageIdx]
        FGImageName = path.split(FGImagePath)[1]
        fgImage = Image.open(FGImagePath)
        CompoundImagePath = path.join(self.CompoundImagesPath, "C" + FGImageName[1: -4] + "___" + BGImageName[:])

        # delete any compound images already present for that FG image
        compoundImage = greenscreen.Overlay(fgImage, bgImage, self.GreenScreenRefColors, tolA=self.GreenScreenTol[0],
                                            tolB=self.GreenScreenTol[1])
        CompoundImagePattern = path.join(self.CompoundImagesPath, "C" + FGImageName[1: -4] + "___*.[jJ][pP][gG]")
        for f in glob(CompoundImagePattern):
            os.remove(f)
        compoundImage.save(CompoundImagePath)
        self.CompoundImageList[self.selectedFGImageIdx] = CompoundImagePath

    def OnBGImageClick(self, event, panelIdx):
        self.selectedBGImageIdx += panelIdx - nBGSelectorPreviewPanels
        self.selectedBGImageIdx = max(0, min(len(self.BGImageFiles) - 1, self.selectedBGImageIdx))
        # refresh all panels
        for panel in self.BGSelectorImagePanels:
            panel.Refresh()

    def DoBGSelection(self, event):
        # create new compound image
        self.MakeCompoundImage()
        self.FGSelectorImagePanels[iMainFGPanel].Refresh()
        self.FGSelectorImagePanels[iMidFGPanel].Refresh()
        pass

    def OnFGImageClick(self, event, panelIdx):
        self.selectedFGImageIdx += panelIdx - iMidFGPanel
        self.selectedFGImageIdx = max(0, min(len(self.CompoundImageList) - 1, self.selectedFGImageIdx))
        # refresh all panels
        for panel in self.FGSelectorImagePanels:
            panel.Refresh()
        pass

    def RefreshGUI(self):
        for panel in self.BGSelectorImagePanels:
            panel.Refresh()
        for panel in self.FGSelectorImagePanels:
            panel.Refresh()

    def OnClose(self, event):
        dlg = wx.MessageDialog(self,
                               "Do you really want to close this application?",
                               "Confirm Exit", wx.OK | wx.CANCEL | wx.ICON_QUESTION)
        result = dlg.ShowModal()
        dlg.Destroy()
        if result == wx.ID_OK:
            dlg = wx.MessageDialog(self,
                                   "Do you really think you should close this application?",
                                   "Confirm Exit if you mean it", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
            result = dlg.ShowModal()
            dlg.Destroy()
            if result == wx.ID_YES:
                dlg = wx.MessageDialog(self,
                                       "REALLY close? Don't say I didn't warn you!",
                                       "Confirm Exit, but don't complain later", wx.OK | wx.CANCEL | wx.ICON_QUESTION)
                result = dlg.ShowModal()
                dlg.Destroy()
                if result == wx.ID_OK:
                    self.Destroy()

    def OnBGPanelPaint(self, evt, panelIdx):
        panel = self.BGSelectorImagePanels[panelIdx]
        dc = wx.BufferedPaintDC(panel)
        dc.Clear()
        imgIdx = self.selectedBGImageIdx + panelIdx - nBGSelectorPreviewPanels
        if imgIdx >= 0 and imgIdx < len(self.BGImageFiles):
            self.BGImageBitmaps[panelIdx] = self.PreviewBGImags[imgIdx]
            panelScalFac = (1.0 - BGPreviewScaleFac) ** abs(panelIdx - nBGSelectorPreviewPanels)
            imgSize = [panel.Size[0] * panelScalFac, panel.Size[1] * panelScalFac]
            if panelIdx == nBGSelectorPreviewPanels:
                imgSize[0] -= 2 * BGSelectedImageBorderWidth
                imgSize[1] -= 2 * BGSelectedImageBorderWidth
            image = wx.ImageFromBitmap(self.BGImageBitmaps[panelIdx]).Scale(imgSize[0], imgSize[1])
            dc.DrawBitmap(wx.BitmapFromImage(image), 0.5 * (panel.Size[0] - imgSize[0]),
                          0.5 * (panel.Size[1] - imgSize[1]))
        else:
            self.BGImageBitmaps[panelIdx] = None

    def OnBGPanelEraseBackground(self, event):
        """ Handles the wx.EVT_ERASE_BACKGROUND event for CustomCheckBox. """
        # This is intentionally empty, because we are using the combination
        # of wx.BufferedPaintDC + an empty OnEraseBackground event to
        # reduce flicker
        pass

    def CacheFGImage(self, imgPath):
        """ Add image to cache; make space in cache if necessary"""
        if imgPath in self.FGImageCache.keys():
            # image is already cached
            return
        # make space in cache if necessary
        while len(self.FGImageCache) >= nFGThumbnailCache:
            # try to remove a random element
            iRand = random.randint(0, len(self.FGImageCache))
            # only remove images not currently shown
            imgNameRand = self.FGImageCache.keys()[iRand]
            if not imgNameRand in self.ShownFGImagePaths:
                del self.FGImageCache[imgNameRand]
        # cache the new image
        bmp = wx.Bitmap(imgPath)
        image = wx.ImageFromBitmap(bmp).Scale(bmp.Size[0] * FGImageThumbnailScaleFac,
                                              bmp.Size[1] * FGImageThumbnailScaleFac)
        self.FGImageCache[imgPath] = wx.BitmapFromImage(image)

    def OnFGPanelPaint(self, evt, panelIdx):
        panel = self.FGSelectorImagePanels[panelIdx]
        dc = wx.BufferedPaintDC(panel)
        dc.Clear()
        if panelIdx < nFGTotalPreviewPanels:
            imgIdx = self.selectedFGImageIdx + panelIdx - iMidFGPanel
        else:
            # main panel
            imgIdx = self.selectedFGImageIdx
        if imgIdx >= 0 and imgIdx < len(self.CompoundImageList) and path.exists(self.CompoundImageList[imgIdx]):
            imgPath = self.CompoundImageList[imgIdx]
            FGImageName = self.FGImageList[imgIdx]
            self.CacheFGImage(imgPath)
            self.ShownFGImagePaths[panelIdx] = imgPath
            imgSize = panel.Size
            if panelIdx != iMainFGPanel:
                bmp = self.FGImageCache[imgPath]
            else:
                # always reload full-res version of main image from disk
                bmp = wx.Bitmap(self.CompoundImageList[imgIdx])
            image = wx.ImageFromBitmap(bmp).Scale(imgSize[0], imgSize[1], wx.IMAGE_QUALITY_HIGH)
            dc.DrawBitmap(wx.BitmapFromImage(image), 0.5 * (panel.Size[0] - imgSize[0]),
                          0.5 * (panel.Size[1] - imgSize[1]))
            if panelIdx == iMidFGPanel:
                # draw a border around current image in preview
                dc.SetPen(wx.Pen((0, 255, 50), 2 * SelectedImageBorderWidth))
                dc.DrawLines(((0, 0), (panel.Size[0], 0), (panel.Size[0], panel.Size[1]), (0, panel.Size[1]), (0, 0)))
            dc.SetTextForeground((255, 255, 255))
            dc.SetFont(wx.Font(16, wx.SWISS, wx.NORMAL, wx.BOLD))
            dc.DrawText(str(imgIdx + 1), 4, 4)
            dc.SetTextForeground((0, 0, 100))
            dc.DrawText(str(imgIdx + 1), 3, 3)
        else:
            self.ShownFGImagePaths[panelIdx] = None

    def OnFGPanelEraseBackground(self, event):
        """ Handles the wx.EVT_ERASE_BACKGROUND event for CustomCheckBox. """
        # This is intentionally empty, because we are using the combination
        # of wx.BufferedPaintDC + an empty OnEraseBackground event to
        # reduce flicker
        pass

    def PrintImage(self, event):
        """ Copy current compound image to PrintedImages folder, send to printer """
        timeStr = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        compoundImgPath = self.CompoundImageList[self.selectedFGImageIdx]
        destFile = path.join(self.PrintedImagesPath, timeStr + "_" + path.split(compoundImgPath)[1])
        shutil.copy(compoundImgPath, destFile)

        ret = subprocess.call(["lpr"] + self.PrinterOptions + [destFile])
        if ret == 0:
            msg = "Sent photo to printer."
        else:
            msg = "Error printing!"
        dlg = wx.MessageDialog(self, "", msg, wx.OK)
        dlg.ShowModal()
