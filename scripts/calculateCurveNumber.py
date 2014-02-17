import arcpy, os, random, urllib, xml, json, sys, subprocess
sys.path.insert(1, sys.path[0] + '/scripts')
import setupTemp as tmp
import numpy as np
from arcpy import env
arcpy.CheckOutExtension("Spatial")
from arcpy.sa import *
env.overwriteOutput = True
env.pyramid = 'NONE'
env.rasterStatistics = 'NONE'

def queryCurveNumberLookup(lc, hsg, scen, coverTypeLookup, cnLookup):
	cts = np.array(coverTypeLookup[lc][scen])
	if len(cts) == 0:
		return None
	if scen == 'high':
		hydCond = 'Poor'
	else:
		hydCond = 'Good'
	coverBool = np.in1d(cnLookup['COVER_CODE'], cts)
	scenBool = np.in1d(cnLookup['HYDROLOGIC_CONDITION'], [hydCond, ''])
	for ct in cts:
		ctBool = cnLookup['COVER_CODE'] == ct
		boolMat = np.vstack((coverBool,scenBool,ctBool))
		cns = cnLookup[hsg][boolMat.all(axis=0)]
		cns = cns.view('i1').reshape(len(cns),len(hsg))
		acrossHgs = np.mean(cns, axis=1)
		if hydCond == 'Good':
			cn = np.min(acrossHgs)
		else:
			cn = np.max(acrossHgs)
	return cn

def downloadCroplandDataLayer(yrStart, yrEnd, tempDir, watershedCdlPrj, rid):
	##################################################
	years = range(int(yrStart), int(yrEnd) + 1)
	cdlUrl = r'http://nassgeodata.gmu.edu:8080/axis2/services/CDLService/GetCDLFile?'
	arcpy.AddMessage("Projecting Area Of Interest to Cropland Data Layer projection...")
	ext = arcpy.Describe(watershedCdlPrj).extent
	ping = subprocess.call(['ping', '-n', '1', 'nassgeodata.gmu.edu'])
	if ping == 1:
		arcpy.AddError('The CropScape server is down. Please try again later, or download local Cropland Data Layers at http://www.nass.usda.gov/research/Cropland/Release/index.htm')
	cdlTiffs = []
	for year in years:
		year = str(year)
		clipUrl = cdlUrl\
			+ r'year='\
			+ year + r'&'\
			+ r'bbox='\
			+ str(ext.XMin) + '%2C'\
			+ str(ext.YMin) + '%2C'\
			+ str(ext.XMax) + '%2C'\
			+ str(ext.YMax)
		try:
			downloadLocXml = tempDir + '/download_' + year + '_' + rid + '.xml'
			urllib.urlretrieve(clipUrl, downloadLocXml)
			tiffUrl = xml.etree.ElementTree.parse(downloadLocXml).getroot()[0].text
			downloadTiff = tempDir + '/cdl_' + year + '_' + rid + '.tif'
			urllib.urlretrieve(tiffUrl, downloadTiff)
		except:
			arcpy.AddError("The CropScape server failed. Please download the layers to your hard drive at http://www.nass.usda.gov/research/Cropland/Release/index.htm")
		cdlTiffs.append(downloadTiff)
	return cdlTiffs
	
