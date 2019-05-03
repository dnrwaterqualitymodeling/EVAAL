import arcpy
import os
import random
import sys
import urllib
import ftplib
import zipfile
import datetime
import shutil
import subprocess
import xml
import json
import math
import numpy as np
from subprocess import Popen
from arcpy import env
from arcpy.sa import *
arcpy.CheckOutExtension("Spatial")
env.overwriteOutput = True
arcpy.env.pyramid = 'NONE'
arcpy.env.rasterStatistics = 'NONE'
wd = sys.path[0]
optFillExe = wd + '/etc/OptimizedPitRemoval.exe'
cnLookupFile = wd + '/etc/curveNumberLookup.csv'
legendFile = wd + '/etc/cdlLegend.csv'
cFactorXwalkFile = wd + '/etc/cFactorLookup.csv'
coverTypeLookupFile = wd + '/etc/coverTypeLookup.json'
rotationSymbologyFile = wd + '/etc/rotationSymbology.lyr'

env.scratchWorkspace = wd + '/temp'

tempDir = env.scratchFolder
tempGdb = env.scratchGDB

startupinfo = subprocess.STARTUPINFO()
startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

def checkForSpaces(parameters):
	for p in parameters:
		if p.value:
			if p.direction == 'Input' and p.datatype in ['Feature Layer','Feature Class','Raster Layer','Raster Dataset','Table']:
				# Value of paramater can only be string type. Doesn't work for multivalue
				if not p.multiValue:
					path = arcpy.Describe(p.value).catalogPath
					if ' ' in path:
						p.setErrorMessage("Spaces are not allowed in dataset path.")

def replaceSpacesWithUnderscores(parameters):
	for p in parameters:
		if p.value:
			if p.direction == 'Output' and p.datatype in ['Feature Layer','Feature Class','Raster Layer','Raster Dataset','Table']:
				if ' ' in p.value.value:
					p.value = p.value.value.replace(' ', '_')
					p.setWarningMessage('Spaces in file path were replaced with underscores.')

def checkProjectionsOfInputs(parameters):
	for p in parameters:
		if p.value:
			if p.direction == 'Input' and p.datatype in ['Feature Layer','Feature Class','Raster Layer','Raster Dataset']:
				# Value of paramater can only be string type. Doesn't work for multivalue
				if not p.multiValue:
					cs = arcpy.Describe(p.value).spatialReference.name
					if cs not in ['NAD_1983_HARN_Transverse_Mercator', 'NAD_1983_HARN_Wisconsin_TM']:
						p.setErrorMessage('Dataset must be projected in \
							NAD_1983_HARN_Transverse_Mercator coordinate system.')


def checkDupOutput(parameters):
    output_names = []
    for p in parameters:
        if p.value:
            if p.direction == 'Output':
                output_names.append(p.value.value)
    if len(output_names) != len(set(output_names)):
        p.setErrorMessage('Duplicate output names are not allowed')

def setupTemp(tempDir, tempGdb):
    env.workspace = tempGdb
    env.scratchWorkspace = os.path.dirname(tempDir)
    tempDir = env.scratchFolder
    tempGdb = env.scratchGDB
    arcpy.AddMessage(' ')
    arcpy.AddMessage('#################')
    arcpy.AddMessage('Cleaning scratch space...')
    arcpy.Compact_management(tempGdb)
    tempFiles = arcpy.ListDatasets() + arcpy.ListTables() + arcpy.ListFeatureClasses()
    for tempFile in tempFiles:
        arcpy.AddMessage('Deleting ' + tempFile + '...')
        arcpy.Delete_management(tempFile)
        arcpy.Compact_management(tempGdb)
    os.chdir(tempDir)
    fileList = os.listdir('.')
    for f in fileList:
        if os.path.isdir(f):
            arcpy.AddMessage('Deleting ' + f + '...')
            shutil.rmtree(f)
        else:
            arcpy.AddMessage('Deleting ' + f + '...')
            os.remove(f)
    arcpy.AddMessage('#################')
    arcpy.AddMessage(' ')

def demConditioning(culverts, watershedFile, lidarRaw, optFillExe, demCondFile, demOptimFillFile, \
    tempDir, tempGdb):
    setupTemp(tempDir,tempGdb)

    env.scratchWorkspace = wd + '/temp'
    env.workspace = tempGdb
    os.environ['ARCTMPDIR'] = tempDir

    rid = str(random.randint(111111, 999999))

    # Intermediate Files
    watershedBuffer = tempGdb + '/watershedBuffer_' + rid
    lidarClip = tempGdb + "/lidarClip_" + rid
    culverts_clip = tempGdb + "/culverts_clip" + rid
    asciiDem = tempDir + "/dem_" + rid + ".asc"
    asciiConditioned = tempDir + "/conditioned_" + rid + ".asc"

    env.scratchWorkspace = tempDir
    env.workspace = tempDir

    arcpy.Buffer_analysis(watershedFile, watershedBuffer, '300 Feet')
    arcpy.AddMessage("Clipping to watershed extent...")
    arcpy.Clip_management(lidarRaw, "", lidarClip, watershedBuffer)
    arcpy.AddMessage("Clipping culverts to watershed extent")
    arcpy.Clip_analysis(culverts, watershedBuffer, culverts_clip)
    arcpy.AddMessage("Rasterizing culverts...")
    env.cellSize = arcpy.GetRasterProperties_management(lidarRaw, 'CELLSIZEX').getOutput(0)
    env.snapRaster = lidarClip
    env.extent = lidarClip
    cul_ras = ZonalStatistics(
        culverts_clip,
        arcpy.Describe(culverts).OIDFieldName,
        lidarClip,
        "MINIMUM"
    )
    dem_culv_burn = Con(IsNull(cul_ras), lidarClip, cul_ras)
    del cul_ras
    dem_culv_burn.save(demCondFile)
    del dem_culv_burn

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

    for dataset in [lidarClip, culverts_clip]:
        arcpy.Delete_management(dataset)

def preparePrecipData(downloadBool, frequency, duration, localCopy, rasterTemplateFile, outPrcp, \
    tempDir, tempGdb):
    setupTemp(tempDir,tempGdb)

    env.scratchWorkspace = wd + '/temp'
    env.workspace = tempGdb
    os.environ['ARCTMPDIR'] = tempDir

    rid = str(random.randint(11111,99999))

    # Intermediate data
    prcpFile = tempGdb + '/prcp_' + rid
    prcpPrjFile = tempGdb + '/prcpPrj_' + rid
    prcpAscii = tempDir + '/prcpRaw_' + rid + '.asc'

    transformation = 'NAD_1983_To_HARN_Wisconsin'

    if downloadBool == 'true':
        # URL for ascii grid of the 10-year 24-hour rainfall event
        ftpDir = 'ftp://hdsc.nws.noaa.gov/pub/hdsc/data/mw/'
        prcpUrl = ftpDir + 'mw' + frequency + 'yr' + duration + 'ha.zip'
        try:
            ftp = ftplib.FTP('hdsc.nws.noaa.gov')
        except:
            arcpy.AddMessage('Your machine is not able to establish a connection to the Precipitation \
                Frequency Data Server (PFDS) at NOAA. Either the server is down, or your internet \
                connection is not allowing a direct connection. Please try again later to test if the \
                server is down. Otherwise, try downloading from different internet connection.')
            arcpy.AddMessage('The file you need is:')
            arcpy.AddMessage(precpUrl)
            arcpy.AddError()
        # Download Prcp data, read data from archive, save backup
        asciiArchive = tempDir + '/mw' + frequency + 'yr' + duration + 'ha.zip'
        # asciiFile = tempDir + '/mw' + frequency + 'yr' + duration + 'ha.asc'
        arcpy.AddMessage("Downloading " + prcpUrl + "...")
        urllib.urlretrieve(prcpUrl, asciiArchive)
        zf = zipfile.ZipFile(asciiArchive, 'r')
    else:
        zf = zipfile.ZipFile(localCopy, 'r')
        # asciiFile = tempDir + '/' + zf.namelist()[0].replace('zip', 'asc')
    arcpy.AddMessage("Reading ASCII frequency-duration data...")
    asciiData = zf.read(zf.namelist()[0])
    zf.close()
    arcpy.AddMessage("Writing ASCII data to file...")
    f = open(prcpAscii, 'w')
    f.write(asciiData)
    f.close()
    arcpy.AddMessage("Converting ASCII data to temporary raster...")
	cs = arcpy.SpatialReference('NAD 1983')
    arcpy.ASCIIToRaster_conversion(prcpAscii, prcpFile, 'INTEGER')
    arcpy.DefineProjection_management(prcpFile, cs)
    env.cellSize = arcpy.GetRasterProperties_management(rasterTemplateFile, 'CELLSIZEX').getOutput(0)
    env.outputCoordinateSystem = cs
	env.mask = rasterTemplateFile
    env.extent = rasterTemplateFile
    arcpy.AddMessage("Clipping to extent...")
    prcpFileClp = prcpFile + '_clipped'
    arcpy.Clip_management(prcpFile, "#", prcpFileClp, rasterTemplateFile, "#", "None")
    #added 1045 2014-7-9
    clSz = str(arcpy.GetRasterProperties_management(rasterTemplateFile, 'CELLSIZEX').getOutput(0))

    #at 1045 2014-7-9
    #changed a second 'rasterTemplateFile' to clSz
    #	thinking being that maybe it can't read the cell size from the raster
    arcpy.AddMessage("Projecting and regridding frequency-duration raster to DEM grid domain...")
	
	env.outputCoordinateSystem = rasterTemplateFile
    arcpy.ProjectRaster_management(prcpFileClp, prcpPrjFile, rasterTemplateFile, 'BILINEAR'\
        , clSz, transformation)
    arcpy.AddMessage('Finished projecting')
    env.snapRaster = rasterTemplateFile #no causes it to freeze
    rasterTemplate = Raster(rasterTemplateFile)
    prcp = Raster(prcpPrjFile)
    arcpy.AddMessage("Masking frequency-duration raster to watershed area...")
    prcpClip = Con(rasterTemplate, prcp)
    arcpy.AddMessage("Saving output...")
    try:
        prcpClip.save(outPrcp)
    except:
        arcpy.AddMessage("Could not save, try saving your file to a \
            geodatabase(.gdb) or reduce the number of characters.")
        raise Exception("Too many characters in file name")
    del rasterTemplate, prcp, prcpClip

