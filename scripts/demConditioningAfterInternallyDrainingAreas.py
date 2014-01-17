import arcpy, os, time, sys
sys.path.insert(1, sys.path[0] + '/scripts')
import setupTemp as tmp
import numpy as np
from arcpy import env
arcpy.CheckOutExtension("Spatial")
from arcpy.sa import *
env.overwriteOutput = True

import subprocess
from subprocess import Popen
startupinfo = subprocess.STARTUPINFO()
startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

def demConditioningAfterInternallyDrainingAreas(demFile, nonContributingAreasFile\
	, grassWaterwaysFile, optFillExe, outFile):

	tempDir = tmp.tempDir
	tempGdb = tmp.tempGdb
	os.environ['ARCTMPDIR'] = tmp.tempDir

	env.workspace = tempDir
	env.scratchWorkspace = tempDir

	if grassWaterwaysFile != '':
		demRunoff = Con(IsNull(grassWaterwaysFile), demFile)
	else:
		demRunoff = Raster(demFile)

	arcpy.AddMessage("Converting to ASCII...")
	asciiDem = tempDir + "/dem.asc"
	arcpy.RasterToASCII_conversion(demRunoff, asciiDem)

	arcpy.AddMessage("Running optimized fill tool...")
	asciiConditioned = tempDir + "/conditioned.asc"
	if os.path.exists(asciiConditioned):
		os.remove(asciiConditioned)
	asciiConditioned = asciiConditioned.replace("/", "\\")
	asciiDem = asciiDem.replace("/", "\\")
	spCall = [optFillExe, '-z', asciiDem, '-fel', asciiConditioned, '-mode', 'bal', '-step', '0.1']
	p = Popen(spCall, startupinfo=startupinfo)
	p.wait()

	arcpy.AddMessage("Converting conditioned DEM back to raster...")
	arcpy.ASCIIToRaster_conversion(asciiConditioned, outFile, "FLOAT")
	arcpy.DefineProjection_management(outFile, nonContributingAreasFile)

if __name__ == '__main__':

	demFile = arcpy.GetParameterAsText(0)
	nonContributingAreasFile = arcpy.GetParameterAsText(1)
	grassWaterwaysFile = arcpy.GetParameterAsText(2)
	outFile = arcpy.GetParameterAsText(3)
	
	optFillExe = sys.path[0] + '/etc/OptimizedPitRemoval.exe'
	
	demConditioningAfterInternallyDrainingAreas(demFile, nonContributingAreasFile\
		, grassWaterwaysFile, optFillExe, outFile)
