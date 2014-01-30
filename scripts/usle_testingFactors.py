import arcpy, math, os, sys
sys.path.insert(1, sys.path[0] + '/scripts')
import setupTemp as tmp
from arcpy import env
arcpy.CheckOutExtension("Spatial")
from arcpy.sa import *
env.overwriteOutput = True
env.rasterStatistics = 'NONE'
env.pyramid = 'NONE'

def usle(demFile, fillFile, erosivityFile, erosivityConstant, kFactorFile, cFactorFile\
	, facThreshold, zonalFile, zonalId, outFile):

	tempDir = tmp.tempDir
	tempGdb = tmp.tempGdb
	os.environ['ARCTMPDIR'] = tmp.tempDir

	env.scratchWorkspace = tempDir
	env.workspace = tempDir
	env.snapRaster = demFile
	env.extent = demFile
	env.mask = demFile
	
	origRes = int(arcpy.GetRasterProperties_management(demFile, 'CELLSIZEX').getOutput(0))
	
	# Temp files
	resampleDemFile = tempGdb +  "/resample"
	resampleFillFile = tempGdb + "/resampleFill"
	lsFile = tempGdb + "/ls"
	
	# Resample the dem to 10-meter resolution (use linear interpolation resample method)
	arcpy.Resample_management(demFile, resampleDemFile, "10", "BILINEAR")
	arcpy.Resample_management(fillFile, resampleFillFile, "10", "BILINEAR")
	env.cellSize = resampleDemFile
	refill = Fill(resampleFillFile)
	
	arcpy.AddMessage("Calcuating LS-factor from grid. This may take awhile...")
	fac = FlowAccumulation(FlowDirection(refill))
	facLand = Plus(Con(fac < facThreshold, fac), 1.0)
	del fac
	Am = facLand * 100
	del facLand
	br = Slope(resampleDemFile, "DEGREE") * (math.pi / 180.0)
	
	a0 = 22.1
	m = 0.6
	n = 1.3
	b0 = 0.09
	LS10 = (m+1)*((Am / a0)**m)*((Sin(br) / b0)**n)
	del a0, m, n, b0
	arcpy.Resample_management(LS10, lsFile, origRes, "BILINEAR")
	del LS10
	
	env.cellSize = demFile
	arcpy.AddMessage("Calculating Soil Loss...")
	if erosivityConstant == '' and erosivityFile == '':
		R = 1
	elif erosivityConstant == '':
		R = Raster(erosivityFile)
	else:
		R = float(erosivityConstant)
	K = Raster(kFactorFile)
	C = Raster(cFactorFile)
	LS = Raster(lsFile)
	
	lsSummaryTable = tempGdb + '/lsSummaryTable'
	kSummaryTable = tempGdb + '/kSummaryTable'
	cSummaryTable = tempGdb + '/cSummaryTable'
	lsSummary = ZonalStatisticsAsTable(zonalFile, zonalId, LS, lsSummaryTable, 'DATA', 'MAXIMUM')
	kSummary = ZonalStatisticsAsTable(zonalFile, zonalId, K, kSummaryTable, 'DATA', 'MEAN')
	cSummary = ZonalStatisticsAsTable(zonalFile, zonalId, C, cSummaryTable, 'DATA', 'MEAN')
	
	ls = arcpy.da.TableToNumPyArray(lsSummaryTable, 'MAX')
	k = arcpy.da.TableToNumPyArray(kSummaryTable, 'MEAN')
	c = arcpy.da.TableToNumPyArray(cSummaryTable, 'MEAN')
	
	E = ls['MAX'] * k['MEAN'] * c['MEAN']
	arcpy.Copy_management(lsSummaryTable, tempGdb + '/meanSoilLoss')
	arcpy.AddField_management(tempGdb + '/meanSoilLoss', 'meanSoilLoss', 'FLOAT')
	
	rows = arcpy.UpdateCursor(tempGdb + '/meanSoilLoss')
	for i,row in enumerate(rows):
		row.meanSoilLoss = float(E[i])
		rows.updateRow(row)
	del row,rows
	# E = R * K * LS * C

	# E.save(outFile)
	# del E, R, K, LS, C 

if __name__ == '__main__':

	#Inputs
	demFile = arcpy.GetParameterAsText(0)
	fillFile = arcpy.GetParameterAsText(1)
	erosivityFile = arcpy.GetParameterAsText(2)
	erosivityConstant = arcpy.GetParameterAsText(3)
	kFactorFile = arcpy.GetParameterAsText(4)
	cFactorFile = arcpy.GetParameterAsText(5)
	facThreshold = int(arcpy.GetParameterAsText(6))
	zonalFile = arcpy.GetParameterAsText(7)
	zonalId = arcpy.GetParameterAsText(8)
	outFile = arcpy.GetParameterAsText(9)
	
	demFile = 'D:/TEMP/pleasant_Valley_soilLossComparison.gdb/demConditioned'
	fillFile = 'D:/TEMP/pleasant_Valley_soilLossComparison.gdb/demOptimFill'
	erosivityFile = ''
	erosivityConstant = ''
	kFactorFile = 'D:/TEMP/pleasant_Valley_soilLossComparison.gdb/kFactor'
	cFactorFile = 'D:/TEMP/pleasant_Valley_soilLossComparison.gdb/c_low'
	facThreshold = 1000	
	zonalFile = 'D:/TEMP/pleasant_Valley_soilLossComparison.gdb/wbiFieldBoundaries'
	zonalId = 'RELATE'
	outFile = 'D:/TEMP/pleasant_Valley_soilLossComparison.gdb/soilLossTableRelate_high'
	
	usle(demFile, fillFile, erosivityFile, erosivityConstant, kFactorFile, cFactorFile\
		, facThreshold, outFile)
