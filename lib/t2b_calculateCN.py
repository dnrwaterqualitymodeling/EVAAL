import arcpy
from arcpy import env
from arcpy.sa import *
import numpy as np
import json
import importlib
import downloadCDL as dcdl
importlib.reload(dcdl)
import queryCN as qcn
importlib.reload(qcn)

def calculateCN(downloadBool, yrStart, yrEnd, localCdlList, gSSURGO, watershedFile, \
    demFile, outCnLow, outCnHigh, ws):

    # Intermediate files
    years = np.arange(int(yrStart), int(yrEnd) + 1).tolist()
    watershedCdlPrj = ws['tempGdb'] + '/watershedCdlPrj_' + ws['rid']
    clipSSURGO = ws['tempGdb'] + '/clipSSURGO_' + ws['rid']
    samplePts = ws['tempGdb'] + '/samplePts_' + ws['rid']
    joinSsurgo = ws['tempGdb'] + '/joinSsurgo_' + ws['rid']
    mapunits_prj = ws['tempGdb'] + '/mapunits_prj_' + ws['rid']
    outCnLow1 = ws['tempGdb'] + '/outCnLow1_' + ws['rid']
    outCnHigh1 = ws['tempGdb'] + '/outCnHigh1_' + ws['rid']

    # Read in C-factor crosswalk table and CDL legend file
    cnLookup = np.loadtxt(ws['cnLookupFile'] \
        , dtype=[('COVER_CODE', 'i1') \
            , ('COVER_TYPE', 'S60') \
            , ('TREATMENT', 'S4') \
            , ('HYDROLOGIC_CONDITION', 'S25') \
            , ('A', 'i1') \
            , ('B', 'i1') \
            , ('C', 'i1') \
            , ('D', 'i1')] \
        , delimiter=',', skiprows=1)
    f = open(ws['coverTypeLookupFile'], 'r')
    coverTypeLookup = json.load(f)
    f.close()
    del f
    arcpy.AddMessage("Projecting Area Of Interest to Cropland Data Layer projection...")
    sr = arcpy.SpatialReference(102039)
    arcpy.Project_management(watershedFile, watershedCdlPrj, sr, "NAD_1983_To_HARN_Wisconsin")
    if downloadBool == 'true':
        arcpy.AddMessage("Downloading Cropland Data Layers...")
        cdlTiffs = dcdl.downloadCDL(yrStart, yrEnd, ws['tempDir'], watershedCdlPrj, ws['rid'])
    else:
        localCdlList = localCdlList.split(';')
        cdlTiffs = []
        years = []
        for i,localCdl in enumerate(localCdlList):
            clipCdl = tempDir + '/cdl_' + str(i) + '_' + ws['rid'] + '.tif'
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
                cn = qcn.queryCN(lc, hsg, scen, coverTypeLookup, cnLookup)
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
