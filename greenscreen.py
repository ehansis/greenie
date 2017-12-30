"""
Green screen image processing
"""

from PIL import Image
import numpy as np


def ImageToYCbCrNumpy(img):
    """
    Conversion RGB -> YCbCR (returned as float32 image!).

    Args:
        img (Image): input RGB image

    Returns:
        np.ndarray: numpy array containing the YCbCr image
    """

    npImg = np.zeros((img.size[1], img.size[0], 3), dtype=np.float32)
    imgNpRGB = np.asarray(img)

    R = imgNpRGB[:, :, 0]
    G = imgNpRGB[:, :, 1]
    B = imgNpRGB[:, :, 2]
    # YCbCr formula from wikipedia
    npImg[:, :, 0] = 0.299 * R + 0.587 * G + 0.114 * B
    npImg[:, :, 1] = 128. - 0.169 * R - 0.331 * G + 0.5 * B
    npImg[:, :, 2] = 128. + 0.5 * R - 0.419 * G - 0.081 * B
    return npImg


def GetRefColor(refImage):
    """
    Get reference color for green screening by simple averaging in RGB and YCbCr

    Args:
        refImage (Image): input RGB image

    Returns:
        (np.ndarray, np.ndarray): two length-3 arrays giving the RFB and YCbCr reference colors
    """
    yRef = ImageToYCbCrNumpy(refImage)
    refColorYCbCr = np.mean(np.mean(yRef, axis=0), axis=0).astype(np.uint8)

    refColorRGB = np.mean(np.mean(np.array(refImage), axis=0), axis=0).astype(np.uint8)

    print "Reference colors: ", str(refColorRGB), str(refColorYCbCr)
    return refColorRGB, refColorYCbCr


def Overlay(fgImage, bgImage, refColors, tolA=30.0, tolB=40.0, filterRadius=1):
    """
    Overlay foreground onto background, after removing green-screen pixels from foreground

    Args:
        fgImage (Image): foreground image
        bgImage (Image): background image, is resized to fgImage if needed
        refColors ((np.ndarray, np.ndarray)): RGB and YCbCr reference colors, from GetRefColor()
        tolA (float): lower bound on linear transition range for masking,
                      pixels with lower CbCr-distance are not removed from the foreground image
        tolB (float): upper bound on linear transition range for masking,
                      pixels with higher CbCr-distance are removed completely from the foreground image

    Returns:
        Image: composited image
    """

    # automatically resize background
    if fgImage.size != bgImage.size:
        bgImage = bgImage.resize(fgImage.size)

    # compute distance in CbCr space
    yFg = ImageToYCbCrNumpy(fgImage)
    colDist = np.sqrt(np.sum((yFg[:, :, 1:] - refColors[1][1:]) ** 2, axis=2))

    # compute mask with linear transition region
    mask = np.zeros(yFg.shape[:2])
    mask[colDist < tolB] = 1.0 - (colDist[colDist < tolB] - tolA) / (tolB - tolA)
    mask[colDist < tolA] = 1.0

    fgNp = np.asarray(fgImage)
    bgNp = np.asarray(bgImage)

    # composite the image
    compNp = ((1.0 - mask[:, :, np.newaxis])
              * np.maximum(fgNp - mask[:, :, np.newaxis] * refColors[0][np.newaxis, np.newaxis, :], 0)
              + mask[:, :, np.newaxis] * bgNp).astype(np.uint8)

    return Image.fromarray(compNp, "RGB")