def queryCurveNumberLookup(lc, hsg, scen, coverTypeLookup, cnLookup):
    cts = np.array(coverTypeLookup[lc][scen])
    hsg = map(str, hsg)
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
    years = range(int(yrStart), int(yrEnd) + 1)
    cdlUrl = r'http://nassgeodata.gmu.edu:8080/axis2/services/CDLService/GetCDLFile?'
    ext = arcpy.Describe(watershedCdlPrj).extent
    ping = subprocess.call(['ping', '-n', '1', 'nassgeodata.gmu.edu'])
    if ping == 1:
        arcpy.AddError('The CropScape server is down. Please try again later, or download local \
            Cropland Data Layers at https://nassgeodata.gmu.edu/CropScape/')
    #unclipped
    cdlTiffs_fl = []
    for year in years:
        year = str(year)
        clipUrl = cdlUrl\
            + r'year='\
            + year + r'&'\
            + r'bbox='\
            + str(ext.XMin) + ','\
            + str(ext.YMin) + ','\
            + str(ext.XMax) + ','\
            + str(ext.YMax)
        try:
            downloadLocXml = tempDir + '/download_' + year + '_' + rid + '.xml'
            urllib.urlretrieve(clipUrl, downloadLocXml)
            tiffUrl = xml.etree.ElementTree.parse(downloadLocXml).getroot()[0].text
            downloadTiff = tempDir + '/cdl_' + year + '_' + rid + '.tif'
            urllib.urlretrieve(tiffUrl, downloadTiff)
        except:
            arcpy.AddError('The CropScape server is down. Please try again later, or download local \
                Cropland Data Layers at https://nassgeodata.gmu.edu/CropScape/')
        cdlTiffs_fl.append(downloadTiff)
        year = str(year)
        clipUrl = cdlUrl\
            + r'year='\
            + year + r'&'\
            + r'bbox='\
            + str(ext.XMin) + ','\
            + str(ext.YMin) + ','\
            + str(ext.XMax) + ','\
            + str(ext.YMax)
        try:
            downloadLocXml = tempDir + '/download_' + year + '_' + rid + '.xml'
            urllib.urlretrieve(clipUrl, downloadLocXml)
            tiffUrl = xml.etree.ElementTree.parse(downloadLocXml).getroot()[0].text
            downloadTiff = tempDir + '/cdl_' + year + '_' + rid + '.tif'
            urllib.urlretrieve(tiffUrl, downloadTiff)
        except:
            arcpy.AddError('The CropScape server is down. Please try again later, or download local \
                Cropland Data Layers at https://nassgeodata.gmu.edu/CropScape/')
        cdlTiffs_fl.append(downloadTiff)
        year = str(year)
        clipUrl = cdlUrl\
            + r'year='\
            + year + r'&'\
            + r'bbox='\
            + str(ext.XMin) + ','\
            + str(ext.YMin) + ','\
            + str(ext.XMax) + ','\
            + str(ext.YMax)
        try:
            downloadLocXml = tempDir + '/download_' + year + '_' + rid + '.xml'
            urllib.urlretrieve(clipUrl, downloadLocXml)
            tiffUrl = xml.etree.ElementTree.parse(downloadLocXml).getroot()[0].text
            downloadTiff = tempDir + '/cdl_' + year + '_' + rid + '.tif'
            urllib.urlretrieve(tiffUrl, downloadTiff)
        except:
            arcpy.AddError('The CropScape server is down. Please try again later, or download local \
                Cropland Data Layers at https://nassgeodata.gmu.edu/CropScape/')
        cdlTiffs_fl.append(downloadTiff)

    # For clipping to watershed extent
    cdlTiffs = []
    for i,fullCdl in enumerate(cdlTiffs_fl):
            clipCdl = tempDir + '/cdl_' + str(i) + '_' + rid + '.tif'
                    #testing the ClippingGeometry option..
            arcpy.Clip_management(fullCdl, '', clipCdl, watershedCdlPrj, '#', 'ClippingGeometry')
            cdlTiffs.append(clipCdl)

    return cdlTiffs

def calculateCurveNumber(downloadBool, yrStart, yrEnd, localCdlList, gSSURGO, watershedFile, \
    demFile, outCnLow, outCnHigh, cnLookupFile, coverTypeLookupFile, tempDir,tempGdb):

    setupTemp(tempDir,tempGdb)

    env.scratchWorkspace = wd + '/temp'
    env.workspace = tempGdb
    os.environ['ARCTMPDIR'] = tempDir

    rid = str(random.randint(10000,99999))

    # Intermediate files
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
    arcpy.AddMessage("Projecting Area Of Interest to Cropland Data Layer projection...")
    sr = arcpy.SpatialReference(102039)
    arcpy.Project_management(watershedFile, watershedCdlPrj, sr, "NAD_1983_To_HARN_Wisconsin")
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
    rows = arcpy.da.UpdateCursor(joinSsurgo, ['hydgrpdcd'] + yrCols + ['cnLow', 'cnHigh'])
    for row in rows:
        if row[0] is None:
            hsg = ['A','B','C','D']
        elif len(row[0]) == 3:
            hsg = [str(row[0][2])]
        else:
            hsg = [str(row[0][0])]
        lcs = []
        for y in range(1,len(yrCols)+1):
            if row[y] is None:
                lcs.append('0')
            else:
                lcs.append(str(row[y]))
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
            row[len(yrCols) + 1] = np.mean(cnsLow)
            row[len(yrCols) + 2] = np.mean(cnsHigh)
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
    env.cellSize = arcpy.GetRasterProperties_management(demFile, 'CELLSIZEX').getOutput(0)
    env.mask = demFile

    wtm = arcpy.Describe(demFile).spatialReference
    outRes = float(arcpy.GetRasterProperties_management(demFile, 'CELLSIZEX').getOutput(0))
    arcpy.ProjectRaster_management(outCnLow1, outCnLow, wtm, 'BILINEAR', outRes)
    arcpy.ProjectRaster_management(outCnHigh1, outCnHigh, wtm, 'BILINEAR', outRes)

