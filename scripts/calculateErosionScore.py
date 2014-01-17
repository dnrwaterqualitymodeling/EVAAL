import arcpy, os
sys.path.insert(1, sys.path[0] + '/scripts')
import setupTemp as tmp
import numpy as np
from arcpy import env
arcpy.CheckOutExtension("Spatial")
from arcpy.sa import *
env.overwriteOutput = True

def calculateErosionScore(usleFile, spiFile, zonalFile, zonalId, demFile, outErosionScoreFile\
	, outSummaryTable, aggregatePolygons, outAggregatedPolygons):

	tempDir = tmp.tempDir
	tempGdb = tmp.tempGdb
	os.environ['ARCTMPDIR'] = tmp.tempDir

	env.scratchWorkspace = tempDir
	env.workspace = tempDir
	env.snapRaster = demFile
	env.extent = demFile
	env.cellSize = demFile
	env.mask = demFile

	lnUsle = Ln(usleFile)
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
		if aggregatePolygons == 'true':
			shapeName = arcpy.Describe(zonalFile).shapeFieldName
			# need to set extent to zonalFile to ensure that feature count
			# matches the number of row iterations when pulling data for 
			# median calculation
			env.extent = zonalFile
			#####################
			n = int(arcpy.GetCount_management(zonalFile).getOutput(0))
			env.extent = demFile 
			areas = np.empty(n, dtype=float)
			rows = arcpy.SearchCursor(zonalFile)
			for i,row in enumerate(rows):
				areas[i] = row.getValue(shapeName).area
			medArea = np.median(areas)
			arcpy.MakeFeatureLayer_management(zonalFile, 'zonalLayer')
			arcpy.SelectLayerByAttribute_management('zonalLayer', 'CLEAR_SELECTION')
			rows = arcpy.SearchCursor(zonalFile)
			for i,row in enumerate(rows):
				if row.getValue(shapeName).area <= medArea:
					id = row.getValue(zonalId)
					if isinstance(id, unicode):
						id = "'" + id + "'"
					arcpy.SelectLayerByAttribute_management('zonalLayer', 'ADD_TO_SELECTION'\
						, '"' + zonalId + '" = ' + str(id))
			zonalAgg = tempGdb + '/zonal_eliminate'
			arcpy.Eliminate_management('zonalLayer', zonalAgg)
			fieldMappings = arcpy.FieldMappings()
			zoneFldMap = arcpy.FieldMap()
			zoneAggFldMap = arcpy.FieldMap()
			zoneFldMap.addInputField(zonalFile, zonalId)
			zoneAggFldMap.addInputField(zonalAgg, zonalId)
			
			outFld = zoneFldMap.outputField
			outFld.name = 'oldZone'
			zoneFldMap.outputField = outFld
			
			outFld = zoneAggFldMap.outputField
			outFld.name = zonalId
			zoneAggFldMap.outputField = outFld
			
			fieldMappings.addFieldMap(zoneFldMap)
			fieldMappings.addFieldMap(zoneAggFldMap)
			arcpy.SpatialJoin_analysis(zonalFile, zonalAgg, tempGdb + '/zonal_spatialJoin', '', ''\
				, fieldMappings, 'WITHIN')
			arcpy.Dissolve_management(tempGdb + '/zonal_spatialJoin', tempGdb + '/zonal_dissolve'\
				, zonalId)
			arcpy.CopyFeatures_management(tempGdb + '/zonal_dissolve', outAggregatedPolygons)
			zonalFile2 = tempGdb + '/zonal_dissolve'
		else:
			zonalFile2 = zonalFile
		zonal = arcpy.PolygonToRaster_conversion(zonalFile2, zonalId, tempGdb + '/zonalRaster'\
			, 'CELL_CENTER', '', demFile)
		# get field data type
		fields = arcpy.ListFields(tempGdb + '/zonalRaster', zonalId)
		dtype = []
		for field in fields:
			dtype.append(field.type)
		if dtype[0] == 'String':
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
	aggregatePolygons = arcpy.GetParameterAsText(7)
	outAggregatedPolygons = arcpy.GetParameterAsText(8)
	
	calculateErosionScore(usleFile, spiFile, zonalFile, zonalId, demFile, outErosionScoreFile\
		, outSummaryTable, aggregatePolygons, outAggregatedPolygons)
	