import arcpy
from arcpy import env
from arcpy.sa import *
import numpy as np
import importlib
import downloadCDL as dcdl
importlib.reload(dcdl)

def cfact(downloadBool, localCdlList, watershedFile, rasterTemplateFile, yrStart, yrEnd,\
    outRotation, outHigh, outLow, ws):

    watershedCdlPrj = ws['tempGdb'] + '/watershedCdlPrj_' + ws['rid']
    samplePts = ws['tempGdb'] + '/samplePts_' + ws['rid']
    outRotation1 = ws['tempGdb'] + '/outRotation1_' + ws['rid']
    outHigh1 = ws['tempGdb'] + '/outHigh1_' + ws['rid']
    outLow1 = ws['tempGdb'] + '/outLow1_' + ws['rid']
    cdlUrl = r'http://nassgeodata.gmu.edu:8080/axis2/services/CDLService/GetCDLFile?'

    arcpy.AddMessage("Projecting Area Of Interest to Cropland Data Layer projection...")
    sr = arcpy.SpatialReference(102039)
    arcpy.Project_management(watershedFile, watershedCdlPrj, sr)
    if downloadBool == 'true':
        arcpy.AddMessage("Downloading Cropland Data Layers...")
        cdlTiffs = dcdl.downloadCDL(yrStart, yrEnd, ws['tempDir'], watershedCdlPrj, ws['rid'])
        years = np.arange(int(yrStart), int(yrEnd) + 1).tolist()
    else:
        arcpy.AddMessage("Clipping Cropland Data Layers to watershed extent...")
        localCdlList = localCdlList.split(';')
        cdlTiffs = []
        years = []
        for i,localCdl in enumerate(localCdlList):
            clipCdl = ws['tempDir'] + '/cdl_' + str(i) + '_' + ws['rid'] + '.tif'
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

    nonRotCropVals = [0] + np.arange(63,181).tolist() + np.arange(182,204).tolist()
    corn = np.array([1])
    alfalfa = np.array([28, 36, 37, 58])
    pasture = np.array([62, 181, 176])
    soyAndGrain = np.array([4,5,21,22,23,24,25,27,29,30,39,205])
    potatoes = np.array([43])
    veggies = np.array([12,42,47,49,50,53,206,216])

    # Read in C-factor crosswalk table and CDL legend file
    cFactorXwalk = np.loadtxt(ws['cFactorXwalkFile'] \
        , dtype=[('LAND_COVER', 'S40'), ('SCENARIO', 'S10'), ('C_FACTOR', 'f4')] \
        , delimiter=',', skiprows=1)

    cdlLegend = np.loadtxt(ws['legendFile'] \
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
            (pSoyAndGrain + pPotato + pVeggies + pAlfalfa + pPasture) == 0
        cashGrainBool = (pCorn + pSoyAndGrain) >= 2./5 and \
            (pPotato + pVeggies + pAlfalfa + pPasture) < 1./5
        dairyBool1 = pAlfalfa >= 1./5 and \
            (pCorn + pSoyAndGrain) >= 1./5
        dairyPotatoBool = pPotato >= 1./5 and \
            pAlfalfa >= 1./5 and \
            pVeggies < 1./5
        potGrnVegBool = (pPotato + pVeggies) >= 1./5
        pastureBool = (pPasture + pAlfalfa) >= 2./5 and \
            (pCorn + pSoyAndGrain + pPotato + pVeggies) == 0
        dairyBool2 = (pAlfalfa + pPasture + pVeggies) >= 1./5
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
                c = np.extract(cFactorXwalk['LAND_COVER'] == str(lc).encode(), cFactorXwalk['C_FACTOR'])
                if len(c) > 0:
                    c_s[j] = c
                else:
                    c_s[j] = np.nan
            if np.all(np.isnan(c_s)):
                c_high = None
                c_low = None
            else:
                c_ave = np.nansum(c_s) / np.sum(np.isfinite(c_s))
                c_high = np.double(c_ave)
                c_low = np.double(c_ave)
        if rot != "No agriculture" and rot != "No Data":
            rotBool = cFactorXwalk['LAND_COVER'] == rot.encode()
            highBool = np.in1d(cFactorXwalk['SCENARIO'], np.array(['High', ''], dtype="|S25"))
            lowBool = np.in1d(cFactorXwalk['SCENARIO'], np.array(['Low', ''], dtype="|S25"))
            c_high = np.extract(np.logical_and(rotBool, highBool), cFactorXwalk['C_FACTOR'])
            c_low = np.extract(np.logical_and(rotBool, lowBool), cFactorXwalk['C_FACTOR'])
            c_high = c_high[0]
            c_low = c_low[0]
        if (c_high is not None):
            c_high = float(c_high)
        if (c_low is not None):
            c_low = float(c_low)
        row.setValue("cFactorHigh", c_high)
        row.setValue("cFactorLow", c_low)
        row.setValue("rotation", rot)
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