def identifyInternallyDrainingAreas(demFile, optimFillFile, prcpFile, cnFile, watershedFile, \
	nonContributingAreasFile, demFinalFile, tempDir, tempGdb):

	rid = str(random.randint(10000,99999))

	setupTemp(tempDir,tempGdb)

	env.scratchWorkspace = wd + '/temp'
	env.workspace = tempGdb
	os.environ['ARCTMPDIR'] = tempDir
	
	# Intermediate Files
	clipCn = tempGdb + '/clipCn_' + rid
	runoffTable = tempDir + '/runoffTable_' + rid + '.dbf'
	storageTable = tempDir + '/storageTable_' + rid + '.dbf'
	trueSinkTable = tempGdb + '/trueSinkTable_' + rid
	nonContribRaw = tempGdb + '/nonContribRaw_' + rid
	nonContribFiltered = tempGdb + '/nonContribFiltered_' + rid
	nonContribUngrouped = tempGdb + '/nonContribUngrouped_' + rid
	inc_runoff = tempGdb + '/inc_runoff_' + rid
	cum_runoff = tempGdb + '/cum_runoff_' + rid
	cum_storage = tempGdb + '/cum_storage_' + rid
	cum_runoff2 = tempGdb + '/cum_runoff2_' + rid
	flow_out = tempGdb + '/flow_out_' + rid
	sinkLarge_file = tempGdb + '/sink_large_' + rid
	seeds = tempGdb + '/seeds_' + rid

	env.scratchWorkspace = tempDir
	env.workspace = tempDir
	os.environ['ARCTMPDIR'] = tempDir
	env.snapRaster = demFile
	env.extent = demFile
	env.cellSize = arcpy.GetRasterProperties_management(demFile, 'CELLSIZEX').getOutput(0)
	env.mask = demFile

	arcpy.AddMessage("Identifying sinks...")
	fill = Fill(demFile)
	sinkDepth = fill - Raster(demFile)
	# area of a gridcell
	A = float(arcpy.GetRasterProperties_management(demFile, 'CELLSIZEX').getOutput(0))**2
	storageVolume = sinkDepth * A
	sinkExtent = Con(sinkDepth > 0, 1)
	sinkGroup = RegionGroup(sinkExtent, "EIGHT", '', 'NO_LINK')
	# to give each non contributing area the MAX depth in the area
	maxDepth = ZonalStatistics(sinkGroup, "Value", sinkDepth, "MAXIMUM", "DATA")
	prcpMeters = Raster(prcpFile) * 0.0000254
	# to assign the mean precip level to each noncontrib area
	meanPrecip = ZonalStatistics(sinkGroup, "Value", prcpMeters, "MEAN", "DATA")
	# only grab those areas where the depth is greater than the precip, thus only the non contributing areas
	sinkLarge = Con(maxDepth > meanPrecip, sinkGroup)
	arcpy.BuildRasterAttributeTable_management(sinkLarge, "Overwrite")
	# arcpy.AddField_management(sinkLarge, "true_sink", "SHORT")
	sinkLarge.save(sinkLarge_file)
	del sinkDepth, sinkExtent, sinkGroup, maxDepth
	
	allnoDat = int(arcpy.GetRasterProperties_management(sinkLarge, 'ALLNODATA').getOutput(0))
	arcpy.AddMessage('All no data returned: ' + str(allnoDat))
	if allnoDat == 1:
		arcpy.AddWarning("No internally draining areas found. Returning null raster and original conditioned DEM.")
		
		# Null raster being saved
		sinkLarge.save(nonContributingAreasFile)
		
		demFinal = arcpy.CopyRaster_management(demFile, demFinalFile)
	else:      
		arcpy.AddMessage("Calculating runoff...")
		CN = Raster(cnFile)
		prcpInches = Raster(prcpFile) / 1000.
		S = (1000.0 / CN) - 10.0
		Ia = 0.2 * S
		runoffDepth = (prcpInches - Ia)**2 / (prcpInches - Ia + S)
		runoffVolume = (runoffDepth * 0.0254) * A
		runoffVolume.save(inc_runoff)
		arcpy.AddMessage("Computing flow direction")
		fdr = FlowDirection(optimFillFile)
		arcpy.AddMessage("Computing runoff accumulation")
		runoffAcc = FlowAccumulation(fdr, runoffVolume, 'FLOAT')
		runoffAcc.save(cum_runoff)
		#### Tristan Nunez fix for sinks in series
		arcpy.AddMessage("Computing storage accumulation")
		storageAcc = FlowAccumulation(fdr, storageVolume, 'FLOAT')
		storageAcc.save(cum_storage)
		arcpy.AddMessage("Runoff minus storage")
		runoffAcc2 = runoffAcc - storageAcc
		runoffAcc2.save(cum_runoff2)
		arcpy.AddMessage("Testing for sink capacity after storm")
		maxFlow = ZonalStatistics(sinkLarge, 'VALUE', runoffAcc, 'MAXIMUM')
		maxFlowInSink = Con(runoffAcc == maxFlow, 1)
		flowOut = Con(maxFlowInSink, runoffAcc2)
		flowOut.save(flow_out)
		arcpy.AddMessage("Identifying true sinks")
		ZonalStatisticsAsTable(sinkLarge, "VALUE", flowOut, runoffTable, "DATA", "MAXIMUM")
		arcpy.TableSelect_analysis(runoffTable, trueSinkTable, '"MAX" < 0')
		####
		del CN, S, Ia, runoffDepth
		
		trueSinkCount = int(arcpy.GetCount_management(trueSinkTable).getOutput(0))
	
		#if trueSinkCount > 0:
		trueSinks = []
		rows = arcpy.da.SearchCursor(trueSinkTable, ['Value'])
		for row in rows:
			trueSinks.append(row[0])
		del row, rows
		trueSinks = np.array(trueSinks)
		
		# ArcGIS set membership reclass functions (Reclassify, InList) are very slow
		# RasterToNumpyArray is used in blocks in an attempt to reduce computation time
		
		blocksize = 512
			
		xrng = range(0, sinkLarge.width, blocksize)
		yrng = range(0, sinkLarge.height, blocksize)
		
		tempfiles = []
		blockno = 0
		arcpy.AddMessage("Blocking sinks grids for numpy set membership")
		arcpy.ClearEnvironment("extent")
		for x in xrng:
			for y in yrng:
				
				# Lower left coordinate of block (in map units)
				mx = sinkLarge.extent.XMin + x * sinkLarge.meanCellWidth
				my = sinkLarge.extent.YMin + y * sinkLarge.meanCellHeight
				# Upper right coordinate of block (in cells)
				lx = min([x + blocksize, sinkLarge.width])
				ly = min([y + blocksize, sinkLarge.height])
				
				blck = arcpy.RasterToNumPyArray(sinkLarge, arcpy.Point(mx, my), lx-x, ly-y)
				true_sink_blck = np.isin(blck, trueSinks).astype(int)
				# Convert data block back to raster
				raster_blck = arcpy.NumPyArrayToRaster(
					true_sink_blck,
					arcpy.Point(mx, my),
					sinkLarge.meanCellWidth,
					sinkLarge.meanCellHeight
				)
				# Save on disk temporarily as 'filename_#.ext'
				# filetemp = ('_%i.' % blockno).join(seeds.rsplit('.',1))
				filetemp = seeds + ('_%i' % blockno)
				raster_blck.save(filetemp)

				# Maintain a list of saved temporary files
				tempfiles.append(filetemp)
				blockno += 1
		
		env.extent = demFile		
		# Mosaic temporary files
		arcpy.AddMessage("Mosaic blocks")
		arcpy.Mosaic_management(';'.join(tempfiles[1:]), tempfiles[0])
		if arcpy.Exists(seeds):
			arcpy.Delete_management(seeds)
		arcpy.Rename_management(tempfiles[0], seeds)

		# Remove temporary files
		for fileitem in tempfiles:
			if arcpy.Exists(fileitem):
				arcpy.Delete_management(fileitem)

		# Release raster objects from memory
		del raster_blck
		
        #   noting that (x, y) is the lower left coordinate (in cells)
		# sink_ext = arcpy.Describe(sinkLarge).extent
		# cellsize = float(arcpy.GetRasterProperties_management(sinkLarge, 'CELLSIZEX').getOutput(0))
		# nrows = int(arcpy.GetRasterProperties_management(sinkLarge, 'ROWCOUNT').getOutput(0))
		# for r in range(1, nrows):
			# ll = arcpy.Point(sink_ext.XMin, sink_ext.YMax - r * cellsize)
			# sinkLargeRow = arcpy.RasterToNumPyArray(sinkLarge, ll, nrows=1)
			# row_bool = np.in1d(sinkLargeRow, np.array(trueSinks))
		
		# arcpy.AddMessage("Flagging true sinks")
		# with arcpy.da.UpdateCursor(sinkLarge, ['VALUE', 'true_sink']) as cursor:
			# for row in cursor:
				# if row[0] in trueSinks:
					# row[1] = 1
				# else:
					# row[1] = 0
				# cursor.updateRow(row)
		# arcpy.AddMessage("Creating watershed seeds")		
		# seeds = InList(sinkLarge, trueSinks)
		
		arcpy.AddMessage("Delineating watersheds of 'true' sinks...")
		seeds2 = Con(seeds == 1, 1)
		nonContributingAreas = Watershed(fdr, seeds2)
		del seeds, seeds2, fdr

		arcpy.AddMessage("Saving output...")
		arcpy.RasterToPolygon_conversion(nonContributingAreas, nonContribRaw, False, 'Value')
		arcpy.MakeFeatureLayer_management(nonContribRaw, 'nonContribRaw_layer')
		arcpy.MakeFeatureLayer_management(watershedFile, 'watershed_layer')
		# To select those nonContributing watersheds that are within the target watershed
		arcpy.SelectLayerByLocation_management('nonContribRaw_layer', 'WITHIN', 'watershed_layer'\
			, '', 'NEW_SELECTION')
		arcpy.CopyFeatures_management('nonContribRaw_layer', nonContribFiltered)
		#Convert only those nonContributing watersheds that are in the target to rasters
		#grid_code for 10.1 and gridcode for 10.2
		if int(arcpy.GetInstallInfo()['Version'].split('.')[1]) > 1:
			colNm = 'gridcode'
		else:
			colNm = 'grid_code'
		cs = arcpy.Describe(demFile).children[0].meanCellHeight
		arcpy.PolygonToRaster_conversion(nonContribFiltered, colNm \
			, nonContribUngrouped, 'CELL_CENTER', '', cs)
		noId = Reclassify(nonContribUngrouped, "Value", RemapRange([[1,1000000000000000,1]]))

		grouped = RegionGroup(noId, 'EIGHT', '', 'NO_LINK')
		grouped.save(nonContributingAreasFile)

		demFinal = Con(IsNull(nonContributingAreasFile), demFile)
		demFinal.save(demFinalFile)

