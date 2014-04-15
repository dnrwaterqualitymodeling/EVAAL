import arcpy, os
sys.path.insert(1, sys.path[0] + '/scripts')
import setupTemp as tmp
import numpy as np
from arcpy import env
arcpy.CheckOutExtension("Spatial")
from arcpy.sa import *
env.overwriteOutput = True

def calculateErosionScore(usleFile, spiFile, zonalFile, zonalId, demFile, outErosionScoreFile\
	, outSummaryTable):

	tempDir = tmp.tempDir
	tempGdb = tmp.tempGdb
	os.environ['ARCTMPDIR'] = tmp.tempDir

	env.scratchWorkspace = tempDir
	env.workspace = tempDir
	env.snapRaster = demFile
	env.extent = demFile
	env.cellSize = demFile

	zonal = arcpy.PolygonToRaster_conversion(zonalFile, zonalId, tempGdb + '/zonalRaster'\
		, 'CELL_CENTER', '', demFile)
	
	env.mask = tempGdb + '/zonalRaster'
	
	lnUsle = Ln(Raster(usleFile) + 1)
	spi = Raster(spiFile)

	spiMean = float(arcpy.GetRasterProperties_management(spi, "MEAN").getOutput(0))
	spiSd = float(arcpy.GetRasterProperties_management(spi, "STD").getOutput(0))
	usleMean = float(arcpy.GetRasterProperties_management(lnUsle, "MEAN").getOutput(0))
	usleSd = float(arcpy.GetRasterProperties_management(lnUsle, "STD").getOutput(0))

	spiZ = (spi - spiMean) / spiSd
	usleZ = (lnUsle - usleMean) / usleSd
	erosionScore = spiZ + usleZ

	if not outErosionScoreFile in ('', '#'):
		erosionScore.save(outErosionScoreFile)
	if not zonalFile == '':
		# get field data type
		fields = arcpy.ListFields(tempGdb + '/zonalRaster', zonalId)
		if len(fields) != 0:
			erosionScoreByClu = ZonalStatisticsAsTable(tempGdb + '/zonalRaster', zonalId, erosionScore\
				, outSummaryTable, "DATA", "ALL")
		else:
			erosionScoreByClu = ZonalStatisticsAsTable(tempGdb + '/zonalRaster', 'VALUE', erosionScore\
				, outSummaryTable, "DATA", "ALL")

if __name__ == '__main__':
	usleFile = arcpy.GetParameterAsText(0)
	spiFile = arcpy.GetParameterAsText(1)
	zonalFile = arcpy.GetParameterAsText(2)
	zonalId = arcpy.GetParameterAsText(3)
	demFile = arcpy.GetParameterAsText(4)
	outErosionScoreFile = arcpy.GetParameterAsText(5)
	outSummaryTable = arcpy.GetParameterAsText(6)
	
	calculateErosionScore(usleFile, spiFile, zonalFile, zonalId, demFile, outErosionScoreFile\
		, outSummaryTable)