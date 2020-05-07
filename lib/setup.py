import arcpy
from arcpy import env
import os
import random
import shutil
import subprocess as sp


def setupWorkspace(wd):
    optFillExe = wd + '/etc/OptimizedPitRemoval.exe'
    cnLookupFile = wd + '/etc/curveNumberLookup.csv'
    legendFile = wd + '/etc/cdlLegend.csv'
    cFactorXwalkFile = wd + '/etc/cFactorLookup.csv'
    coverTypeLookupFile = wd + '/etc/coverTypeLookup.json'
    rotationSymbologyFile = wd + '/etc/rotationSymbology.lyr'
    env.scratchWorkspace = wd + '/temp'
    tempDir = env.scratchFolder
    tempGdb = env.scratchGDB
    env.workspace = tempGdb
    env.overwriteOutput = True
    os.environ['ARCTMPDIR'] = tempDir
    arcpy.CheckOutExtension("Spatial")
    arcpy.env.pyramid = 'NONE'
    arcpy.env.rasterStatistics = 'NONE'
    rid = str(random.randint(111111, 999999))
    arcpy.AddMessage("Run ID: " + rid)
    startupinfo = sp.STARTUPINFO()
    startupinfo.dwFlags |= sp.STARTF_USESHOWWINDOW
    ws = {
        'optFillExe': optFillExe,
        'cnLookupFile': cnLookupFile,
        'legendFile': legendFile,
        'cFactorXwalkFile': cFactorXwalkFile,
        'coverTypeLookupFile': coverTypeLookupFile,
        'rotationSymbologyFile': rotationSymbologyFile,
        'tempDir': tempDir,
        'tempGdb': tempGdb,
        'rid': rid,
        'startupinfo': startupinfo
    }
    return ws

def setupTemp(tempDir, tempGdb):
    # env.workspace = tempGdb
    # env.scratchWorkspace = os.path.dirname(tempDir)
    # tempDir = env.scratchFolder
    # tempGdb = env.scratchGDB
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