def demConditioningAfterInternallyDrainingAreas(demFile, nonContributingAreasFile, \
    grassWaterwaysFile, optFillExe, outFile, tempDir, tempGdb):

    setupTemp(tempDir,tempGdb)

    env.scratchWorkspace = wd + '/temp'
    env.workspace = tempGdb
    os.environ['ARCTMPDIR'] = tempDir

    env.extent = demFile

    if grassWaterwaysFile is None or grassWaterwaysFile in ['', '#']:
        demRunoff = Raster(demFile)
    else:
        demRunoff = Con(IsNull(grassWaterwaysFile), demFile)

    arcpy.AddMessage("Converting to ASCII...")
    asciiDem = tempDir + "/dem.asc"
    arcpy.RasterToASCII_conversion(demRunoff, asciiDem)

    arcpy.AddMessage("Running optimized fill tool...")
    asciiConditioned = tempDir + "/conditioned.asc"
    if os.path.exists(asciiConditioned):
        os.remove(asciiConditioned)
    asciiConditioned = asciiConditioned.replace("/", "\\")
    asciiDem = asciiDem.replace("/", "\\")
    spCall = [optFillExe, '-z', asciiDem, '-fel', asciiConditioned, '-mode', 'bal', '-step', '0.1']
    p = Popen(spCall, startupinfo=startupinfo)
    p.wait()

    arcpy.AddMessage("Converting conditioned DEM back to raster...")
    arcpy.ASCIIToRaster_conversion(asciiConditioned, outFile, "FLOAT")
    arcpy.DefineProjection_management(outFile, nonContributingAreasFile)

def streamPowerIndex(demFile, fillFile, facThreshold, outFile, tempDir, tempGdb):

    setupTemp(tempDir,tempGdb)

    env.scratchWorkspace = wd + '/temp'
    env.workspace = tempGdb
    os.environ['ARCTMPDIR'] = tempDir


    env.snapRaster = demFile
    env.extent = demFile
    env.cellSize = arcpy.GetRasterProperties_management(demFile, 'CELLSIZEX').getOutput(0)
    env.mask = demFile

    arcpy.AddMessage('Calculating slope...')
    G = Slope(demFile, "DEGREE") * (math.pi / 180.0)
    arcpy.AddMessage('Calculating flow accumulation...')
    fac = FlowAccumulation(FlowDirection(fillFile))
    arcpy.AddMessage('Removing flow accumulation pixels above threshold...')
    facLand = Plus(Con(fac < facThreshold, fac), 1.0)
    arcpy.AddMessage('Converting flow accumulation to contributing area...')
    CA = facLand * float(env.cellSize)**2

    del fac, facLand
    arcpy.AddMessage('Calculating stream power index...')
    innerTerm = Con(BooleanAnd(IsNull(CA * Tan(G)),(Raster(demFile) > 0)),1,((CA * Tan(G)) + 1))

    spi = Ln(innerTerm)
    spi.save(outFile)

def aggregateByElement(tableName, attField, elemField, wtField, stat):
    nRows = int(arcpy.GetCount_management(tableName).getOutput(0))
    elem = np.empty(nRows, dtype='S15')
    att = np.empty(nRows, dtype=np.float)
    wt = np.empty(nRows, dtype=np.float)
    rows = arcpy.da.SearchCursor(tableName, [elemField,attField,wtField])
    for i,row in enumerate(rows):
        elem[i] = row[0]
        att[i] = row[1]
        wt[i] = row[2]
    del i, row, rows
    # Delete rows with nan values or weights equal to zero
    if stat == 'wa':
        inds = np.invert((np.isnan(att) + np.isnan(wt) + (wt == 0)) > 0)
    elif stat == 'top':
        inds = np.invert((np.isnan(att) + np.isnan(wt) + (wt > 0)) > 0)
    elem = elem[inds]
    att = att[inds]
    wt = wt[inds]
    attAve = np.zeros([len(np.unique(elem)),2], dtype=np.float)
    for i,m in enumerate(np.unique(elem)):
        ind = np.where(elem == m)
        if stat == 'wa':
            attAve[i,0:2] = np.array(np.average(att[ind], weights=wt[ind], returned=True))
        elif stat == 'top':
            attAve[i,0:2] = np.array(np.average(att[ind], returned=True))
    del i,m
    attAve = attAve[np.where(attAve[:,1] > 0)]
    elem = np.array(np.unique(elem)[np.where(attAve[:,1] > 0)])
    return {'element' : elem, 'attAve' : attAve}

def makeTableFromAggregatedData(dataDict, tableFile):
    if arcpy.Exists(tableFile):
        arcpy.Delete_management(tableFile)
    arcpy.CreateTable_management(os.path.dirname(tableFile), os.path.basename(tableFile))
    arcpy.AddField_management(tableFile, 'element', 'TEXT', '', '', 15)
    arcpy.AddField_management(tableFile, 'attAve', 'FLOAT', 5, 3)
    arcpy.AddField_management(tableFile, 'wt_sum', 'FLOAT', 5, 3)
    rows = arcpy.InsertCursor(tableFile)
    for i,m in enumerate(np.unique(dataDict['element'])):
        row = rows.newRow()
        row.element = str(m)
        row.attAve = float(dataDict['attAve'][i,0])
        row.wt_sum = float(dataDict['attAve'][i,1])
        rows.insertRow(row)
    del row, rows

def rasterizeKfactor(gssurgoGdb, attField, demFile, watershedFile, outRaster, tempDir, tempGdb):
    randId = str(random.randint(1e5,1e6))

    setupTemp(tempDir,tempGdb)

    env.scratchWorkspace = wd + '/temp'
    env.workspace = tempGdb
    os.environ['ARCTMPDIR'] = tempDir

    arcpy.AddMessage('Creating gSSURGO table views...')
    compTable = gssurgoGdb + '/component'
    chorizonTable = gssurgoGdb + '/chorizon'
    arcpy.MakeTableView_management(chorizonTable, 'chorizon')
    arcpy.MakeTableView_management(compTable, 'component')

    arcpy.AddMessage("Calculating weighted average across horizons...")
    byHoriz = aggregateByElement('chorizon', attField, 'cokey', 'hzdept_r', 'top')
    attAveByHorizFile = tempGdb + '/attAveByHoriz_' + randId
    arcpy.AddMessage("Writing table for weighted average across horizons...")
    makeTableFromAggregatedData(byHoriz, attAveByHorizFile)
    arcpy.MakeTableView_management(attAveByHorizFile, 'attAveByHoriz')
    arcpy.AddMessage("Joining weighted average across horizons to component table...")
    arcpy.AddJoin_management('component', 'cokey', 'attAveByHoriz', 'element')
    arcpy.AddMessage("Calculating weighted average across components...")
    byComp = aggregateByElement('component', 'attAveByHoriz_' + randId + '.attAve'\
        , 'component.mukey', 'component.comppct_r', 'wa')
    attAveByCompFile = tempGdb + '/attAveByComp_' + randId
    arcpy.AddMessage("Writing table for weighted average across components...")
    makeTableFromAggregatedData(byComp, attAveByCompFile)
    arcpy.AddMessage("Projecting gSSURGO...")
    env.snapRaster = demFile
    env.extent = demFile

    cs = arcpy.Describe(demFile).children[0].meanCellHeight
    env.cellSize = cs
    arcpy.Clip_analysis(gssurgoGdb + '/MUPOLYGON', watershedFile\
        , tempGdb + '/MUPOLYGON_clip_' + randId)
    arcpy.Project_management(tempGdb + '/MUPOLYGON_clip_' + randId\
        , tempGdb + '/MUPOLYGON_prj_' + randId\
        , demFile, 'NAD_1983_To_HARN_Wisconsin')
    arcpy.MakeFeatureLayer_management(tempGdb + '/MUPOLYGON_prj_' + randId, 'mupolygon')
    arcpy.AddJoin_management('mupolygon', 'MUKEY', attAveByCompFile, 'element')
    outField = 'attAveByComp_' + randId + '.attAve'
    arcpy.PolygonToRaster_conversion('mupolygon', outField, outRaster\
        ,'MAXIMUM_COMBINED_AREA', '', cs)

