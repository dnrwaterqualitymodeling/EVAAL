import arcpy
from arcpy import env
from arcpy.sa import *
import requests
import zipfile

def preparePrecipData(downloadBool, frequency, duration, localCopy, rasterTemplateFile, outPrcp, ws):

    # Intermediate data
    prcpFile = ws['tempGdb'] + '/prcp_' + ws['rid']
    prcpPrjFile = ws['tempGdb'] + '/prcpPrj_' + ws['rid']
    prcpAscii = ws['tempDir'] + '/prcpRaw_' + ws['rid'] + '.asc'

    transformation = 'NAD_1983_To_HARN_Wisconsin'

    if downloadBool == 'true':
        # URL for ascii grid of the 10-year 24-hour rainfall event
        httpsDir = 'https://hdsc.nws.noaa.gov/pub/hdsc/data/mw/'
        prcpUrl = httpsDir + 'mw' + frequency + 'yr' + duration + 'ha.zip'
        asciiArchive = ws['tempDir'] + '/mw' + frequency + 'yr' + duration + 'ha.zip'
        arcpy.AddMessage("Downloading " + prcpUrl + "...")
        r = requests.get(prcpUrl, allow_redirects=True)
        open(asciiArchive, 'wb').write(r.content)
        zf = zipfile.ZipFile(asciiArchive, 'r')
    else:
        zf = zipfile.ZipFile(localCopy, 'r')
    arcpy.AddMessage("Reading ASCII frequency-duration data...")
    asciiData = zf.read(zf.namelist()[0])
    zf.close()
    arcpy.AddMessage("Writing ASCII data to file...")
    f = open(prcpAscii, 'wb')
    f.write(asciiData)
    f.close()
    arcpy.AddMessage("Converting ASCII data to temporary raster...")
    arcpy.ASCIIToRaster_conversion(prcpAscii, prcpFile, 'INTEGER')

    cs = arcpy.SpatialReference('NAD 1983')
    arcpy.DefineProjection_management(prcpFile, cs)

    env.cellSize = arcpy.GetRasterProperties_management(rasterTemplateFile, 'CELLSIZEX').getOutput(0)
    env.mask = rasterTemplateFile
    env.extent = rasterTemplateFile
    arcpy.AddMessage("Clipping to extent...")
    prcpFileClp = prcpFile + '_clipped'
    arcpy.Clip_management(prcpFile, "#", prcpFileClp, rasterTemplateFile, "#", "None")
    clSz = str(arcpy.GetRasterProperties_management(rasterTemplateFile, 'CELLSIZEX').getOutput(0))

    arcpy.AddMessage("Projecting and regridding frequency-duration raster to DEM grid domain...")

    arcpy.ProjectRaster_management(prcpFileClp, prcpPrjFile, rasterTemplateFile, 'BILINEAR'\
        , clSz, transformation)
    arcpy.AddMessage('Finished projecting')
    env.snapRaster = rasterTemplateFile
    rasterTemplate = Raster(rasterTemplateFile)
    prcp = Raster(prcpPrjFile)
    arcpy.AddMessage("Masking frequency-duration raster to watershed area...")
    prcpClip = Con(rasterTemplate, prcp)
    arcpy.AddMessage("Saving output...")
    try:
        prcpClip.save(outPrcp)
    except:
        arcpy.AddMessage("Could not save, try saving your file to a \
            geodatabase(.gdb) or reduce the number of characters.")
        raise Exception("Too many characters in file name")
    del rasterTemplate, prcp, prcpClip
