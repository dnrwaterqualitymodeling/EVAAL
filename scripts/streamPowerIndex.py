import arcpy, math, os
sys.path.insert(1, sys.path[0] + '/scripts')
import setupTemp as tmp
from arcpy import env
arcpy.CheckOutExtension("Spatial")
from arcpy.sa import *
env.overwriteOutput = True

def streamPowerIndex(demFile, fillFile, facThreshold, outFile):
	tempDir = tmp.tempDir
	tempGdb = tmp.tempGdb
	os.environ['ARCTMPDIR'] = tmp.tempDir

	env.scratchWorkspace = tempDir
	env.workspace = tempDir
	env.snapRaster = demFile
	env.extent = demFile
	env.cellSize = demFile
	env.mask = demFile

	G = Slope(demFile, "DEGREE") * (math.pi / 180.0)
	fac = FlowAccumulation(FlowDirection(fillFile))
	facLand = Plus(Con(fac < facThreshold, fac), 1.0)
	CA = facLand * float(env.cellSize)**2

	del fac, facLand
	innerTerm = Con(BooleanAnd(IsNull(CA * Tan(G)),(Raster(demFile) > 0)),1,((CA * Tan(G)) + 1))
		
	spi = Ln(innerTerm)
	spi.save(outFile)

if __name__ == '__main__':

	demFile = arcpy.GetParameterAsText(0)
	fillFile = arcpy.GetParameterAsText(1)
	facThreshold = int(arcpy.GetParameterAsText(2))
	outFile = arcpy.GetParameterAsText(3)
	
	streamPowerIndex(demFile, fillFile, facThreshold, outFile)