def calculateCurveNumber(downloadBool, yrStart, yrEnd, localCdlList, gSSURGO, watershedFile, \
	demFile, outCnLow, outCnHigh, cnLookupFile, coverTypeLookupFile):

	tempDir = tmp.tempDir
	tempGdb = tmp.tempGdb
	os.environ['ARCTMPDIR'] = tmp.tempDir

	# Intermediate files
	rid = str(random.randint(10000,99999))
	arcpy.AddMessage("Process ID " + rid)
	years = range(int(yrStart), int(yrEnd) + 1)
	watershedCdlPrj = tempGdb + '/watershedCdlPrj_' + rid
	clipSSURGO = tempGdb + '/clipSSURGO_' + rid
	samplePts = tempGdb + '/samplePts_' + rid
	joinSsurgo = tempGdb + '/joinSsurgo_' + rid
	mapunits_prj = tempGdb + '/mapunits_prj_' + rid
	outCnLow1 = tempGdb + '/outCnLow1_' + rid
	outCnHigh1 = tempGdb + '/outCnHigh1_' + rid

	# Read in C-factor crosswalk table and CDL legend file
	cnLookup = np.loadtxt(cnLookupFile \
		, dtype=[('COVER_CODE', 'i1') \
			, ('COVER_TYPE', 'S60') \
			, ('TREATMENT', 'S4') \
			, ('HYDROLOGIC_CONDITION', 'S25') \
			, ('A', 'i1') \
			, ('B', 'i1') \
			, ('C', 'i1') \
			, ('D', 'i1')] \
		, delimiter=',', skiprows=1)
	f = open(coverTypeLookupFile, 'r')
	coverTypeLookup = json.load(f)
	f.close()
	del f
	sr = arcpy.SpatialReference(102039)
	arcpy.Project_management(watershedFile, watershedCdlPrj, sr)
	if downloadBool == 'true':
		arcpy.AddMessage("Downloading Cropland Data Layers...")
		cdlTiffs = downloadCroplandDataLayer(yrStart, yrEnd, tempDir, watershedCdlPrj, rid)
	else:
		localCdlList = localCdlList.split(';')
		cdlTiffs = []
		years = []
		for i,localCdl in enumerate(localCdlList):
			clipCdl = tempDir + '/cdl_' + str(i) + '_' + rid + '.tif'
			arcpy.Clip_management(localCdl, '', clipCdl, watershedCdlPrj)
			cdlTiffs.append(clipCdl)
			years.append(i)
	
	resolutions = []
	for cdlTiff in cdlTiffs:
		res = float(arcpy.GetRasterProperties_management(cdlTiff, 'CELLSIZEX').getOutput(0))
		resolutions.append(res)
	minResCdlTiff = np.array(cdlTiffs)[resolutions == np.min(resolutions)][0]
	arcpy.RasterToPoint_conversion(minResCdlTiff, samplePts)
	
	cdlList = []
	yrCols = []
	for i,year in enumerate(years):
		yrCol = 'lc_' + str(year)
		yrCols.append(yrCol)
		cdlList.append([cdlTiffs[i], yrCol])

	ExtractMultiValuesToPoints(samplePts, cdlList, 'NONE')

	arcpy.AddMessage("Overlaying gSSURGO Hydrologic Soil Group...")
	arcpy.Clip_analysis(gSSURGO + "/MUPOLYGON", watershedFile, clipSSURGO)
	arcpy.Project_management(clipSSURGO, mapunits_prj, demFile\
		, 'NAD_1983_To_HARN_Wisconsin')
	arcpy.JoinField_management(mapunits_prj, "MUKEY", gSSURGO + "/muaggatt" \
		, "MUKEY", "hydgrpdcd")
	arcpy.SpatialJoin_analysis(samplePts, mapunits_prj, joinSsurgo, '' \
		, 'KEEP_COMMON', '', 'INTERSECT')
	
	arcpy.AddMessage("Querying TR-55 based on land cover and hydrologic soil group...")
	arcpy.AddField_management(joinSsurgo, 'cnLow', 'FLOAT')
	arcpy.AddField_management(joinSsurgo, 'cnHigh', 'FLOAT')
	ptCount = int(arcpy.GetCount_management(joinSsurgo).getOutput(0))
	msg = "Generalizing rotation from crop sequence, and applying a C-factor..."
	arcpy.SetProgressor("step", msg, 0, ptCount, 1)
	rows = arcpy.UpdateCursor(joinSsurgo)
	for row in rows:
		if row.hydgrpdcd is None:
			hsg = ['A','B','C','D']
		else:
			hsg = [str(row.hydgrpdcd[0])]
		lcs = []
		for yrCol in yrCols:
			if row.getValue(yrCol) is None:
				lcs.append('0')
			else:
				lcs.append(str(row.getValue(yrCol)))
		cnsHigh = []
		cnsLow = []
		for lc in lcs:	
			for scen, hydCond in zip(['low', 'high'], ['Good', 'Poor']):
				cn = queryCurveNumberLookup(lc, hsg, scen, coverTypeLookup, cnLookup)
				if scen == 'low' and cn is not None:
					cnsLow.append(cn)
				elif scen == 'high' and cn is not None:
					cnsHigh.append(cn)
		if (len(cnsHigh) > 0) and (len(cnsLow) > 0):
			row.cnLow = np.mean(cnsLow)
			row.cnHigh = np.mean(cnsHigh)
		rows.updateRow(row)
		arcpy.SetProgressorPosition()
	arcpy.ResetProgressor()
	del row, rows

	arcpy.AddMessage("Creating output rasters...")
	arcpy.PointToRaster_conversion(joinSsurgo, "cnLow", outCnLow1, 'MOST_FREQUENT', \
		'', minResCdlTiff)
	arcpy.PointToRaster_conversion(joinSsurgo, "cnHigh", outCnHigh1, 'MOST_FREQUENT', \
		'', minResCdlTiff)
		
	env.snapRaster = demFile
	env.cellSize = demFile
	env.mask = demFile
	
	wtm = arcpy.Describe(demFile).spatialReference
	outRes = int(arcpy.GetRasterProperties_management(demFile, 'CELLSIZEX').getOutput(0))		
	arcpy.ProjectRaster_management(outCnLow1, outCnLow, wtm, 'BILINEAR', outRes)
	arcpy.ProjectRaster_management(outCnHigh1, outCnHigh, wtm, 'BILINEAR', outRes)

if __name__ == '__main__':

	# Input files
	downloadBool = arcpy.GetParameterAsText(0)
	yrStart = arcpy.GetParameterAsText(1)
	yrEnd = arcpy.GetParameterAsText(2)
	localCdlList = arcpy.GetParameterAsText(3)
	gSSURGO = arcpy.GetParameterAsText(4)
	watershedFile = arcpy.GetParameterAsText(5)
	demFile = arcpy.GetParameterAsText(6)
	outCnHigh = arcpy.GetParameterAsText(7)
	outCnLow = arcpy.GetParameterAsText(8)
	cnLookupFile = sys.path[0] + '/etc/curveNumberLookup.csv'
	coverTypeLookupFile = sys.path[0] + '/etc/coverTypeLookup.json'
	
	# gSSURGO = 'K:/gSSURGO/soils/Wisconsin/SDM_State_WI.gdb'
	# watershedFile = 'D:/TEMP/huc16Sample.shp'
	# demFile = 'D:/TEMP/c_low_prj.img'
	# yrStart = 2008
	# yrEnd = 2012
	# outCnHigh = 'D:/TEMP/cn_high.img'
	# outCnLow = 'D:/TEMP/cn_low.img'
	# cnLookupFile = 'T:/Projects/Rock_River/Code/lidarTargetingTools/curveNumberLookup.csv'
	# coverTypeLookupFile = 'T:/Projects/Rock_River/Code/lidarTargetingTools/coverTypeLookup.json'

	calculateCurveNumber(downloadBool, yrStart, yrEnd, localCdlList, gSSURGO, watershedFile, \
		demFile, outCnLow, outCnHigh, cnLookupFile, coverTypeLookupFile)