def calculateCFactor(downloadBool, localCdlList, watershedFile, rasterTemplateFile, yrStart, yrEnd,\
    outRotation, outHigh, outLow, legendFile, cFactorXwalkFile, tempDir, tempGdb):

    setupTemp(tempDir,tempGdb)

    env.scratchWorkspace = wd + '/temp'
    env.workspace = tempGdb
    os.environ['ARCTMPDIR'] = tempDir

    rid = str(random.randint(10000,99999))
    watershedCdlPrj = tempGdb + '/watershedCdlPrj_' + rid
    samplePts = tempGdb + '/samplePts_' + rid
    outRotation1 = tempGdb + '/outRotation1_' + rid
    outHigh1 = tempGdb + '/outHigh1_' + rid
    outLow1 = tempGdb + '/outLow1_' + rid
    cdlUrl = r'http://nassgeodata.gmu.edu:8080/axis2/services/CDLService/GetCDLFile?'

    arcpy.AddMessage("Projecting Area Of Interest to Cropland Data Layer projection...")
    sr = arcpy.SpatialReference(102039)
    arcpy.Project_management(watershedFile, watershedCdlPrj, sr)
    if downloadBool == 'true':
        arcpy.AddMessage("Downloading Cropland Data Layers...")
        cdlTiffs = downloadCroplandDataLayer(yrStart, yrEnd, tempDir, watershedCdlPrj, rid)
        years = range(int(yrStart), int(yrEnd) + 1)
    else:
        arcpy.AddMessage("Clipping Cropland Data Layers to watershed extent...")
        localCdlList = localCdlList.split(';')
        cdlTiffs = []
        years = []
        for i,localCdl in enumerate(localCdlList):
            clipCdl = tempDir + '/cdl_' + str(i) + '_' + rid + '.tif'
            arcpy.Clip_management(localCdl, '', clipCdl, watershedCdlPrj, '#', 'ClippingGeometry')
            cdlTiffs.append(clipCdl)
            years.append(i)

    resolutions = []
    for cdlTiff in cdlTiffs:
        res = float(arcpy.GetRasterProperties_management(cdlTiff, 'CELLSIZEX').getOutput(0))
        resolutions.append(res)

    minResCdlTiff = np.array(cdlTiffs)[resolutions == np.min(resolutions)][0]

    arcpy.AddMessage("Converting Cropland Data Layer grid to points. If your watershed is larger than a HUC12, this may take awhile...")
    arcpy.RasterToPoint_conversion(minResCdlTiff, samplePts)

    cdlList = []
    yrCols = []
    for i,year in enumerate(years):
        yrCol = 'lc_' + str(year)
        yrCols.append(yrCol)
        cdlList.append([cdlTiffs[i], yrCol])

    arcpy.AddMessage("Pulling crop sequence from Cropland Data Layers...")
    ExtractMultiValuesToPoints(samplePts, cdlList, 'NONE')

    nonRotCropVals = [0] + range(63,181) + range(182,204)
    corn = np.array([1])
    alfalfa = np.array([28, 36, 37, 58])
    pasture = np.array([62, 181, 176])
    soyAndGrain = np.array([4,5,21,22,23,24,25,27,29,30,39,205])
    potatoes = np.array([43])
    veggies = np.array([12,42,47,49,50,53,206,216])

    # Read in C-factor crosswalk table and CDL legend file
    cFactorXwalk = np.loadtxt(cFactorXwalkFile \
        , dtype=[('LAND_COVER', 'S40'), ('SCENARIO', 'S10'), ('C_FACTOR', 'f4')] \
        , delimiter=',', skiprows=1)

    cdlLegend = np.loadtxt(legendFile \
        , dtype=[('VALUE', 'u1'), ('CLASS_NAME', 'S30')] \
        , delimiter=',', skiprows=1)

    arcpy.AddField_management(samplePts, 'rotation', 'TEXT')
    arcpy.AddField_management(samplePts, 'cFactorLow', 'FLOAT')
    arcpy.AddField_management(samplePts, 'cFactorHigh', 'FLOAT')

    ptCount = int(arcpy.GetCount_management(samplePts).getOutput(0))
    msg = "Generalizing rotation from crop sequence, and applying a C-factor..."
    arcpy.SetProgressor("step", msg, 0, ptCount, 1)
    rows = arcpy.UpdateCursor(samplePts)
    for i,row in enumerate(rows):
        lcs = []
        for yrCol in yrCols:
            if row.getValue(yrCol) is None:
                lcs.append(0)
            else:
                lcs.append(row.getValue(yrCol))
        lcs = np.array(lcs)
        nYr = float(len(lcs))
        # Crop proportions
        pNas = float(len(np.where(lcs == 0)[0])) / nYr
        pCorn = float(len(np.where(np.in1d(lcs,corn))[0])) / nYr
        pAlfalfa = float(len(np.where(np.in1d(lcs,alfalfa))[0])) / nYr
        pPasture = float(len(np.where(np.in1d(lcs,pasture))[0])) / nYr
        pSoyAndGrain = float(len(np.where(np.in1d(lcs,soyAndGrain))[0])) / nYr
        pPotato = float(len(np.where(np.in1d(lcs,potatoes))[0])) / nYr
        pVeggies = float(len(np.where(np.in1d(lcs,veggies))[0])) / nYr

        noDataBool = pNas == 1.
        contCornBool = pCorn >= 3./5 and \
            (pSoyAndGrain + pPotato + pVeggies + pAlfalfa + pPasture) == 0.
        cashGrainBool = (pCorn + pSoyAndGrain) >= 2./5 and \
            (pPotato + pVeggies + pAlfalfa + pPasture) == 0.
        dairyBool1 = pAlfalfa >= 1./5 and \
            (pCorn + pSoyAndGrain) >= 1./5
        dairyPotatoBool = pPotato >= 1./5 and \
            pAlfalfa >= 1./5 and \
            pVeggies == 0.
        potGrnVegBool = (pPotato + pVeggies) >= 1./5
        pastureBool = (pPasture + pAlfalfa) >= 2./5 and \
            (pCorn + pSoyAndGrain + pPotato + pVeggies) == 0.
        dairyBool2 = (pAlfalfa + pPasture) >= 1./5
        if noDataBool:
            rot = "No Data"
            c_high = None
            c_low = None
        elif contCornBool:
            rot = "Continuous Corn"
        elif cashGrainBool:
            rot = "Cash Grain"
        elif dairyBool1:
            rot = "Dairy Rotation"
        elif dairyPotatoBool:
            rot = "Dairy Potato Year"
        elif potGrnVegBool:
            rot = "Potato/Grain/Veggie Rotation"
        elif pastureBool:
            rot = "Pasture/Hay/Grassland"
        elif dairyBool2:
            rot = "Dairy Rotation"
        else:
            rot = "No agriculture"
            c_s = np.empty(len(lcs))
            for j,lc in enumerate(lcs):
                c = np.extract(cFactorXwalk['LAND_COVER'] == str(lc) \
                    , cFactorXwalk['C_FACTOR'])
                if len(c) > 0:
                    c_s[j] = c
                else:
                    c_s[j] = np.nan
            c_ave = np.nansum(c_s) / np.sum(np.isfinite(c_s))
            if np.isnan(c_ave):
                c_high = None
                c_low = None
            else:
                c_high = float(c_ave)
                c_low = float(c_ave)
        if rot != "No agriculture" and rot != "No Data":
            rotBool = cFactorXwalk['LAND_COVER'] == rot
            highBool = np.in1d(cFactorXwalk['SCENARIO'], np.array(['High', '']))
            lowBool = np.in1d(cFactorXwalk['SCENARIO'], np.array(['Low', '']))
            c_high = np.extract(np.logical_and(rotBool, highBool), cFactorXwalk['C_FACTOR'])
            c_low = np.extract(np.logical_and(rotBool, lowBool), cFactorXwalk['C_FACTOR'])
            c_high = float(c_high)
            c_low = float(c_low)
        row.cFactorHigh = c_high
        row.cFactorLow = c_low
        row.rotation = rot
        rows.updateRow(row)
        arcpy.SetProgressorPosition()
    arcpy.ResetProgressor()
    del row, rows

    arcpy.AddMessage("Converting points to raster...")
    arcpy.PointToRaster_conversion(samplePts, "rotation", outRotation1, 'MOST_FREQUENT', \
        '', minResCdlTiff)
    arcpy.PointToRaster_conversion(samplePts, "cFactorHigh", outHigh1, 'MEAN', \
        '', minResCdlTiff)
    arcpy.PointToRaster_conversion(samplePts, "cFactorLow", outLow1, 'MEAN', \
        '', minResCdlTiff)

    wtm = arcpy.Describe(rasterTemplateFile).spatialReference
    outRes = float(arcpy.GetRasterProperties_management(rasterTemplateFile, 'CELLSIZEX').getOutput(0))
    env.mask = rasterTemplateFile
    env.snapRaster = rasterTemplateFile
    env.extent = rasterTemplateFile
    arcpy.ProjectRaster_management(outRotation1, outRotation, wtm, 'NEAREST', outRes)
    arcpy.ProjectRaster_management(outHigh1, outHigh, wtm, 'BILINEAR', outRes)
    arcpy.ProjectRaster_management(outLow1, outLow, wtm, 'BILINEAR', outRes)

