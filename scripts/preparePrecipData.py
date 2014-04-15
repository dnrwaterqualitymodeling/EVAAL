import arcpy, os, urllib, zipfile, time, random, sys
sys.path.insert(1, sys.path[0] + '/scripts')
import setupTemp as tmp
from arcpy import env
arcpy.CheckOutExtension("Spatial")
from arcpy.sa import *
env.overwriteOutput = True
arcpy.env.pyramid = 'NONE'
arcpy.env.rasterStatistics = 'NONE'

def preparePrecipData(frequency, duration, rasterTemplateFile, outPrcp):
	rid = str(random.randint(11111,99999))

	tempDir = tmp.tempDir
	tempGdb = tmp.tempGdb
	os.environ['ARCTMPDIR'] = tmp.tempDir

	# INPUT DATA
	# URL for ascii grid of the 10-year 24-hour rainfall event
	ftpDir = 'ftp://hdsc.nws.noaa.gov/pub/hdsc/data/mw/'
	prcpUrl = ftpDir + 'mw' + frequency + 'yr' + duration + 'ha.zip'
	transformation = 'NAD_1983_To_HARN_Wisconsin'
	downloadsFolder = os.environ['UserProfile'] + '/Downloads'
	# Intermediate data
	prcpFile = tempGdb + '/prcp_' + rid
	prcpPrjFile = tempGdb + '/prcpPrj_' + rid
	prcpAscii = tempDir + '/prcpRaw_' + rid + '.asc'

	# Download Prcp data, read data from archive, save backup
	asciiArchive = downloadsFolder + '/mw' + frequency + 'yr' + duration + 'ha.zip'
	asciiFile = downloadsFolder + '/mw' + frequency + 'yr' + duration + 'ha.asc'
	arcpy.AddMessage("Downloading:")
	arcpy.AddMessage(prcpUrl)
	urllib.urlretrieve(prcpUrl, asciiArchive)
	zf = zipfile.ZipFile(asciiArchive, 'r')
	asciiData = zf.read('mw' + frequency + 'yr' + duration + 'ha.asc')
	zf.close()
	f = open(prcpAscii, 'w')
	f.write(asciiData)
	f.close()
	arcpy.ASCIIToRaster_conversion(prcpAscii, prcpFile, 'INTEGER')
	
	if arcpy.GetInstallInfo()['Version'] == '10.0':
		cs = os.environ['AGSDESKTOPJAVA']\
			+ 'Coordinate Systems/Geographic Coordinate Systems/North America/NAD 1983.prj'
	else:
		cs = arcpy.SpatialReference('NAD 1983')
	arcpy.DefineProjection_management(prcpFile, cs)

	env.snapRaster = rasterTemplateFile
	env.cellSize = rasterTemplateFile
	env.mask = rasterTemplateFile
	env.extent = rasterTemplateFile

	arcpy.ProjectRaster_management(prcpFile, prcpPrjFile, rasterTemplateFile, 'BILINEAR'\
		, rasterTemplateFile, transformation)

	rasterTemplate = Raster(rasterTemplateFile)
	prcp = Raster(prcpPrjFile)
	prcpClip = Con(rasterTemplate, prcp)
	prcpClip.save(outPrcp)

	del rasterTemplate, prcp, prcpClip
	arcpy.Delete_management(prcpFile)
	arcpy.Delete_management(prcpPrjFile)

if __name__ == '__main__':

	###########################
	# User-specific inputs
	###########################
	frequency = arcpy.GetParameterAsText(0)
	duration = arcpy.GetParameterAsText(1)
	rasterTemplateFile = arcpy.GetParameterAsText(2)
	outPrcp = arcpy.GetParameterAsText(3)
	
	preparePrecipData(frequency, duration, rasterTemplateFile, outPrcp)
