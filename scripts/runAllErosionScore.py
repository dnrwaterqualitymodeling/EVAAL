from calculateCurveNumber import calculateCurveNumber
from calculateErosionScore import calculateErosionScore
from calculateKFactor import mainProcess as calculateKFactor
from demConditioning import demConditioning
from demConditioningAfterInternallyDrainingAreas import demConditioningAfterInternallyDrainingAreas
from identifyInternallyDrainingAreas import identifyInternallyDrainingAreas
from preparePrecipData import preparePrecipData
from streamPowerIndex import streamPowerIndex
from usle import usle

# 1.)
culverts = arcpy.GetParameterAsText(0)
watershedFile = arcpy.GetParameterAsText(1)
lidarRaw = arcpy.GetParameterAsText(2)
optFillExe = arcpy.GetParameterAsText(3)
demCondFile = arcpy.GetParameterAsText(4)
demOptimFillFile = arcpy.GetParameterAsText(5)
# 2a.)
frequency = arcpy.GetParameterAsText(6)
duration = arcpy.GetParameterAsText(7)
outPrcp = arcpy.GetParameterAsText(8)
# 2b.)
CNchart = arcpy.GetParameterAsText(9)
NLCD_2006 = arcpy.GetParameterAsText(10)
gSSURGO = arcpy.GetParameterAsText(11)
cnNEW = arcpy.GetParameterAsText(12)
# 2c.)
nonContributingAreasFile = arcpy.GetParameterAsText(13)
demFinalFile = arcpy.GetParameterAsText(14)
# 3.)
grassWaterwaysFile = arcpy.GetParameterAsText(15)
demReconditioned = arcpy.GetParameterAsText(16)
# 4.)
facThreshold = int(arcpy.GetParameterAsText(17))
spiFile = arcpy.GetParameterAsText(18)
# 5a.)
kFactAttField = arcpy.GetParameterAsText(19)
kFactorFile = arcpy.GetParameterAsText(20)
# 5b.)
erosivityFile = arcpy.GetParameterAsText(21)
erosivityConstant = arcpy.GetParameterAsText(22)
cFactorFile = arcpy.GetParameterAsText(23)
usleFile = arcpy.GetParameterAsText(24)
# 6.)
zonalFile = arcpy.GetParameterAsText(25)
zonalId = arcpy.GetParameterAsText(26)
outErosionScoreFile = arcpy.GetParameterAsText(27)
outSummaryTable = arcpy.GetParameterAsText(28)
aggregatePolygons = arcpy.GetParameterAsText(29)
outAggregatedPolygons = arcpy.GetParameterAsText(30)

if __name__ == '__main__':
	
	arcpy.AddMessage("1. Condition the LiDAR DEM")
	demConditioning(culverts, watershedFile, lidarRaw, optFillExe, demCondFile, demOptimFillFile)
	
	arcpy.AddMessage("2a. Download Precipitation Data")
	preparePrecipData(frequency, duration, demCondFile, outPrcp)
	
	arcpy.AddMessage("2b. Create Curve Number Raster")
	calculateCurveNumber(CNchart, NLCD_2006, gSSURGO, watershedFile, demCondFile, cnNEW)
	
	arcpy.AddMessage("2c. Identify Internally draining areas")
	identifyInternallyDrainingAreas(demCondFile, demOptimFillFile, outPrcp, cnNEW, watershedFile\
		, nonContributingAreasFile, demFinalFile)
	
	arcpy.AddMessage("3. Recondition DEM for Internally Draining Areas")
	demConditioningAfterInternallyDrainingAreas(demFinalFile, nonContributingAreasFile, grassWaterwaysFile\
		, optFillExe, demReconditioned)
	
	arcpy.AddMessage("4. Calculate Stream Power Index")
	streamPowerIndex(demFile, fillFile, facThreshold, outFile)
	
	arcpy.AddMessage("5a. Rasterize K-factor for USLE")
	calculateKFactor(gssurgoGdb, attField, demFile, outRaster)
	
	arcpy.AddMessage("5b. Calculate Soil Loss Using USLE")
	usle(demFile, fillFile, erosivityFile, erosivityConstant, kFactorFile, cFactorFile, facThreshold\
		, outFile)
	
	arcpy.AddMessage("6. Calculate Erosion Score")
	calculateErosionScore(usleFile, spiFile, zonalFile, zonalId, demFile, outErosionScoreFile\
		, outSummaryTable, aggregatePolygons, outAggregatedPolygons)