def usle(demFile, fillFile, erosivityFile, erosivityConstant, kFactorFile, cFactorFile, \
    facThreshold, outFile, tempDir, tempGdb):

    setupTemp(tempDir,tempGdb)

    env.scratchWorkspace = wd + '/temp'
    os.environ['ARCTMPDIR'] = tempDir

    env.snapRaster = demFile
    env.extent = demFile
    env.mask = demFile

    origRes = float(arcpy.GetRasterProperties_management(demFile, 'CELLSIZEX').getOutput(0))

    # Temp files
    resampleDemFile = tempGdb +  "/resample"
    resampleFillFile = tempGdb + "/resampleFill"
    lsFile = tempGdb + "/ls"

    # Resample the dem to 10-meter resolution (use linear interpolation resample method)
    arcpy.AddMessage("Resampling conditioned DEM...")
    arcpy.Resample_management(demFile, resampleDemFile, "10", "BILINEAR")
    arcpy.AddMessage("Resampling re-conditioned DEM...")
    arcpy.Resample_management(fillFile, resampleFillFile, "10", "BILINEAR")
    env.cellSize = arcpy.GetRasterProperties_management(resampleDemFile, 'CELLSIZEX').getOutput(0)
    arcpy.AddMessage("Re-filling re-conditioned DEM...")
    refill = Fill(resampleFillFile)

    arcpy.AddMessage("Calculating LS-factor from grid. This may take awhile...")
    fac = FlowAccumulation(FlowDirection(refill))
    arcpy.AddMessage('Removing flow accumulation pixels above threshold...')
    facLand = Plus(Con(fac < facThreshold, fac), 1.0)
    del fac
    Am = facLand * 10
    del facLand
    arcpy.AddMessage('Calculating br term of slope/slope-length equation...')
    br = Slope(resampleDemFile, "DEGREE") * (math.pi / 180.0)

    a0 = 22.1
    m = 0.6
    n = 1.3
    b0 = 0.09
    arcpy.AddMessage('Calculating slope/slope-length...')
    LS10 = (m+1)*((Am / a0)**m)*((Sin(br) / b0)**n)
    del a0, m, n, b0
    arcpy.Resample_management(LS10, lsFile, origRes, "BILINEAR")
    del LS10

    env.cellSize = arcpy.GetRasterProperties_management(demFile, 'CELLSIZEX').getOutput(0)
    arcpy.AddMessage("Calculating Soil Loss...")
    if erosivityConstant is None and erosivityFile is None:
        R = 1
    elif erosivityConstant == '':
        R = Raster(erosivityFile)
    else:
        R = float(erosivityConstant)
    K = Raster(kFactorFile)
    C = Raster(cFactorFile)
    LS = Con(BooleanAnd(IsNull(lsFile),(Raster(demFile) > 0)), 0, lsFile)

    E = R * K * LS * C

    E.save(outFile)
    del E, R, K, LS, C

def calculateErosionScore(usleFile, spiFile, zonalFile, zonalId, demFile, outErosionScoreFile, \
    outSummaryTable, tempDir, tempGdb):

    randId = str(random.randint(1e5,1e6))

    setupTemp(tempDir,tempGdb)

    env.scratchWorkspace = wd + '/temp'
    env.workspace = tempGdb
    os.environ['ARCTMPDIR'] = tempDir

    env.snapRaster = demFile
    env.extent = demFile
    env.cellSize = arcpy.GetRasterProperties_management(demFile, 'CELLSIZEX').getOutput(0)

    arcpy.AddMessage("Converting zones to raster...")
    if zonalId is None:
        zonalId = 'OBJECTID'
    if zonalFile is not None:

        zonal = arcpy.PolygonToRaster_conversion(zonalFile, zonalId, tempGdb + '/zonalRaster'\
            , 'CELL_CENTER', '', demFile)

        env.mask = tempGdb + '/zonalRaster'

    arcpy.AddMessage("Calculating summary statistics of soil loss and stream power index...")
    lnUsle = Ln(Raster(usleFile) + 1)
        # x 1 was added by T. Nelson on 2014-08-20
        #	Arc was not able to calculate stats on (line 978)
        #	this '*1' seems to work...for some reason
    spi = Raster(spiFile)*1

    arcpy.CalculateStatistics_management(spi)
    arcpy.CalculateStatistics_management(lnUsle)

    spiMean = float(arcpy.GetRasterProperties_management(spi, "MEAN").getOutput(0))
    spiSd = float(arcpy.GetRasterProperties_management(spi, "STD").getOutput(0))
    usleMean = float(arcpy.GetRasterProperties_management(lnUsle, "MEAN").getOutput(0))
    usleSd = float(arcpy.GetRasterProperties_management(lnUsle, "STD").getOutput(0))

    arcpy.AddMessage("Calculating Z-scores...")
    spiZ = (spi - spiMean) / spiSd
    usleZ = (lnUsle - usleMean) / usleSd
    arcpy.AddMessage("Calculating erosion vulnerability index...")
    erosionScore = spiZ + usleZ

    if outErosionScoreFile is not None:
        erosionScore.save(outErosionScoreFile)
    if zonalFile is not None:
        arcpy.AddMessage("Summarizing erosion vulnerability index within zonal statistics feature class boundaries...")
        fields = arcpy.ListFields(tempGdb + '/zonalRaster')
        if len(fields) == 3:
            erosionScoreByClu = ZonalStatisticsAsTable(tempGdb + '/zonalRaster', 'Value', erosionScore\
                    , outSummaryTable, "DATA", "ALL")
        else:
            erosionScoreByClu = ZonalStatisticsAsTable(tempGdb + '/zonalRaster', zonalId, erosionScore\
                , outSummaryTable, "DATA", "ALL")

