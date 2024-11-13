import arcpy
from arcpy import env
from arcpy.sa import *
import os
import subprocess as sp

def demRecondition(demFile, nonContributingAreasFile, grassWaterwaysFile, outFile, ws):
    env.extent = demFile
                                                    
    if grassWaterwaysFile is None or grassWaterwaysFile in ['', '#']:
        demRunoff = Raster(demFile)
    else:
        demRunoff = Con(IsNull(grassWaterwaysFile), demFile)

    arcpy.AddMessage("Converting to ASCII...")
    asciiDem = ws['tempDir'] + "/dem.asc"
    arcpy.RasterToASCII_conversion(demRunoff, asciiDem)

    arcpy.AddMessage("Running optimized fill tool...")
    asciiConditioned = ws['tempDir'] + "/conditioned.asc"
    if os.path.exists(asciiConditioned):
        os.remove(asciiConditioned)
    asciiConditioned = asciiConditioned.replace("/", "\\")
    asciiDem = asciiDem.replace("/", "\\")
    spCall = [ws['optFillExe'], '-z', asciiDem, '-fel', asciiConditioned, '-mode', 'bal', '-step', '0.1']
    p = sp.Popen(spCall, startupinfo=ws['startupinfo'])
    p.wait()

    arcpy.AddMessage("Converting conditioned DEM back to raster...")
    arcpy.ASCIIToRaster_conversion(asciiConditioned, outFile, "FLOAT")
    arcpy.DefineProjection_management(outFile, nonContributingAreasFile)
