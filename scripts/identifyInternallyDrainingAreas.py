import arcpy, os, time, sys
sys.path.insert(1, sys.path[0] + '/scripts')
import setupTemp as tmp
import numpy as np
from arcpy import env
arcpy.CheckOutExtension("Spatial")
from arcpy.sa import *
env.overwriteOutput = True

def identifyInternallyDrainingAreas(demFile, optimFillFile, prcpFile, cnFile, watershedFile\
	, nonContributingAreasFile, demFinalFile):

	tempDir = tmp.tempDir
	tempGdb = tmp.tempGdb

	# Intermediate Files
	clipCn = tempGdb + '/clipCn'
	runoffTable = tempDir + '/runoffTable.dbf'
	storageTable = tempDir + '/storageTable.dbf'
	trueSinkTable = tempGdb + '/trueSinkTable'
	nonContribRaw = tempGdb + '/nonContribRaw'
	nonContribFiltered = tempGdb + '/nonContribFiltered'
	nonContribUngrouped = tempGdb + '/nonContribUngrouped'

	env.scratchWorkspace = tempDir
	env.workspace = tempDir
	os.environ['ARCTMPDIR'] = tmp.tempDir
	env.snapRaster = demFile
	env.extent = demFile
	env.cellSize = demFile
	env.mask = demFile

	arcpy.AddMessage("Identifying sinks...")
	fill = Fill(demFile)
	sinkDepth = fill - Raster(demFile)
	A = float(env.cellSize)**2  # area of a gridcell
	storageVolume = sinkDepth * A
	sinkExtent = Con(sinkDepth > 0, 1)
	sinkGroup = RegionGroup(sinkExtent, "EIGHT", '', 'NO_LINK')
	maxDepth = ZonalStatistics(sinkGroup, "Value", sinkDepth, "MAXIMUM", "DATA")
	prcpMeters = Raster(prcpFile) * 0.0000254
	meanPrecip = ZonalStatistics(sinkGroup, "Value", prcpMeters, "MEAN", "DATA")
	sinkLarge = Con(maxDepth > meanPrecip, sinkGroup)
	del sinkDepth, sinkExtent, sinkGroup, maxDepth

	arcpy.AddMessage("Calculating runoff...")
	CN = Raster(cnFile)
	prcpInches = Raster(prcpFile) / 1000.
	S = (1000.0 / CN) - 10.0
	Ia = 0.2 * S
	runoffDepth = (prcpInches - Ia)**2 / (prcpInches - Ia + S)
	runoffVolume = (runoffDepth * 0.0254) * A
	fdr = FlowDirection(optimFillFile)
	runoffAcc = FlowAccumulation(fdr, runoffVolume, 'FLOAT')
	del CN, S, Ia, runoffDepth

	arcpy.AddMessage("Comparing runoff to sink capacity...")
	arcpy.BuildRasterAttributeTable_management(sinkLarge, True)

	ZonalStatisticsAsTable(sinkLarge, "VALUE", runoffAcc, runoffTable, "DATA", "MAXIMUM")
	ZonalStatisticsAsTable(sinkLarge, "VALUE", storageVolume, storageTable, "DATA", "SUM")

	arcpy.JoinField_management(runoffTable, 'VALUE', storageTable, 'VALUE')
	arcpy.TableSelect_analysis(runoffTable, trueSinkTable, '"SUM" > "MAX"')

	trueSinks = []
	rows = arcpy.SearchCursor(trueSinkTable, '', '', 'Value')
	for row in rows:
		trueSinks.append(row.Value)
	del row, rows

	arcpy.AddMessage("Delineating watersheds of 'true' sinks...")
	seeds = arcpy.sa.ExtractByAttributes(sinkLarge, 'VALUE IN ' + str(tuple(trueSinks)))
	nonContributingAreas = Watershed(fdr, seeds)
	del seeds, fdr

	arcpy.AddMessage("Saving output...")
	arcpy.RasterToPolygon_conversion(nonContributingAreas, nonContribRaw, False, 'Value')
	arcpy.MakeFeatureLayer_management(nonContribRaw, 'nonContribRaw_layer')
	arcpy.MakeFeatureLayer_management(watershedFile, 'watershed_layer')
	arcpy.SelectLayerByLocation_management('nonContribRaw_layer', 'WITHIN', 'watershed_layer'\
		, '', 'NEW_SELECTION')
	arcpy.CopyFeatures_management('nonContribRaw_layer', nonContribFiltered)
	arcpy.PolygonToRaster_conversion(nonContribFiltered, 'grid_code'\
		, nonContribUngrouped, 'CELL_CENTER', '', demFile)
	noId = Reclassify(nonContribUngrouped, "Value"\
		, RemapRange([[1,1000000000000000,1]]))

	grouped = RegionGroup(noId, 'EIGHT', '', 'NO_LINK')
	grouped.save(nonContributingAreasFile)

	demFinal = Con(IsNull(nonContributingAreasFile), demFile)
	demFinal.save(demFinalFile)

if __name__ == '__main__':

	# Input files
	demFile = arcpy.GetParameterAsText(0)
	optimFillFile = arcpy.GetParameterAsText(1)
	prcpFile = arcpy.GetParameterAsText(2) # Run the script, preparePrecipData.py
	cnFile = arcpy.GetParameterAsText(3)
	watershedFile = arcpy.GetParameterAsText(4)
	nonContributingAreasFile = arcpy.GetParameterAsText(5)
	demFinalFile = arcpy.GetParameterAsText(6)
	
	identifyInternallyDrainingAreas(demFile, optimFillFile, prcpFile, cnFile, watershedFile\
		, nonContributingAreasFile, demFinalFile)