class Toolbox(object):
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the
        .pyt file)."""
        self.label = "__EVAAL__"
        self.alias = "evaal"
        # List of tool classes associated with this toolbox
        self.tools = [conditionTheLidarDem,
            downloadPrecipitationData,
            createCurveNumberRaster,
            internallyDrainingAreas,
            demReconditioning,
            calculateStreamPowerIndex,
            rasterizeKfactorForUsle,
            rasterizeCfactorForUsle,
            calculateSoilLossUsingUsle,
            erosionScore]

class conditionTheLidarDem(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "1. Condition the LiDAR DEM"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Culverts",
            name="culverts",
            datatype="Feature Layer",
            parameterType="Required",
            direction="Input")
        param0.filter.list = ["Polyline"]

        param1 = arcpy.Parameter(
            displayName="Watershed area (unbuffered)",
            name="watershed_area",
            datatype="Feature Layer",
            parameterType="Required",
            direction="Input")
        param1.filter.list = ["Polygon"]

        param2 = arcpy.Parameter(
            displayName="Raw LiDAR DEM (vertical units in meters)",
            name="raw_lidar_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param3 = arcpy.Parameter(
            displayName="Output conditioned DEM",
            name="output_conditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        param4 = arcpy.Parameter(
            displayName="Output optimized fill",
            name="output_optimized_fill",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3, param4]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        checkForSpaces(parameters)
        checkProjectionsOfInputs(parameters)
        checkDupOutput(parameters)
        return

    def execute(self, parameters, messages):
        culverts = parameters[0].valueAsText
        watershedFile = parameters[1].valueAsText
        lidarRaw = parameters[2].valueAsText
        demCondFile = parameters[3].valueAsText
        demOptimFillFile = parameters[4].valueAsText

        demConditioning(culverts, watershedFile, lidarRaw, optFillExe, demCondFile, demOptimFillFile, tempDir, tempGdb)

class downloadPrecipitationData(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "2a. Download precipitation data"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
        displayName= "Download frequency-duration data? If yes, define frequency and duration below.",
        name="download_frequency_duration",
        datatype="Boolean",
        parameterType="Required",
        direction="Input")
        param0.value = 1

        param1 = arcpy.Parameter(
            displayName="Frequency (years)",
            name="frequency",
            datatype="String",
            parameterType="Optional",
            direction="Input")
        param1.value = '10'
        param1.filter.type = "ValueList"
        param1.filter.list = [1, 2, 5, 10, 25, 50, 100, 200, 500, 1000]

        param2 = arcpy.Parameter(
            displayName="Duration (hours)",
            name="duration",
            datatype="String",
            parameterType="Optional",
            direction="Input")
        param2.filter.type = "ValueList"
        param2.filter.list = [2, 3, 6, 12, 24]
        param2.value = '24'

        param3 = arcpy.Parameter(
            displayName="Locally stored frequency-duration data (zip file)",
            name="local_frequency_duration",
            datatype="File",
            parameterType="Optional",
            direction="Input")
        param3.filter.list = ["zip"]

        param4 = arcpy.Parameter(
            displayName="Conditioned DEM (for template)",
            name="raster_template",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param5 = arcpy.Parameter(
            displayName="Output precipitation frequency-duration raster",
            name="output_precipitation_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3, param4, param5]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        if parameters[0].value == 1:
            parameters[1].enabled = 1
            parameters[2].enabled = 1
            parameters[3].enabled = 0
        else:
            parameters[1].enabled = 0
            parameters[2].enabled = 0
            parameters[3].enabled = 1
        replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        checkForSpaces(parameters)
        checkProjectionsOfInputs(parameters)
        return

    def execute(self, parameters, messages):
        downloadBool = parameters[0].valueAsText
        frequency = parameters[1].valueAsText
        duration = parameters[2].valueAsText
        localCopy = parameters[3].valueAsText
        rasterTemplateFile = parameters[4].valueAsText
        outPrcp = parameters[5].valueAsText

        preparePrecipData(downloadBool, frequency, duration, localCopy, rasterTemplateFile, \
            outPrcp, tempDir, tempGdb)

class createCurveNumberRaster(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "2b. Create curve number raster"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Download Cropland Data Layers? If yes, define years below. If no, define locally stored layers",
            name="download_cropland_data_layers",
            datatype="Boolean",
            parameterType="Required",
            direction="Input")
        param0.value = 1

        param1 = arcpy.Parameter(
            displayName="Start year. Five total years is recommended",
            name="start_year",
            datatype="String",
            parameterType="Optional",
            direction="Input")
        param1.filter.type = "ValueList"
        param1.filter.list = range(2008,datetime.date.today().year - 1)
        param1.value = 2009

        param2 = arcpy.Parameter(
            displayName="End year",
            name="end_year",
            datatype="String",
            parameterType="Optional",
            direction="Input")
        param2.filter.type = "ValueList"
        param2.filter.list = range(2009,datetime.date.today().year)
        param2.value = datetime.date.today().year - 1

        param3 = arcpy.Parameter(
            displayName="Use locally stored Cropland Data Layers?",
            name="use_locally_stored_cropland_data_layers",
            datatype="Raster Layer",
            parameterType="Optional",
            direction="Input",
            multiValue=True)

        param4 = arcpy.Parameter(
            displayName="gSSURGO geodatabase",
            name="gssurgo_geodatabase",
            datatype="Workspace",
            parameterType="Required",
            direction="Input")
        param4.filter.list = ["Local Database"]

        param5 = arcpy.Parameter(
            displayName="Watershed area (buffered)",
            name="watershed_area",
            datatype="Feature Layer",
            parameterType="Required",
            direction="Input")
        param5.filter.list = ["Polygon"]

        param6 = arcpy.Parameter(
            displayName="Conditioned DEM for raster template",
            name="raster_template",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param7 = arcpy.Parameter(
            displayName="Output curve number raster (high estimate)",
            name="output_curve_number_high",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        param8 = arcpy.Parameter(
            displayName="Output curve number raster (low estimate)",
            name="output_curve_number_low",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3, param4, param5, param6, param7, param8]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        if parameters[0].value == 1:
            parameters[1].enabled = 1
            parameters[2].enabled = 1
            parameters[3].enabled = 0
        else:
            parameters[1].enabled = 0
            parameters[2].enabled = 0
            parameters[3].enabled = 1
        replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        checkForSpaces(parameters)
        checkProjectionsOfInputs(parameters)
        checkDupOutput(parameters)
        return

    def execute(self, parameters, messages):
        downloadBool = parameters[0].valueAsText
        yrStart = parameters[1].valueAsText
        yrEnd = parameters[2].valueAsText
        localCdlList = parameters[3].valueAsText
        gSSURGO = parameters[4].valueAsText
        watershedFile = parameters[5].valueAsText
        demFile = parameters[6].valueAsText
        outCnHigh = parameters[7].valueAsText
        outCnLow = parameters[8].valueAsText

        calculateCurveNumber(downloadBool, yrStart, yrEnd, localCdlList, gSSURGO, watershedFile, \
            demFile, outCnLow, outCnHigh, cnLookupFile, coverTypeLookupFile, tempDir, tempGdb)

class internallyDrainingAreas(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "2c. Identify internally draining areas"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Conditioned DEM",
            name="conditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Optimized fill raster",
            name="optimized_fill_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName="Precipitation frequency-duration raster",
            name="precipitation_frequency_duration_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param3 = arcpy.Parameter(
            displayName="Curve number raster",
            name="curve_number_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param4 = arcpy.Parameter(
            displayName="Watershed area (buffered)",
            name="watershed_area",
            datatype="Feature Layer",
            parameterType="Required",
            direction="Input")
        param4.filter.list = ["Polygon"]

        param5 = arcpy.Parameter(
            displayName="Output internally draining areas",
            name="internally_draining_areas",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        param6 = arcpy.Parameter(
            displayName="Output DEM excluding internally draining areas",
            name="dem_excluding_internally_draining_areas",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3, param4, param5, param6]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        checkForSpaces(parameters)
        checkProjectionsOfInputs(parameters)
        checkDupOutput(parameters)
        return

    def execute(self, parameters, messages):
        # Input files
        demFile = parameters[0].valueAsText
        optimFillFile = parameters[1].valueAsText
        prcpFile = parameters[2].valueAsText
        cnFile = parameters[3].valueAsText
        watershedFile = parameters[4].valueAsText
        nonContributingAreasFile = parameters[5].valueAsText
        demFinalFile = parameters[6].valueAsText

        identifyInternallyDrainingAreas(demFile, optimFillFile, prcpFile, cnFile, watershedFile\
            , nonContributingAreasFile, demFinalFile, tempDir, tempGdb)

class demReconditioning(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "3. Recondition DEM for internally draining areas"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="DEM excluding internally draining areas",
            name="dem_excluding_internally_draining_areas",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Internally draining areas raster",
            name="internally_draining_areas",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName='Best management practice areas (i.e., grass waterways, riparian buffer areas)',
            name="additional_non_contributing_areas",
            datatype="Raster Layer",
            parameterType="Optional",
            direction="Input")

        param3 = arcpy.Parameter(
            displayName="Output Reconditioned DEM excluding internally draining areas",
            name="reconditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        checkForSpaces(parameters)
        checkProjectionsOfInputs(parameters)
        return

    def execute(self, parameters, messages):
        # Input files
        demFile = parameters[0].valueAsText
        nonContributingAreasFile = parameters[1].valueAsText
        grassWaterwaysFile = parameters[2].valueAsText
        outFile = parameters[3].valueAsText

        demConditioningAfterInternallyDrainingAreas(demFile, nonContributingAreasFile\
            , grassWaterwaysFile, optFillExe, outFile, tempDir, tempGdb)

class calculateStreamPowerIndex(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "4. Calculate Stream Power Index"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Conditioned DEM",
            name="conditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Reconditioned DEM excluding non-contributing areas",
            name="reconditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName='Flow accumulation threshold (for a 3-meter resolution grid)',
            name="flow_accumulation_threshold",
            datatype="String",
            parameterType="Required",
            direction="Input")
        param2.value = '50000'

        param3 = arcpy.Parameter(
            displayName="Output stream power index raster",
            name="stream_power_index_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        checkForSpaces(parameters)
        checkProjectionsOfInputs(parameters)
        return

    def execute(self, parameters, messages):
        # Input files
        demFile = parameters[0].valueAsText
        fillFile = parameters[1].valueAsText
        facThreshold = int(parameters[2].valueAsText)
        outFile = parameters[3].valueAsText

        streamPowerIndex(demFile, fillFile, facThreshold, outFile, tempDir, tempGdb)

class rasterizeKfactorForUsle(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "5a. Rasterize K-factor for USLE"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="gSSURGO database",
            name="gssurgo_geodatabase",
            datatype="Workspace",
            parameterType="Required",
            direction="Input")
        param0.filter.list = ["Local Database"]

        param1 = arcpy.Parameter(
            displayName="K-factor field",
            name="k_factor_field",
            datatype="String",
            parameterType="Required",
            direction="Input")
        param1.value = 'kwfact'

        param2 = arcpy.Parameter(
            displayName='Conditioned DEM (raster grid template)',
            name="conditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param3 = arcpy.Parameter(
            displayName="Watershed area (buffered)",
            name="watershed_area",
            datatype="Feature Layer",
            parameterType="Required",
            direction="Input")
        param3.filter.list = ["Polygon"]

        param4 = arcpy.Parameter(
            displayName="Output K-factor raster",
            name="k_factor_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3, param4]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        checkForSpaces(parameters)
        checkProjectionsOfInputs(parameters)
        return

    def execute(self, parameters, messages):
        # Input files
        gssurgoGdb = parameters[0].valueAsText
        attField = parameters[1].valueAsText
        demFile = parameters[2].valueAsText
        watershedFile = parameters[3].valueAsText
        outRaster = parameters[4].valueAsText

        rasterizeKfactor(gssurgoGdb, attField, demFile, watershedFile, outRaster, tempDir, tempGdb)

class rasterizeCfactorForUsle(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "5b. Rasterize C-factor for USLE"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Download Cropland Data Layers? If yes, define years below. If no, define locally stored layers",
            name="download_cropland_data_layers",
            datatype="Boolean",
            parameterType="Required",
            direction="Input")
        param0.value = 1

        param1 = arcpy.Parameter(
            displayName="Start year. Five total years is recommended",
            name="start_year",
            datatype="String",
            parameterType="Optional",
            direction="Input")
        param1.filter.type = "ValueList"
        param1.filter.list = range(2008,datetime.date.today().year - 1)
        param1.value = 2009

        param2 = arcpy.Parameter(
            displayName="End year",
            name="end_year",
            datatype="String",
            parameterType="Optional",
            direction="Input")
        param2.filter.type = "ValueList"
        param2.filter.list = range(2009,datetime.date.today().year)
        param2.value = datetime.date.today().year - 1

        param3 = arcpy.Parameter(
            displayName="Use locally stored Cropland Data Layers?",
            name="use_locally_stored_cropland_data_layers",
            datatype="Raster Layer",
            parameterType="Optional",
            direction="Input",
            multiValue=True)
        param3.enabled = 0

        param4 = arcpy.Parameter(
            displayName="Watershed area (buffered)",
            name="watershed_area",
            datatype="Feature Layer",
            parameterType="Required",
            direction="Input")
        param4.filter.list = ["Polygon"]

        param5 = arcpy.Parameter(
            displayName="Conditioned DEM, for template",
            name="raster_template",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param6 = arcpy.Parameter(
            displayName="Output crop rotation raster",
            name="crop_rotation_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")
        param6.symbology = rotationSymbologyFile

        param7 = arcpy.Parameter(
            displayName="Output C-factor raster (high estimate)",
            name="output_c_factor_high",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        param8 = arcpy.Parameter(
            displayName="Output C-factor raster (low estimate)",
            name="output_c_factor_low",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3, param4, param5, param6, param7, param8]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        if parameters[0].value == 1:
            parameters[1].enabled = 1
            parameters[2].enabled = 1
            parameters[3].enabled = 0
        else:
            parameters[1].enabled = 0
            parameters[2].enabled = 0
            parameters[3].enabled = 1
        replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        checkForSpaces(parameters)
        checkProjectionsOfInputs(parameters)
        checkDupOutput(parameters)
        return

    def execute(self, parameters, messages):
        # Input files
        downloadBool = parameters[0].valueAsText
        yrStart = parameters[1].valueAsText
        yrEnd = parameters[2].valueAsText
        localCdlList = parameters[3].valueAsText
        watershedFile = parameters[4].valueAsText
        rasterTemplateFile = parameters[5].valueAsText
        outRotation = parameters[6].valueAsText
        outHigh = parameters[7].valueAsText
        outLow = parameters[8].valueAsText

        calculateCFactor(downloadBool, localCdlList, watershedFile, rasterTemplateFile, yrStart, \
            yrEnd, outRotation, outHigh, outLow, legendFile, cFactorXwalkFile, tempDir, tempGdb)

class calculateSoilLossUsingUsle(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "5c. Calculate soil loss index using USLE"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Conditioned DEM",
            name="conditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Reconditioned DEM excluding non-contributing areas",
            name="reconditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName="Erosivity raster (SI units)",
            name="erosivity_raster",
            datatype="Raster Layer",
            parameterType="Optional",
            direction="Input")

        param3 = arcpy.Parameter(
            displayName="Erosivity constant",
            name="erosivity_constant",
            datatype="String",
            parameterType="Optional",
            direction="Input")

        param4 = arcpy.Parameter(
            displayName="K-factor raster",
            name="k_factor_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param5 = arcpy.Parameter(
            displayName="C-factor raster",
            name="c_factor_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param6 = arcpy.Parameter(
            displayName="Flow Accumulation threshold (for a 10-meter resolution grid)",
            name="flow_accumulation_threshold",
            datatype="String",
            parameterType="Required",
            direction="Input")
        param6.value = '1000'

        param7 = arcpy.Parameter(
            displayName="Output soil loss raster",
            name="soil_loss_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Output")

        parameters = [param0, param1, param2, param3, param4, param5, param6, param7]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        if parameters[2].value is not None:
            parameters[3].enabled = 0
        elif parameters[3].value is not None:
            parameters[2].enabled = 0
        else:
            parameters[2].enabled = 1
            parameters[3].enabled = 1
        checkForSpaces(parameters)
        checkProjectionsOfInputs(parameters)
        return

    def execute(self, parameters, messages):
        #Inputs
        demFile = parameters[0].valueAsText
        fillFile = parameters[1].valueAsText
        erosivityFile = parameters[2].valueAsText
        erosivityConstant = parameters[3].valueAsText
        kFactorFile = parameters[4].valueAsText
        cFactorFile = parameters[5].valueAsText
        facThreshold = int(parameters[6].valueAsText)
        outFile = parameters[7].valueAsText

        usle(demFile, fillFile, erosivityFile, erosivityConstant, kFactorFile, cFactorFile\
            , facThreshold, outFile, tempDir, tempGdb)

class erosionScore(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "6. Calculate erosion vulnerability index"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        param0 = arcpy.Parameter(
            displayName="Soil loss raster",
            name="soil_loss_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param1 = arcpy.Parameter(
            displayName="Stream power index raster",
            name="stream_power_index_raster",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param2 = arcpy.Parameter(
            displayName="Zonal statistic boundary feature class",
            name="zonal_boundary",
            datatype="Feature Layer",
            parameterType="Optional",
            direction="Input")
        param2.filter.list = ["Polygon"]

        param3 = arcpy.Parameter(
            displayName="Zonal statistic field",
            name="zonal_statistic_field",
            datatype="Field",
            parameterType="Optional",
            direction="Input")
        param3.parameterDependencies = [param2.name]

        param4 = arcpy.Parameter(
            displayName="Conditioned DEM (for raster template)",
            name="conditioned_dem",
            datatype="Raster Layer",
            parameterType="Required",
            direction="Input")

        param5 = arcpy.Parameter(
            displayName="Output erosion vulnerability index raster",
            name="erosion_score_raster",
            datatype="Raster Layer",
            parameterType="Optional",
            direction="Output")

        param6 = arcpy.Parameter(
            displayName="Output summary table",
            name="output_summary_table",
            datatype="Table",
            parameterType="Optional",
            direction="Output")

        parameters = [param0, param1, param2, param3, param4, param5, param6]
        return parameters

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        if parameters[2].value is not None:
            parameters[3].enabled = 1
            parameters[3].parameterType = "Required"
            parameters[6].enabled = 1
            parameters[6].parameterType = "Required"
        else:
            parameters[3].enabled = 0
            parameters[3].parameterType = "Optional"
            parameters[6].enabled = 0
            parameters[6].parameterType = "Optional"
        replaceSpacesWithUnderscores(parameters)
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        checkForSpaces(parameters)
        checkProjectionsOfInputs(parameters)
        checkDupOutput(parameters)
        return

    def execute(self, parameters, messages):
        #Inputs
        usleFile = parameters[0].valueAsText
        spiFile = parameters[1].valueAsText
        zonalFile = parameters[2].valueAsText
        zonalId = parameters[3].valueAsText
        demFile = parameters[4].valueAsText
        outErosionScoreFile = parameters[5].valueAsText
        outSummaryTable = parameters[6].valueAsText

        calculateErosionScore(usleFile, spiFile, zonalFile, zonalId, demFile, outErosionScoreFile, \
            outSummaryTable, tempDir, tempGdb)
