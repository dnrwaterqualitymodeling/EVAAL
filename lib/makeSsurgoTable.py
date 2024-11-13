import arcpy
import numpy as np
import os

def makeSsurgoTable(dataDict, tableFile):
    if arcpy.Exists(tableFile):
        arcpy.Delete_management(tableFile)
    arcpy.CreateTable_management(os.path.dirname(tableFile), os.path.basename(tableFile))
    arcpy.AddField_management(tableFile, 'element', 'TEXT', '', '', 15)
    arcpy.AddField_management(tableFile, 'attAve', 'FLOAT', 5, 3)
    arcpy.AddField_management(tableFile, 'wt_sum', 'FLOAT', 5, 3)
    rows = arcpy.InsertCursor(tableFile)
    for i,m in enumerate(np.unique(dataDict['element'])):
        row = rows.newRow()
        row.element = str(m.decode())
        row.attAve = float(dataDict['attAve'][i,0])
        row.wt_sum = float(dataDict['attAve'][i,1])
        rows.insertRow(row)
    del row, rows
