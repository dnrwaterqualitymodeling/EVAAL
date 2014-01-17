import arcpy, os, random, sys
sys.path.insert(1, sys.path[0] + '/scripts')
import setupTemp as tmp
from arcpy import env
arcpy.CheckOutExtension("Spatial")
from arcpy.sa import *
env.overwriteOutput = True

import subprocess
from subprocess import Popen
startupinfo = subprocess.STARTUPINFO()
startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

def demConditioning(culverts, watershedFile, lidarRaw, optFillExe, demCondFile, demOptimFillFile):
	if env.cellSize == 'MAXOF':
		cellSize = 3
	else:
		cellSize = env.cellSize

	tempDir = tmp.tempDir
	tempGdb = tmp.tempGdb
	os.environ['ARCTMPDIR'] = tmp.tempDir
	
	rid = str(random.randint(111111, 999999))
	
	# Intermediate Files
	watershedBuffer = tempGdb + '/watershedBuffer_' + rid
	lidarClip = tempGdb + "/lidarClip_" + rid
	lidarResample = tempGdb + "/lidarResample_" + rid
	lidarPt = tempGdb + "/lidarPt_" + rid
	asciiDem = tempDir + "/dem_" + rid + ".asc"
	asciiConditioned = tempDir + "/conditioned_" + rid + ".asc"

	env.scratchWorkspace = tempDir
	env.workspace = tempDir
	os.environ['ARCTMPDIR'] = tmp.tempDir

	lidarCellsize = arcpy.GetRasterProperties_management(lidarRaw, 'CELLSIZEX').getOutput(0)
	arcpy.Buffer_analysis(watershedFile, watershedBuffer, '300 Feet')
	arcpy.AddMessage("Clipping to watershed extent...")
	arcpy.Clip_management(lidarRaw, "", lidarClip, watershedBuffer)
	arcpy.AddMessage("Resampling and projecting to WTM/3m...")
	arcpy.ProjectRaster_management(lidarClip, lidarResample, watershedBuffer, "BILINEAR", cellSize)
	arcpy.AddMessage("Converting DEM to points...")
	arcpy.RasterToPoint_conversion(lidarResample, lidarPt, "VALUE")

	arcpy.AddMessage("Preparing inputs for TopoToRaster...")
	ptElevFC = TopoPointElevation([[lidarPt, 'grid_code']])
	boundaryFC = TopoBoundary([watershedBuffer])
	culvertFC = TopoStream([culverts])
	topoFCs = ([ptElevFC, boundaryFC, culvertFC])
	ext = arcpy.Describe(watershedBuffer).extent

	arcpy.AddMessage("Running TopoToRaster...")
	ttr = TopoToRaster(topoFCs, cellSize, ext, 20, "", "", "ENFORCE", "SPOT", 40, 0.5, 1, 0, 0, 200)
	ttr.save(demCondFile)

	arcpy.AddMessage("Converting to ASCII...")
	arcpy.RasterToASCII_conversion(demCondFile, asciiDem)

	arcpy.AddMessage("Running optimized fill tool...")
	if os.path.exists(asciiConditioned):
		os.remove(asciiConditioned)
	asciiConditioned = asciiConditioned.replace("/", "\\")
	asciiDem = asciiDem.replace("/", "\\")
	spCall = [optFillExe, '-z', asciiDem, '-fel', asciiConditioned, '-mode', 'bal', '-step', '0.1']
	p = Popen(spCall, startupinfo=startupinfo)
	p.wait()

	arcpy.AddMessage("Converting conditioned DEM back to raster...")
	arcpy.ASCIIToRaster_conversion(asciiConditioned, demOptimFillFile, "FLOAT")
	arcpy.DefineProjection_management(demOptimFillFile, watershedFile)

	os.remove(asciiConditioned)
	os.remove(asciiDem)

	for dataset in [lidarClip, lidarResample, lidarPt]:
		arcpy.Delete_management(dataset)

if __name__ == '__main__':

	culverts = arcpy.GetParameterAsText(0)
	watershedFile = arcpy.GetParameterAsText(1)
	lidarRaw = arcpy.GetParameterAsText(2)
	demCondFile = arcpy.GetParameterAsText(3)
	demOptimFillFile = arcpy.GetParameterAsText(4)
	
	optFillExe = sys.path[0] + '/etc/OptimizedPitRemoval.exe'
	
	demConditioning(culverts, watershedFile, lidarRaw, optFillExe, demCondFile, demOptimFillFile)
