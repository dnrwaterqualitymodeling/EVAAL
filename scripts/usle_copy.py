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
	, facThreshold, outFile):

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
	LS10  =  (m+1)*((Am / a0)**m)*((Sin(br) / b0)**n)
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

	E = R * K * LS * C

	E.save(outFile)
	del E, R, K, LS, C 

if __name__ == '__main__':

	#Inputs
	demFile = arcpy.GetParameterAsText(0)
	fillFile = arcpy.GetParameterAsText(1)
	erosivityFile = arcpy.GetParameterAsText(2)
	erosivityConstant = arcpy.GetParameterAsText(3)
	kFactorFile = arcpy.GetParameterAsText(4)
	cFactorFile = arcpy.GetParameterAsText(5)
	facThreshold = int(arcpy.GetParameterAsText(6))
	outFile = arcpy.GetParameterAsText(7)

	usle(demFile, fillFile, erosivityFile, erosivityConstant, kFactorFile, cFactorFile\
		, facThreshold, outFile)
